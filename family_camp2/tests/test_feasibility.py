from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.validation.feasibility import (
    CamperOverdemand,
    find_overdemanding_campers,
    max_non_overlapping_sessions,
)

DAY = datetime(2026, 8, 1)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(
        name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age
    )


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_max_non_overlapping_sessions_empty_list_is_zero():
    assert max_non_overlapping_sessions([]) == 0


def test_max_non_overlapping_sessions_counts_disjoint_sessions():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    s1 = session(craft, "A", 9)
    s2 = session(canoeing, "A", 11)

    assert max_non_overlapping_sessions([s1, s2]) == 2


def test_max_non_overlapping_sessions_counts_overlapping_sessions_once():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    s1 = session(craft, "A", 9)
    s2 = session(canoeing, "A", 9)  # same start time as s1 - can't attend both

    assert max_non_overlapping_sessions([s1, s2]) == 1


def test_find_overdemanding_campers_flags_a_camper_who_wants_more_than_can_ever_fit():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    archery = activity("Archery")
    # All three sessions run at the same time - at most 1 of the 3 requested
    # activities could ever be attended, regardless of session capacity.
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9), session(archery, "A", 9)]
    kid = camper("Kid", optional=(craft, canoeing, archery))

    overdemanding = find_overdemanding_campers(sessions, [kid])

    assert overdemanding == [CamperOverdemand(kid, requested_count=3, available_timeslots=1)]


def test_find_overdemanding_campers_not_flagged_when_requests_fit():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 11)]  # non-overlapping
    kid = camper("Kid", optional=(craft, canoeing))

    assert find_overdemanding_campers(sessions, [kid]) == []


def test_find_overdemanding_campers_skips_campers_with_no_requests():
    craft = activity("Craft")
    sessions = [session(craft, "A", 9)]
    bystander = camper("Bystander")  # no priorities or optional activities

    assert find_overdemanding_campers(sessions, [bystander]) == []


def test_find_overdemanding_campers_respects_age_eligibility():
    # Only one of the two same-time sessions is age-eligible for this camper,
    # so their real ceiling is 1 - but only the age-eligible one counts as a
    # slot at all, and it's the only thing they requested, so this is fine.
    craft = activity("Craft", min_age=18)
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9)]
    kid = camper("Kid", age=10, optional=(canoeing,))

    assert find_overdemanding_campers(sessions, [kid]) == []


def test_find_overdemanding_campers_counts_distinct_activities_not_priorities_plus_optional_separately():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9)]  # overlapping - 1 slot max
    kid = camper("Kid", priorities=(craft,), optional=(canoeing,))

    overdemanding = find_overdemanding_campers(sessions, [kid])

    assert overdemanding == [CamperOverdemand(kid, requested_count=2, available_timeslots=1)]
