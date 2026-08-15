from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.status_report import (
    ActivityTableRow,
    DayBlock,
    FrontMatterSummary,
    _activity_table_rows,
    _activity_timetable_blocks,
    _camp_date_range,
    _distinct_camp_days,
    _front_matter_summary,
    _render_activity_table,
    _render_activity_timetable_drawing,
    _render_activity_timetable_fallback,
    _render_front_matter,
)

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
