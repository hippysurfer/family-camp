from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.class2 import (
    Tier0Weights,
    check_class2,
    find_family_time_conflicts,
    find_missing_priorities,
    find_under_minimum_sessions,
    find_unmet_compulsory_activities,
    find_unsupervised_family_splits,
    score_tier0,
)

DAY = datetime(2026, 8, 1)


def activity(name, minutes=60, min_occ=2, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_clean_timetable_reports_nothing():
    archery = activity("Archery")
    c = camper("Kid", priorities=(archery,))
    s = session(archery, "A", 10)
    c2 = camper("Kid2", family="F2", priorities=(archery,))
    tt = Timetable().with_assignment(c, s).with_assignment(c2, s)  # 2 in session, meets min_occ=2

    report = check_class2(tt, campers=[c, c2])
    assert report.is_clean


def test_missing_priority_detected():
    archery = activity("Archery")
    c = camper("Kid", priorities=(archery,))
    tt = Timetable()  # never assigned

    violations = find_missing_priorities(tt, [c])
    assert len(violations) == 1
    assert violations[0].camper == c
    assert violations[0].activity == archery


def test_family_time_conflict_detected():
    archery = activity("Archery")
    canoeing = activity("Canoeing")
    parent = camper("Parent", age=40, age_group="Adult", priorities=(archery,))
    kid = camper("Kid", age=10, priorities=(canoeing,))

    s1 = session(archery, "A", 10)
    s2 = session(canoeing, "B", 10)  # overlaps s1

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    violations = find_family_time_conflicts(tt)

    assert len(violations) == 1
    assert {violations[0].camper_a, violations[0].camper_b} == {parent, kid}


def test_family_together_in_same_session_is_not_a_conflict():
    archery = activity("Archery")
    parent = camper("Parent", age=40, age_group="Adult", priorities=(archery,))
    kid = camper("Kid", age=10, priorities=(archery,))
    s = session(archery, "A", 10)

    tt = Timetable().with_assignment(parent, s).with_assignment(kid, s)
    assert find_family_time_conflicts(tt) == []


def test_unsupervised_family_split_flags_session_without_an_adult():
    swimming = activity("Swimming", max_occ=1)  # forces the family apart
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)  # non-overlapping with s1

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    violations = find_unsupervised_family_splits(tt)

    assert len(violations) == 1
    assert violations[0].session == s2  # the session with only the child


def test_family_split_with_adult_in_every_session_is_not_flagged():
    swimming = activity("Swimming", max_occ=1)
    parent1 = camper("Parent1", age=40, age_group="Adult", priorities=(swimming,))
    parent2 = camper("Parent2", age=42, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)

    tt = (
        Timetable()
        .with_assignment(parent1, s1)
        .with_assignment(parent2, s2)
        .with_assignment(kid, s2)
    )
    assert find_unsupervised_family_splits(tt) == []


def test_under_minimum_session_detected():
    archery = activity("Archery", min_occ=3)
    c = camper("Kid", priorities=(archery,))
    s = session(archery, "A", 10)

    tt = Timetable().with_assignment(c, s)
    violations = find_under_minimum_sessions(tt)

    assert len(violations) == 1
    assert violations[0].count == 1
    assert violations[0].min_occupancy == 3


def test_empty_session_is_not_under_minimum():
    archery = activity("Archery", min_occ=3)
    s = session(archery, "A", 10)
    tt = Timetable()

    assert find_under_minimum_sessions(tt) == []


def test_unmet_compulsory_activity_detected():
    bbq = activity("Saturday BBQ")
    c = camper("Kid")
    tt = Timetable()

    violations = find_unmet_compulsory_activities(tt, [c], frozenset({bbq}))
    assert len(violations) == 1
    assert violations[0].activity == bbq


def test_no_compulsory_activities_by_default_means_no_violations():
    c = camper("Kid")
    tt = Timetable()
    assert find_unmet_compulsory_activities(tt, [c], frozenset()) == []


def test_score_tier0_matches_hand_computed_weighted_sum():
    archery = activity("Archery")
    c = camper("Kid", priorities=(archery,))  # missing priority: never assigned
    tt = Timetable()

    report = check_class2(tt, campers=[c])
    weights = Tier0Weights()

    assert len(report.missing_priorities) == 1
    expected = 1 * weights.missing_priority
    assert score_tier0(report, weights) == expected


def test_score_tier0_ranks_priority_violation_above_many_lesser_violations():
    """A single missing-priority violation must outweigh even the largest
    plausible number of lower-severity violations at REQUIREMENTS.md NFR-1's
    scale (upper bound: 500 campers), per the severity-ordering rationale in
    Tier0Weights' docstring."""
    weights = Tier0Weights()
    max_plausible_count = 500

    priority_only_score = score_tier0(
        _report_with(missing_priorities=1), weights
    )
    many_lesser_score = score_tier0(
        _report_with(
            family_conflicts=max_plausible_count,
            under_minimum=max_plausible_count,
            compulsory=max_plausible_count,
        ),
        weights,
    )

    assert priority_only_score > many_lesser_score


def _report_with(missing_priorities=0, family_conflicts=0, under_minimum=0, compulsory=0):
    from family_camp2.validation.class2 import Class2Report

    return Class2Report(
        missing_priorities=[object()] * missing_priorities,
        family_time_conflicts=[object()] * family_conflicts,
        under_minimum_sessions=[object()] * under_minimum,
        unmet_compulsory=[object()] * compulsory,
    )
