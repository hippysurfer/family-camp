from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.cp_sat import add_class2_indicators, build_model, extract_timetable, solve_phase1, tier0_expr
from family_camp2.validation.class2 import Tier0Weights, check_class2, score_tier0

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def camper(name, family, age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_phase1_finds_the_hand_verified_minimum_for_an_oversubscribed_activity():
    # Only one seat, two campers who both need it as a priority - exactly
    # one of them must end up with a missing_priority violation, no matter
    # what the solver does. The true minimum Tier 0 score is therefore
    # exactly 1 * weights.missing_priority.
    craft = activity("Craft", max_occ=1)
    c1 = camper("Kid1", "F1", priorities=(craft,))
    c2 = camper("Kid2", "F2", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)

    model, var_index = build_model([craft], [session], [c1, c2])
    class2_vars = add_class2_indicators(model, var_index, [c1, c2], [session])
    weights = Tier0Weights()
    objective = tier0_expr(class2_vars, weights)

    solver, v0 = solve_phase1(model, objective)

    assert v0 == 1 * weights.missing_priority


def test_phase1_result_agrees_with_independent_validator():
    """The two independent layers - the solver's own objective value, and
    the shared validator scoring the extracted Timetable from scratch -
    must agree (DESIGN_OPTIONS.md §2.4/§3.6)."""
    craft = activity("Craft", max_occ=1)
    c1 = camper("Kid1", "F1", priorities=(craft,))
    c2 = camper("Kid2", "F2", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)

    model, var_index = build_model([craft], [session], [c1, c2])
    class2_vars = add_class2_indicators(model, var_index, [c1, c2], [session])
    weights = Tier0Weights()
    objective = tier0_expr(class2_vars, weights)

    solver, v0 = solve_phase1(model, objective)
    timetable = extract_timetable(solver, var_index)

    validator_report = check_class2(timetable, [c1, c2])
    validator_score = score_tier0(validator_report, weights)

    assert validator_score == v0
    assert len(validator_report.missing_priorities) == 1


def test_phase1_is_zero_when_fully_feasible():
    craft = activity("Craft", max_occ=2)
    c1 = camper("Kid1", "F1", priorities=(craft,))
    c2 = camper("Kid2", "F2", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)

    model, var_index = build_model([craft], [session], [c1, c2])
    class2_vars = add_class2_indicators(model, var_index, [c1, c2], [session])
    objective = tier0_expr(class2_vars, Tier0Weights())

    _, v0 = solve_phase1(model, objective)
    assert v0 == 0
