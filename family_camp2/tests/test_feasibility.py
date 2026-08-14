from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.validation.feasibility import (
    FamilyOverdemand,
    find_overdemanding_families,
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


def test_find_overdemanding_families_flags_a_family_who_wants_more_than_can_ever_fit():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    archery = activity("Archery")
    # All three sessions run at the same time - at most 1 of the 3 requested
    # activities could ever be attended by the family, regardless of who
    # attends which one, since none of them can overlap for the family.
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9), session(archery, "A", 9)]
    kid = camper("Kid", optional=(craft, canoeing, archery))

    overdemanding = find_overdemanding_families(sessions, [kid])

    assert overdemanding == [FamilyOverdemand("F1", (kid,), requested_count=3, available_timeslots=1)]


def test_find_overdemanding_families_unions_distinct_requests_across_members():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    archery = activity("Archery")
    # Same-time sessions again, but the 3 requests are split across 2
    # siblings, and craft is requested by both - the family only has 1
    # slot, and it's short by 2 *distinct* activities, not 3.
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9), session(archery, "A", 9)]
    sib1 = camper("Sib1", family="F1", optional=(craft, canoeing))
    sib2 = camper("Sib2", family="F1", optional=(craft, archery))

    overdemanding = find_overdemanding_families(sessions, [sib1, sib2])

    assert overdemanding == [
        FamilyOverdemand("F1", (sib1, sib2), requested_count=3, available_timeslots=1)
    ]


def test_find_overdemanding_families_not_flagged_when_requests_fit():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 11)]  # non-overlapping
    kid = camper("Kid", optional=(craft, canoeing))

    assert find_overdemanding_families(sessions, [kid]) == []


def test_find_overdemanding_families_two_members_pooling_non_overlapping_slots_can_still_fit():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    # Different times, so even though it's 2 distinct requests, the family
    # (as a whole) can fit both - one member in each, back to back.
    sessions = [session(craft, "A", 9), session(canoeing, "A", 11)]
    sib1 = camper("Sib1", family="F1", optional=(craft,))
    sib2 = camper("Sib2", family="F1", optional=(canoeing,))

    assert find_overdemanding_families(sessions, [sib1, sib2]) == []


def test_find_overdemanding_families_skips_families_with_no_requests():
    craft = activity("Craft")
    sessions = [session(craft, "A", 9)]
    bystander = camper("Bystander")  # no priorities or optional activities

    assert find_overdemanding_families(sessions, [bystander]) == []


def test_find_overdemanding_families_session_available_if_any_member_is_age_eligible():
    # craft is 18+ - the kid alone couldn't use it, but the adult in the
    # same family can, so it counts towards the family's pooled ceiling.
    craft = activity("Craft", min_age=18)
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 11)]  # non-overlapping
    adult = camper("Adult", family="F1", age=40, priorities=(craft,))
    kid = camper("Kid", family="F1", age=10, optional=(canoeing,))

    assert find_overdemanding_families(sessions, [adult, kid]) == []


def test_find_overdemanding_families_excludes_sessions_no_member_is_eligible_for():
    craft = activity("Craft", min_age=18)  # nobody in this family is 18+
    canoeing = activity("Canoeing")
    archery = activity("Archery")
    kid = camper("Kid", family="F1", age=10, optional=(canoeing, archery))

    # canoeing and archery overlap for the kid, so there's really only 1
    # available slot - craft's 3 non-overlapping sessions must not count
    # towards the family's ceiling, since nobody in it is age-eligible.
    sessions = [
        session(canoeing, "A", 9),
        session(archery, "A", 9),
        session(craft, "A", 12),
        session(craft, "B", 14),
        session(craft, "C", 16),
    ]

    overdemanding = find_overdemanding_families(sessions, [kid])

    assert overdemanding == [FamilyOverdemand("F1", (kid,), requested_count=2, available_timeslots=1)]


def test_find_overdemanding_families_counts_priorities_and_optional_together():
    craft = activity("Craft")
    canoeing = activity("Canoeing")
    sessions = [session(craft, "A", 9), session(canoeing, "A", 9)]  # overlapping - 1 slot max
    kid = camper("Kid", priorities=(craft,), optional=(canoeing,))

    overdemanding = find_overdemanding_families(sessions, [kid])

    assert overdemanding == [FamilyOverdemand("F1", (kid,), requested_count=2, available_timeslots=1)]
