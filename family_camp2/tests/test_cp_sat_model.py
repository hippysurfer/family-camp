from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.cp_sat import build_model, extract_timetable
from family_camp2.validation.class1 import check_class1
from fixtures import load_small_camp

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def _solve_maximally(model: cp_model.CpModel, var_index) -> cp_model.CpSolver:
    """Force as dense a feasible solution as possible, to stress-test the
    structural constraints (a solve with no objective could trivially
    "succeed" by assigning nobody, which wouldn't exercise them)."""
    model.Maximize(sum(var_index.by_pair.values()))
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return solver


def test_model_builds_for_small_camp_fixture():
    activities, sessions, campers = load_small_camp()
    model, var_index = build_model(activities, sessions, campers)
    assert isinstance(model, cp_model.CpModel)
    assert len(var_index.by_pair) > 0


def test_no_variable_for_unrequested_activity():
    swimming = activity("Swimming")
    craft = activity("Craft")
    c = camper("Kid", priorities=(craft,))  # never asked for swimming
    s = Session(activity=swimming, label="A", start=DAY)

    _, var_index = build_model([swimming, craft], [s], [c])
    assert (c, s) not in var_index


def test_no_variable_for_age_ineligible_camper():
    climbing = activity("Climbing", min_age=12)
    young = camper("Young", age=10, priorities=(climbing,))
    old_enough = camper("OldEnough", age=12, priorities=(climbing,))
    s = Session(activity=climbing, label="A", start=DAY)

    _, var_index = build_model([climbing], [s], [young, old_enough])
    assert (young, s) not in var_index
    assert (old_enough, s) in var_index


def test_maximal_solution_never_violates_class1():
    activities, sessions, campers = load_small_camp()
    model, var_index = build_model(activities, sessions, campers)

    solver = _solve_maximally(model, var_index)
    timetable = extract_timetable(solver, var_index)

    report = check_class1(timetable)
    assert report.is_clean, report


def test_maximal_solution_respects_no_duplicate_activity_even_with_two_sessions_of_same_activity():
    archery = activity("Archery", max_occ=5)
    kid = camper("Kid", priorities=(archery,))
    morning = Session(activity=archery, label="Morning", start=DAY)
    afternoon = Session(activity=archery, label="Afternoon", start=DAY + timedelta(hours=5))

    model, var_index = build_model([archery], [morning, afternoon], [kid])
    solver = _solve_maximally(model, var_index)
    timetable = extract_timetable(solver, var_index)

    assert len(timetable.sessions_of(kid)) == 1  # not both, despite being eligible for both
