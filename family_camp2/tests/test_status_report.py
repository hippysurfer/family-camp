from datetime import datetime, timedelta

from family_camp2.config import EngineConfig
from family_camp2.constraints.base import ConstraintInstance
from family_camp2.constraints.rules import NoActivityBefore
from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable
from family_camp2.status_report import (
    ActivityTableRow,
    CamperLoadingRow,
    CustomConstraintSummary,
    DayBlock,
    FamilyLoadingRow,
    FrontMatterSummary,
    SessionLoadingRow,
    SolverInfo,
    _activity_table_rows,
    _activity_timetable_blocks,
    _camp_date_range,
    _camper_loading_rows,
    _custom_constraint_summary,
    _distinct_camp_days,
    _family_loading_rows,
    _front_matter_summary,
    _paginate,
    _render_activity_table,
    _render_activity_timetable_drawing,
    _render_activity_timetable_fallback,
    _render_camper_loading_charts,
    _render_family_loading_charts,
    _render_front_matter,
    _render_overdemand_callout,
    _render_session_loading_charts,
    _render_solver_info,
    _session_loading_rows,
    _session_loading_stats,
    render_status_report_pdf,
)
from family_camp2.validation.class2 import Class2Report, MissingPriority, UnderMinimumSession
from family_camp2.validation.custom_constraints import CustomConstraintViolation
from family_camp2.validation.feasibility import FamilyOverdemand
from family_camp2.validation.tiers import UnmetOptionalRequest
from family_camp2.validation.validator import validate

DAY1 = datetime(2026, 8, 1, 9, 0)
DAY2 = datetime(2026, 8, 2, 9, 0)
DAY3 = datetime(2026, 8, 3, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ)


def session(act, label, start):
    return Session(activity=act, label=label, start=start)


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


# --- front matter ---


def test_camp_date_range_spans_earliest_start_to_latest_end():
    archery = activity("Archery", minutes=60)
    craft = activity("Craft", minutes=30)
    sessions = [session(archery, "A", DAY1), session(craft, "B", DAY2 + timedelta(hours=2))]

    start, end = _camp_date_range(sessions)

    assert start == DAY1
    assert end == DAY2 + timedelta(hours=2, minutes=30)


def test_distinct_camp_days_deduplicates_and_sorts():
    archery = activity("Archery")
    sessions = [
        session(archery, "A", DAY2),
        session(archery, "B", DAY1),
        session(archery, "C", DAY1 + timedelta(hours=3)),
    ]

    assert _distinct_camp_days(sessions) == [DAY1.date(), DAY2.date()]


def test_front_matter_summary_computes_headline_counts():
    archery = activity("Archery")
    craft = activity("Craft")
    sessions = [session(archery, "A", DAY1), session(craft, "B", DAY2)]
    campers = [camper("Kid", family="F1"), camper("Parent", family="F1", age=40), camper("Alex", family="F2", age=30)]
    generated_at = datetime(2026, 7, 1, 12, 0)

    summary = _front_matter_summary([archery, craft], sessions, campers, generated_at)

    assert summary.generated_at == generated_at
    assert summary.camp_start == DAY1
    assert summary.camp_end == DAY2 + craft.duration
    assert summary.num_activities == 2
    assert summary.num_sessions == 2
    assert summary.num_campers == 3
    assert summary.num_families == 2


def test_front_matter_summary_camp_duration_property():
    summary = FrontMatterSummary(
        generated_at=DAY1, camp_start=DAY1, camp_end=DAY1 + timedelta(hours=30),
        num_activities=1, num_sessions=1, num_campers=1, num_families=1,
    )
    assert summary.camp_duration == timedelta(hours=30)


def test_render_front_matter_produces_one_flowable_per_line():
    summary = FrontMatterSummary(
        generated_at=DAY1, camp_start=DAY1, camp_end=DAY2,
        num_activities=3, num_sessions=10, num_campers=50, num_families=20,
    )
    flowables = _render_front_matter(summary)
    assert len(flowables) == 4


# --- activity table ---


def test_activity_table_rows_counts_sessions_and_flags_compulsory():
    archery = activity("Archery")
    craft = activity("Craft")
    sessions = [session(archery, "A", DAY1), session(archery, "B", DAY1 + timedelta(hours=2))]

    rows = _activity_table_rows([archery, craft], sessions, compulsory=frozenset({archery}))

    by_name = {r.activity.name: r for r in rows}
    assert by_name["Archery"].num_sessions == 2
    assert by_name["Archery"].is_compulsory is True
    assert by_name["Craft"].num_sessions == 0
    assert by_name["Craft"].is_compulsory is False


def test_activity_table_rows_sorted_by_name():
    rows = _activity_table_rows([activity("Zebra"), activity("Archery")], [], compulsory=frozenset())
    assert [r.activity.name for r in rows] == ["Archery", "Zebra"]


def test_render_activity_table_has_one_row_per_activity_plus_header():
    rows = [
        ActivityTableRow(activity("Archery"), num_sessions=2, is_compulsory=True),
        ActivityTableRow(activity("Craft"), num_sessions=0, is_compulsory=False),
    ]
    table = _render_activity_table(rows)
    assert len(table._cellvalues) == 3  # header + 2 activities


# --- activity timetable blocks / graphic / fallback ---


def test_activity_timetable_blocks_returns_none_when_not_exactly_two_days():
    archery = activity("Archery")
    one_day = [session(archery, "A", DAY1)]
    three_days = [session(archery, "A", DAY1), session(archery, "B", DAY2), session(archery, "C", DAY3)]

    assert _activity_timetable_blocks([archery], one_day) is None
    assert _activity_timetable_blocks([archery], three_days) is None


def test_activity_timetable_blocks_computes_offsets_for_a_genuine_two_day_camp():
    archery = activity("Archery", minutes=60)
    s1 = session(archery, "Morning", DAY1)  # 09:00 on day 1
    s2 = session(archery, "Afternoon", DAY2 + timedelta(hours=5))  # 14:00 on day 2

    blocks = _activity_timetable_blocks([archery], [s1, s2])

    assert blocks is not None
    assert len(blocks) == 2
    by_session = {b.session: b for b in blocks}
    assert by_session[s1].start_offset_minutes == 9 * 60
    assert by_session[s1].duration_minutes == 60
    assert by_session[s1].day == DAY1.date()
    assert by_session[s2].start_offset_minutes == 14 * 60
    assert by_session[s2].day == DAY2.date()


def test_render_activity_timetable_drawing_produces_a_block_per_session():
    archery = activity("Archery", minutes=60)
    craft = activity("Craft", minutes=30)
    s1 = session(archery, "Morning", DAY1)
    s2 = session(craft, "Morning", DAY2 + timedelta(hours=1))
    blocks = _activity_timetable_blocks([archery, craft], [s1, s2])

    drawing = _render_activity_timetable_drawing(blocks, [archery, craft], width=400)

    # 2 activity-row labels + 2 activity-row gridlines + 2 day headers + 2 session blocks
    assert len(drawing.contents) == 8


def test_render_activity_timetable_fallback_has_one_row_per_session_plus_header():
    archery = activity("Archery")
    sessions = [session(archery, "A", DAY1), session(archery, "B", DAY2), session(archery, "C", DAY3)]

    table = _render_activity_timetable_fallback(sessions)

    assert len(table._cellvalues) == 4  # header + 3 sessions


# --- activity session loading (FR-102) ---


def test_session_loading_rows_computes_occupancy_spare_and_under_minimum_flag():
    archery = activity("Archery", min_occ=2, max_occ=4)
    s1 = session(archery, "Full", DAY1)
    s2 = session(archery, "Under", DAY1 + timedelta(hours=2))
    kid = camper("Kid")
    parent = camper("Parent", age=40)
    timetable = Timetable(frozenset({Assignment(kid, s1), Assignment(parent, s1)}))
    class2_report = Class2Report(under_minimum_sessions=[UnderMinimumSession(session=s2, count=0, min_occupancy=2)])

    rows = _session_loading_rows(timetable, [s1, s2], class2_report)

    by_label = {r.session.label: r for r in rows}
    assert by_label["Full"].occupancy == 2
    assert by_label["Full"].capacity == 4
    assert by_label["Full"].spare == 2
    assert by_label["Full"].under_minimum is False
    assert by_label["Under"].occupancy == 0
    assert by_label["Under"].spare == 4
    assert by_label["Under"].under_minimum is True


def test_session_loading_rows_sorted_by_activity_then_start():
    craft = activity("Craft")
    archery = activity("Archery")
    s1 = session(craft, "A", DAY1)
    s2 = session(archery, "B", DAY1 + timedelta(hours=1))
    rows = _session_loading_rows(Timetable(), [s1, s2], Class2Report())
    assert [r.session.activity.name for r in rows] == ["Archery", "Craft"]


def test_session_loading_stats_computes_mean_and_stdev_of_spare_capacity():
    rows = [
        SessionLoadingRow(session=None, capacity=10, occupancy=8, spare=2, under_minimum=False),
        SessionLoadingRow(session=None, capacity=10, occupancy=4, spare=6, under_minimum=False),
        SessionLoadingRow(session=None, capacity=10, occupancy=10, spare=0, under_minimum=True),
    ]

    stats = _session_loading_stats(rows)

    assert stats.mean_spare == (2 + 6 + 0) / 3
    assert stats.under_minimum_count == 1


def test_session_loading_stats_handles_no_sessions():
    stats = _session_loading_stats([])
    assert stats.mean_spare == 0.0
    assert stats.stdev_spare == 0.0
    assert stats.under_minimum_count == 0


# --- pagination ---


def test_paginate_splits_evenly():
    assert _paginate([1, 2, 3, 4], per_page=2) == [[1, 2], [3, 4]]


def test_paginate_handles_a_remainder_page():
    assert _paginate([1, 2, 3, 4, 5], per_page=2) == [[1, 2], [3, 4], [5]]


def test_paginate_handles_empty_input():
    assert _paginate([], per_page=2) == []


def test_render_session_loading_charts_produces_one_drawing_per_page():
    archery = activity("Archery")
    rows = [
        SessionLoadingRow(session=session(archery, f"S{i}", DAY1), capacity=10, occupancy=i, spare=10 - i, under_minimum=False)
        for i in range(5)
    ]

    drawings = _render_session_loading_charts(rows, width=400, per_page=2)

    assert len(drawings) == 3  # 2 + 2 + 1
    assert all(len(d.contents) == 1 for d in drawings)  # one chart per page


# --- camper activity loading (FR-103) ---


def test_camper_loading_rows_computes_met_and_unmet_counts():
    archery = activity("Archery")
    craft = activity("Craft")
    zipline = activity("Zipline")
    fully_satisfied = camper("Fully", priorities=(archery,), optional=(craft,))
    partly_unmet = camper("Partly", priorities=(archery, zipline), optional=(craft,))

    class2_report = Class2Report(missing_priorities=[MissingPriority(camper=partly_unmet, activity=zipline)])
    unmet_optional = [UnmetOptionalRequest(camper=partly_unmet, activity=craft)]

    rows = _camper_loading_rows([fully_satisfied, partly_unmet], class2_report, unmet_optional)

    by_name = {r.camper.name: r for r in rows}
    assert by_name["Fully"].priorities_met == 1
    assert by_name["Fully"].priorities_unmet == 0
    assert by_name["Fully"].optional_met == 1
    assert by_name["Fully"].optional_unmet == 0
    assert by_name["Fully"].has_unmet_priority is False

    assert by_name["Partly"].priorities_met == 1
    assert by_name["Partly"].priorities_unmet == 1
    assert by_name["Partly"].optional_met == 0
    assert by_name["Partly"].optional_unmet == 1
    assert by_name["Partly"].has_unmet_priority is True


def test_camper_loading_rows_sorted_by_family_then_name():
    rows = _camper_loading_rows(
        [
            camper("Zoe", family="F2"),
            camper("Bob", family="F1"),
            camper("Amy", family="F1"),
        ],
        Class2Report(),
        [],
    )
    assert [(r.camper.family_id, r.camper.name) for r in rows] == [
        ("F1", "Amy"), ("F1", "Bob"), ("F2", "Zoe"),
    ]


def test_render_camper_loading_charts_produces_one_drawing_per_page():
    rows = [
        CamperLoadingRow(
            camper=camper(f"C{i}"), priorities_met=1, priorities_unmet=0, optional_met=0, optional_unmet=0,
            has_unmet_priority=False,
        )
        for i in range(7)
    ]

    drawings = _render_camper_loading_charts(rows, width=400, per_page=3)

    assert len(drawings) == 3  # 3 + 3 + 1
    assert all(len(d.contents) == 1 for d in drawings)


# --- family activity loading + overdemand callout (FR-104/105) ---


def test_family_loading_rows_aggregates_camper_rows_by_family():
    camper_rows = [
        CamperLoadingRow(
            camper=camper("Amy", family="F1"), priorities_met=1, priorities_unmet=0,
            optional_met=1, optional_unmet=0, has_unmet_priority=False,
        ),
        CamperLoadingRow(
            camper=camper("Bob", family="F1"), priorities_met=0, priorities_unmet=1,
            optional_met=0, optional_unmet=1, has_unmet_priority=True,
        ),
        CamperLoadingRow(
            camper=camper("Zoe", family="F2"), priorities_met=2, priorities_unmet=0,
            optional_met=0, optional_unmet=0, has_unmet_priority=False,
        ),
    ]

    rows = _family_loading_rows(camper_rows)

    by_family = {r.family_id: r for r in rows}
    assert by_family["F1"].priorities_met == 1
    assert by_family["F1"].priorities_unmet == 1
    assert by_family["F1"].optional_met == 1
    assert by_family["F1"].optional_unmet == 1
    assert by_family["F1"].has_unmet_priority is True
    assert by_family["F2"].has_unmet_priority is False
    assert [r.family_id for r in rows] == ["F1", "F2"]  # sorted


def test_render_family_loading_charts_produces_one_drawing_per_page():
    rows = [
        FamilyLoadingRow(
            family_id=f"F{i}", priorities_met=1, priorities_unmet=0, optional_met=0, optional_unmet=0,
            has_unmet_priority=False,
        )
        for i in range(5)
    ]

    drawings = _render_family_loading_charts(rows, width=400, per_page=2)

    assert len(drawings) == 3  # 2 + 2 + 1
    assert all(len(d.contents) == 1 for d in drawings)


def test_render_overdemand_callout_returns_none_when_nothing_is_overdemanding():
    assert _render_overdemand_callout([]) is None


def test_render_overdemand_callout_returns_a_table_with_a_row_per_family():
    overdemand = [
        FamilyOverdemand(family_id="F1", members=(camper("Amy", family="F1"),), requested_count=5, available_timeslots=3),
        FamilyOverdemand(family_id="F2", members=(camper("Zoe", family="F2"),), requested_count=4, available_timeslots=2),
    ]

    table = _render_overdemand_callout(overdemand)

    assert table is not None
    assert len(table._cellvalues) == 3  # header + 2 families


# --- solver information + document assembly (FR-106) ---


def test_custom_constraint_summary_counts_hard_soft_and_violated():
    archery = activity("Archery")
    emma = camper("Emma", priorities=(archery,))
    hard = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="hard")
    soft_violated = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="12:00"), severity="soft")
    soft_clean = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="08:00"), severity="soft")
    config = EngineConfig(constraints=(hard, soft_violated, soft_clean))
    class2_report = Class2Report(
        custom_constraint_violations=[
            CustomConstraintViolation(camper=emma, session=session(archery, "A", DAY1), constraint=soft_violated)
        ]
    )

    summary = _custom_constraint_summary(config, class2_report)

    assert summary.hard_count == 1
    assert summary.soft_count == 2
    assert summary.soft_violated_count == 1


def test_render_solver_info_states_na_when_no_solver_was_run():
    report = validate(Timetable(), [], [])
    solver_info = SolverInfo()
    summary = CustomConstraintSummary(hard_count=0, soft_count=0, soft_violated_count=0)

    flowables = _render_solver_info(report, solver_info, summary)

    assert "N/A" in flowables[0].text


def test_render_solver_info_states_solver_name_and_duration_when_present():
    report = validate(Timetable(), [], [])
    solver_info = SolverInfo(solver_name="cp_sat", duration_seconds=12.3, diagnostics={"phase1_status": "OPTIMAL"})
    summary = CustomConstraintSummary(hard_count=1, soft_count=2, soft_violated_count=1)

    flowables = _render_solver_info(report, solver_info, summary)

    assert "cp_sat" in flowables[0].text
    assert "12.3" in flowables[0].text


def _assert_valid_pdf(path):
    assert path.exists()
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 500


def _small_camp():
    archery = activity("Archery", minutes=60, max_occ=4)
    craft = activity("Craft", minutes=30, max_occ=2)
    s1 = session(archery, "Morning", DAY1)
    s2 = session(craft, "Morning", DAY2 + timedelta(hours=1))
    emma = camper("Emma", family="F1", priorities=(archery,), optional=(craft,))
    sam = camper("Sam", family="F2", age=9, priorities=(craft,))
    activities = [archery, craft]
    sessions = [s1, s2]
    campers = [emma, sam]
    timetable = Timetable(frozenset({Assignment(emma, s1), Assignment(sam, s2)}))
    return activities, sessions, campers, timetable


def test_render_status_report_pdf_end_to_end_with_a_real_solver_info(tmp_path):
    activities, sessions, campers, timetable = _small_camp()
    report = validate(timetable, campers, sessions)
    config = EngineConfig()
    solver_info = SolverInfo(solver_name="cp_sat", duration_seconds=1.5, diagnostics={"tier0_optimum": 0})
    output_path = tmp_path / "status_report.pdf"

    render_status_report_pdf(activities, sessions, campers, timetable, report, config, solver_info, output_path)

    _assert_valid_pdf(output_path)


def test_render_status_report_pdf_end_to_end_for_the_revalidate_case(tmp_path):
    activities, sessions, campers, timetable = _small_camp()
    report = validate(timetable, campers, sessions)
    config = EngineConfig()
    output_path = tmp_path / "status_report.pdf"

    render_status_report_pdf(activities, sessions, campers, timetable, report, config, SolverInfo(), output_path)

    _assert_valid_pdf(output_path)


def test_render_status_report_pdf_handles_a_non_two_day_camp(tmp_path):
    archery = activity("Archery")
    s1 = session(archery, "A", DAY1)
    s2 = session(archery, "B", DAY2)
    s3 = session(archery, "C", DAY3)
    kid = camper("Kid", priorities=(archery,))
    activities = [archery]
    sessions = [s1, s2, s3]
    campers = [kid]
    timetable = Timetable(frozenset({Assignment(kid, s1)}))
    report = validate(timetable, campers, sessions)
    output_path = tmp_path / "status_report.pdf"

    render_status_report_pdf(
        activities, sessions, campers, timetable, report, EngineConfig(), SolverInfo(), output_path
    )

    _assert_valid_pdf(output_path)
