from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.class2 import (
    Tier0Weights,
    check_class2,
    find_family_splits,
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


def test_unsupervised_family_split_flags_lone_adult_session():
    swimming = activity("Swimming", max_occ=1)  # forces the family apart
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)  # non-overlapping with s1

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    violations = find_unsupervised_family_splits(tt, [parent, kid])

    # s1 (parent alone, no child) is a lone-adult violation. s2 (kid alone)
    # is fine: the parent isn't assigned to anything overlapping s2's time,
    # so they're free to informally accompany the kid there.
    assert len(violations) == 1
    assert violations[0].session == s1
    assert violations[0].reason == "lone_adult"


def test_unsupervised_family_split_flags_unaccompanied_child_when_no_adult_is_idle():
    swimming = activity("Swimming", max_occ=1)
    canoeing = activity("Canoeing")
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,), optional=(canoeing,))
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)
    parent_busy = session(canoeing, "A", 14)  # overlaps s2 - parent is NOT idle then

    tt = (
        Timetable()
        .with_assignment(parent, s1)
        .with_assignment(parent, parent_busy)
        .with_assignment(kid, s2)
    )
    violations = find_unsupervised_family_splits(tt, [parent, kid])

    # s1 is a lone-adult violation (as above). s2's child is unaccompanied
    # AND the parent is busy in a different, overlapping session at that
    # time - no idle adult available to informally accompany the kid.
    reasons = {v.session: v.reason for v in violations}
    assert reasons[s1] == "lone_adult"
    assert reasons[s2] == "unaccompanied_child"


def test_unsupervised_family_split_allows_unaccompanied_child_when_an_adult_is_idle():
    swimming = activity("Swimming", max_occ=1)
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    violations = find_unsupervised_family_splits(tt, [parent, kid])

    assert all(v.session != s2 for v in violations)  # parent is idle (free) during s2


def test_unsupervised_family_split_allows_unaccompanied_child_when_an_adult_has_no_assignments_at_all():
    swimming = activity("Swimming", max_occ=1)
    canoeing = activity("Canoeing")
    parent1 = camper("Parent1", age=40, age_group="Adult", priorities=(swimming,), optional=(canoeing,))
    parent2 = camper("Parent2", age=42, age_group="Adult")  # never assigned to anything - trivially idle
    kid = camper("Kid", age=10, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)
    parent1_busy = session(canoeing, "A", 14)  # overlaps s2 - parent1 alone would NOT be idle then

    tt = (
        Timetable()
        .with_assignment(parent1, s1)
        .with_assignment(parent1, parent1_busy)
        .with_assignment(kid, s2)
    )
    violations = find_unsupervised_family_splits(tt, [parent1, parent2, kid])

    # Only parent2 - who has no assignments at all - is idle during s2;
    # that alone is enough to excuse the otherwise-unaccompanied kid.
    assert all(v.session != s2 for v in violations)


def test_family_split_with_adult_and_child_in_every_session_is_not_flagged():
    swimming = activity("Swimming", max_occ=2)
    parent1 = camper("Parent1", age=40, age_group="Adult", priorities=(swimming,))
    parent2 = camper("Parent2", age=42, age_group="Adult", priorities=(swimming,))
    kid1 = camper("Kid1", age=10, priorities=(swimming,))
    kid2 = camper("Kid2", age=11, priorities=(swimming,))

    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)

    tt = (
        Timetable()
        .with_assignment(parent1, s1)
        .with_assignment(kid1, s1)
        .with_assignment(parent2, s2)
        .with_assignment(kid2, s2)
    )
    assert find_unsupervised_family_splits(tt, [parent1, parent2, kid1, kid2]) == []


def test_unsupervised_family_split_applies_to_optional_not_just_priority_activities():
    """FR-17 covers both priority and optional activities - a family split
    confined entirely to optional activities must still be detected."""
    bushcraft = activity("Bushcraft skills", max_occ=1)
    parent = camper("Parent", age=40, age_group="Adult", optional=(bushcraft,))
    kid = camper("Kid", age=10, optional=(bushcraft,))

    s1 = session(bushcraft, "Morning", 9)
    s2 = session(bushcraft, "Afternoon", 14)

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    violations = find_unsupervised_family_splits(tt, [parent, kid])

    assert len(violations) == 1
    assert violations[0].session == s1
    assert violations[0].reason == "lone_adult"


def test_unsupervised_family_split_not_flagged_when_no_child_ever_requested_the_activity():
    """An activity only the adults in the family asked for can never have a
    child attend it, no matter what the solver does - flagging every split
    session as lone-adult would be a permanent, unfixable penalty."""
    yoga = activity("Adult Yoga", max_occ=1)
    parent1 = camper("Parent1", age=40, age_group="Adult", priorities=(yoga,))
    parent2 = camper("Parent2", age=42, age_group="Adult", priorities=(yoga,))
    kid = camper("Kid", age=10)  # in the family, but never requested yoga

    s1 = session(yoga, "Morning", 9)
    s2 = session(yoga, "Afternoon", 14)

    tt = Timetable().with_assignment(parent1, s1).with_assignment(parent2, s2)
    assert find_unsupervised_family_splits(tt, [parent1, parent2, kid]) == []


def test_find_family_splits_reports_the_split_family_activity_pair():
    swimming = activity("Swimming", max_occ=1)
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))
    s1 = session(swimming, "Morning", 9)
    s2 = session(swimming, "Afternoon", 14)

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s2)
    splits = find_family_splits(tt)

    assert len(splits) == 1
    assert splits[0].family_id == "F1"
    assert splits[0].activity == swimming
    assert set(splits[0].sessions) == {s1, s2}


def test_find_family_splits_empty_when_family_stays_together():
    swimming = activity("Swimming", max_occ=2)
    parent = camper("Parent", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", age=10, priorities=(swimming,))
    s1 = session(swimming, "Morning", 9)

    tt = Timetable().with_assignment(parent, s1).with_assignment(kid, s1)
    assert find_family_splits(tt) == []


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


def test_score_tier0_ranks_family_split_above_many_lesser_violations_but_below_family_safety():
    """FR-24: a family split, even a properly-supervised one, should be
    avoided ahead of under_minimum/compulsory issues - but never traded
    against an actual family-safety violation (a time conflict or a poorly
    supervised split)."""
    weights = Tier0Weights()
    max_plausible_count = 500

    split_only_score = score_tier0(_report_with(family_splits=1), weights)
    many_lesser_score = score_tier0(
        _report_with(under_minimum=max_plausible_count, compulsory=max_plausible_count), weights
    )
    assert split_only_score > many_lesser_score

    many_splits_score = score_tier0(_report_with(family_splits=max_plausible_count), weights)
    one_safety_violation_score = score_tier0(_report_with(family_conflicts=1), weights)
    assert one_safety_violation_score > many_splits_score


def _report_with(missing_priorities=0, family_conflicts=0, family_splits=0, under_minimum=0, compulsory=0):
    from family_camp2.validation.class2 import Class2Report

    return Class2Report(
        missing_priorities=[object()] * missing_priorities,
        family_time_conflicts=[object()] * family_conflicts,
        family_splits=[object()] * family_splits,
        under_minimum_sessions=[object()] * under_minimum,
        unmet_compulsory=[object()] * compulsory,
    )
