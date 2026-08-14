"""FR-17/FR-24: CP-SAT's own family-split modeling (add_class2_indicators'
family_split/lone_adult/unaccompanied_child indicators, tier0_expr's new
weighted term) must agree with the independent validator
(validation.class2), exactly like the other Tier 0 concerns already
covered by test_cp_sat_tier0.py.
"""

from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.cp_sat import add_class2_indicators, build_model, extract_timetable, solve_phase1, tier0_expr
from family_camp2.validation.class2 import Tier0Weights, check_class2, score_tier0

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def camper(name, family, age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def _solve(activities, sessions, campers, weights=Tier0Weights()):
    model, var_index = build_model(activities, sessions, campers)
    class2_vars = add_class2_indicators(model, var_index, campers, sessions)
    objective = tier0_expr(class2_vars, weights)
    solver, v0 = solve_phase1(model, objective)
    timetable = extract_timetable(solver, var_index)
    return v0, timetable


def test_solver_avoids_an_avoidable_split():
    craft = activity("Craft", max_occ=2)  # plenty of room for both in one session
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(craft,))
    kid = camper("Kid", "F1", age=10, priorities=(craft,))
    s1 = Session(craft, "Morning", DAY)
    s2 = Session(craft, "Afternoon", DAY + timedelta(hours=5))

    v0, timetable = _solve([craft], [s1, s2], [parent, kid])

    assert v0 == 0
    # both in the same session - not split across the two available ones
    assert timetable.sessions_of(parent) == timetable.sessions_of(kid)


def test_solver_splits_only_when_capacity_forces_it_and_flags_the_lone_adult_session():
    craft = activity("Craft", max_occ=1)  # only one seat per session - can't stay together
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(craft,))
    kid = camper("Kid", "F1", age=10, priorities=(craft,))
    s1 = Session(craft, "Morning", DAY)
    s2 = Session(craft, "Afternoon", DAY + timedelta(hours=5))  # non-overlapping with s1

    weights = Tier0Weights()
    v0, timetable = _solve([craft], [s1, s2], [parent, kid], weights)

    # Forced apart (capacity 1 each) - both priorities still get met (far
    # cheaper than a missing_priority violation), so exactly one
    # family_split occurrence. Whichever session ends up adult-only is a
    # lone_adult violation; the child-only session is fine because the
    # non-overlapping adult is idle during it (the exception applies).
    assert v0 == weights.family_split + weights.family_safety

    validator_report = check_class2(timetable, [parent, kid])
    assert score_tier0(validator_report, weights) == v0
    assert len(validator_report.family_splits) == 1
    assert len(validator_report.unsupervised_splits) == 1
    assert validator_report.unsupervised_splits[0].reason == "lone_adult"


def test_solver_does_not_penalise_a_split_activity_no_child_ever_requested():
    yoga = activity("Adult Yoga", max_occ=1)  # forces a split between the two parents
    parent1 = camper("Parent1", "F1", age=40, age_group="Adult", priorities=(yoga,))
    parent2 = camper("Parent2", "F1", age=42, age_group="Adult", priorities=(yoga,))
    kid = camper("Kid", "F1", age=10)  # in the family, never requested yoga
    s1 = Session(yoga, "Morning", DAY)
    s2 = Session(yoga, "Afternoon", DAY + timedelta(hours=5))

    weights = Tier0Weights()
    v0, timetable = _solve([yoga], [s1, s2], [parent1, parent2, kid], weights)

    # Split is unavoidable (capacity 1), so it's still counted - but since
    # no child ever requested yoga, neither session is a lone_adult
    # violation (an exemption both layers must agree on).
    assert v0 == weights.family_split

    validator_report = check_class2(timetable, [parent1, parent2, kid])
    assert score_tier0(validator_report, weights) == v0
    assert validator_report.unsupervised_splits == []


def test_phase1_result_agrees_with_independent_validator_on_a_properly_mixed_split():
    craft = activity("Craft", max_occ=2)
    parent = camper("Parent", "F1", age=40, age_group="Adult", priorities=(craft,))
    kid1 = camper("Kid1", "F1", age=10, priorities=(craft,))
    kid2 = camper("Kid2", "F1", age=11, priorities=(craft,))
    other_parent = camper("OtherParent", "F1", age=41, age_group="Adult", priorities=(craft,))
    s1 = Session(craft, "Morning", DAY)
    s2 = Session(craft, "Afternoon", DAY + timedelta(hours=5))
    campers = [parent, kid1, kid2, other_parent]

    weights = Tier0Weights()
    v0, timetable = _solve([craft], [s1, s2], campers, weights)

    validator_report = check_class2(timetable, campers)
    assert score_tier0(validator_report, weights) == v0
