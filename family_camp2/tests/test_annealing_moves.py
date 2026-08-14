from collections import defaultdict
from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.moves import (
    State,
    assign_family,
    fix_lone_adult_split,
    fix_unsupervised_split,
    move_family,
    remove_family,
    swap_families,
)
from family_camp2.validation.class1 import check_class1

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def camper(name, family, age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def by_family(campers):
    d = defaultdict(list)
    for c in campers:
        d[c.family_id].append(c)
    return dict(d)


def assert_class1_clean(state):
    report = check_class1(state.to_timetable())
    assert report.is_clean, report


# --- assign_family ---


def test_assign_family_adds_eligible_members():
    archery = activity("Archery", max_occ=5)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(archery,))
    kid = camper("Kid", "F1", age=10, priorities=())  # never requested archery
    session = Session(activity=archery, label="A", start=DAY)
    campers_by_family = by_family([parent, kid])

    state = State([parent, kid], [session])
    new_state = assign_family(state, "F1", session, campers_by_family)

    assert new_state is not None
    assert new_state.is_assigned(parent, session)
    assert not new_state.is_assigned(kid, session)  # not requested, correctly excluded
    assert_class1_clean(new_state)
    assert not state.is_assigned(parent, session)  # original untouched


def test_assign_family_rejected_when_capacity_exceeded():
    craft = activity("Craft", max_occ=1)
    c1 = camper("Kid1", "F1", priorities=(craft,))
    c2 = camper("Kid2", "F1", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)
    campers_by_family = by_family([c1, c2])

    state = State([c1, c2], [session])
    result = assign_family(state, "F1", session, campers_by_family)

    assert result is None  # both eligible, but only room for one


def test_assign_family_rejected_when_no_one_eligible():
    climbing = activity("Climbing", min_age=12)
    young = camper("Young", "F1", age=8, priorities=(climbing,))
    session = Session(activity=climbing, label="A", start=DAY)
    campers_by_family = by_family([young])

    state = State([young], [session])
    result = assign_family(state, "F1", session, campers_by_family)

    assert result is None  # age-ineligible, nobody left to add


# --- move_family ---


def test_move_family_relocates_to_parallel_session():
    craft = activity("Craft", max_occ=5)
    kid = camper("Kid", "F1", priorities=(craft,))
    morning = Session(activity=craft, label="Morning", start=DAY)
    afternoon = Session(activity=craft, label="Afternoon", start=DAY + timedelta(hours=5))
    campers_by_family = by_family([kid])

    state = State([kid], [morning, afternoon])
    state = assign_family(state, "F1", morning, campers_by_family)

    moved = move_family(state, "F1", morning, afternoon, campers_by_family)

    assert moved is not None
    assert not moved.is_assigned(kid, morning)
    assert moved.is_assigned(kid, afternoon)
    assert_class1_clean(moved)


def test_move_family_rejected_across_different_activities():
    craft = activity("Craft")
    archery = activity("Archery")
    kid = camper("Kid", "F1", priorities=(craft, archery))
    craft_session = Session(activity=craft, label="A", start=DAY)
    archery_session = Session(activity=archery, label="A", start=DAY + timedelta(hours=5))
    campers_by_family = by_family([kid])

    state = State([kid], [craft_session, archery_session])
    state = assign_family(state, "F1", craft_session, campers_by_family)

    result = move_family(state, "F1", craft_session, archery_session, campers_by_family)
    assert result is None


def test_move_family_rejected_when_it_would_double_book():
    craft = activity("Craft", max_occ=5)
    archery = activity("Archery", max_occ=5)
    kid = camper("Kid", "F1", priorities=(craft, archery))
    morning = Session(activity=craft, label="Morning", start=DAY)
    afternoon = Session(activity=craft, label="Afternoon", start=DAY + timedelta(hours=1))  # overlaps nothing yet
    clashing_archery = Session(activity=archery, label="A", start=DAY + timedelta(hours=1))  # overlaps afternoon craft
    campers_by_family = by_family([kid])

    state = State([kid], [morning, afternoon, clashing_archery])
    state = assign_family(state, "F1", morning, campers_by_family)
    state = assign_family(state, "F1", clashing_archery, campers_by_family)

    result = move_family(state, "F1", morning, afternoon, campers_by_family)
    assert result is None  # afternoon craft overlaps the already-assigned archery session


# --- swap_families ---


def test_swap_families_exchanges_sessions():
    craft = activity("Craft", max_occ=5)
    archery = activity("Archery", max_occ=5)
    kid_a = camper("KidA", "FA", priorities=(craft, archery))
    kid_b = camper("KidB", "FB", priorities=(craft, archery))
    craft_session = Session(activity=craft, label="A", start=DAY)
    archery_session = Session(activity=archery, label="A", start=DAY + timedelta(hours=5))
    campers_by_family = by_family([kid_a, kid_b])

    state = State([kid_a, kid_b], [craft_session, archery_session])
    state = assign_family(state, "FA", craft_session, campers_by_family)
    state = assign_family(state, "FB", archery_session, campers_by_family)

    swapped = swap_families(state, "FA", craft_session, "FB", archery_session, campers_by_family)

    assert swapped is not None
    assert swapped.is_assigned(kid_a, archery_session)
    assert swapped.is_assigned(kid_b, craft_session)
    assert_class1_clean(swapped)


def test_swap_families_rejected_when_not_eligible_for_new_activity():
    craft = activity("Craft", max_occ=5)
    archery = activity("Archery", max_occ=5)
    kid_a = camper("KidA", "FA", priorities=(craft,))  # never wants archery
    kid_b = camper("KidB", "FB", priorities=(archery,))
    craft_session = Session(activity=craft, label="A", start=DAY)
    archery_session = Session(activity=archery, label="A", start=DAY + timedelta(hours=5))
    campers_by_family = by_family([kid_a, kid_b])

    state = State([kid_a, kid_b], [craft_session, archery_session])
    state = assign_family(state, "FA", craft_session, campers_by_family)
    state = assign_family(state, "FB", archery_session, campers_by_family)

    result = swap_families(state, "FA", craft_session, "FB", archery_session, campers_by_family)
    assert result is None


def test_swap_families_rejected_when_asymmetric_group_sizes_would_overflow_capacity():
    """Regression test: swap_families previously computed the room freed up
    in session_a using the *incoming* group's size instead of the group
    vacating it, which failed to reject a swap that would overflow
    session_a's capacity whenever the incoming family (from session_b) was
    larger than the outgoing one."""
    activity_a = activity("A", max_occ=1)
    activity_b = activity("B", max_occ=2)
    solo = camper("Solo", "FA", priorities=(activity_a, activity_b))
    pair1 = camper("Pair1", "FB", priorities=(activity_a, activity_b))
    pair2 = camper("Pair2", "FB", priorities=(activity_a, activity_b))
    session_a = Session(activity=activity_a, label="A", start=DAY)
    session_b = Session(activity=activity_b, label="B", start=DAY + timedelta(hours=5))
    campers_by_family = by_family([solo, pair1, pair2])

    state = State([solo, pair1, pair2], [session_a, session_b])
    state._add(solo, session_a)  # session_a: 1/1 (full)
    state._add(pair1, session_b)
    state._add(pair2, session_b)  # session_b: 2/2 (full)

    result = swap_families(state, "FA", session_a, "FB", session_b, campers_by_family)

    assert result is None  # session_a (capacity 1) can't hold both members of FB


# --- remove_family ---


def test_remove_family_always_succeeds_and_stays_clean():
    craft = activity("Craft", max_occ=5)
    kid = camper("Kid", "F1", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)
    campers_by_family = by_family([kid])

    state = State([kid], [session])
    state = assign_family(state, "F1", session, campers_by_family)
    assert state.is_assigned(kid, session)

    removed = remove_family(state, "F1", session, campers_by_family)
    assert not removed.is_assigned(kid, session)
    assert_class1_clean(removed)


# --- fix_unsupervised_split ---


def test_fix_unsupervised_split_adds_an_available_adult():
    swimming = activity("Swimming", max_occ=5)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", "F1", age=10, priorities=(swimming,))
    session = Session(activity=swimming, label="A", start=DAY)
    campers_by_family = by_family([parent, kid])

    state = State([parent, kid], [session])
    state = assign_family(state, "F1", session, campers_by_family)  # adds both, since both eligible+room

    # Force the "kid only" scenario by removing the parent again, then fixing it.
    state = remove_family(state, "F1", session, campers_by_family)
    state._add(kid, session)

    fixed = fix_unsupervised_split(state, "F1", session, campers_by_family)

    assert fixed is not None
    assert fixed.is_assigned(parent, session)
    assert_class1_clean(fixed)


def test_fix_unsupervised_split_rejected_when_no_adult_available():
    swimming = activity("Swimming", max_occ=5)
    kid = camper("Kid", "F1", age=10, priorities=(swimming,))
    session = Session(activity=swimming, label="A", start=DAY)
    campers_by_family = by_family([kid])

    state = State([kid], [session])
    state._add(kid, session)

    result = fix_unsupervised_split(state, "F1", session, campers_by_family)
    assert result is None


def test_fix_unsupervised_split_rejected_when_session_full():
    swimming = activity("Swimming", max_occ=1)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", "F1", age=10, priorities=(swimming,))
    session = Session(activity=swimming, label="A", start=DAY)
    campers_by_family = by_family([parent, kid])

    state = State([parent, kid], [session])
    state._add(kid, session)  # session already at capacity 1

    result = fix_unsupervised_split(state, "F1", session, campers_by_family)
    assert result is None


# --- fix_lone_adult_split ---


def test_fix_lone_adult_split_adds_an_available_child():
    swimming = activity("Swimming", max_occ=5)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", "F1", age=10, priorities=(swimming,))
    session = Session(activity=swimming, label="A", start=DAY)
    campers_by_family = by_family([parent, kid])

    state = State([parent, kid], [session])
    state._add(parent, session)  # adult-only session - nothing to supervise

    fixed = fix_lone_adult_split(state, "F1", session, campers_by_family)

    assert fixed is not None
    assert fixed.is_assigned(kid, session)
    assert_class1_clean(fixed)


def test_fix_lone_adult_split_rejected_when_no_child_available():
    swimming = activity("Swimming", max_occ=5)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(swimming,))
    campers_by_family = by_family([parent])
    session = Session(activity=swimming, label="A", start=DAY)

    state = State([parent], [session])
    state._add(parent, session)

    result = fix_lone_adult_split(state, "F1", session, campers_by_family)
    assert result is None


def test_fix_lone_adult_split_rejected_when_session_full():
    swimming = activity("Swimming", max_occ=1)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(swimming,))
    kid = camper("Kid", "F1", age=10, priorities=(swimming,))
    session = Session(activity=swimming, label="A", start=DAY)
    campers_by_family = by_family([parent, kid])

    state = State([parent, kid], [session])
    state._add(parent, session)  # session already at capacity 1

    result = fix_lone_adult_split(state, "F1", session, campers_by_family)
    assert result is None
