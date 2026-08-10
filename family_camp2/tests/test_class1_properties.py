"""Property-based hardening for Class 1 (DESIGN_OPTIONS.md §4.5 recommendation).

Strengthens confidence in the two structural-invariant claims the whole
design leans on beyond the hand-picked example fixtures used elsewhere:
that neither the annealing move layer (moves.py) nor the CP-SAT model's
variable domain (cp_sat.py) can ever produce a Class 1 violation, across a
wide variety of randomly generated small camp instances - not just the
specific ones a human thought to write a test for.
"""

import random
from collections import defaultdict
from datetime import datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from ortools.sat.python import cp_model

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.moves import State
from family_camp2.solvers.annealing.solver import _propose_move
from family_camp2.solvers.cp_sat import build_model, extract_timetable
from family_camp2.validation.class1 import check_class1

DAY = datetime(2026, 8, 1, 9, 0)


@st.composite
def small_camp(draw, max_activities=3, max_sessions=4, max_campers=5):
    num_activities = draw(st.integers(min_value=1, max_value=max_activities))
    activities = []
    for i in range(num_activities):
        min_occ = draw(st.integers(min_value=1, max_value=2))
        max_occ = draw(st.integers(min_value=min_occ, max_value=min_occ + 3))
        min_age = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=15)))
        activities.append(
            Activity(name=f"Act{i}", duration=timedelta(minutes=60), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)
        )

    num_sessions = draw(st.integers(min_value=1, max_value=max_sessions))
    sessions = []
    for i in range(num_sessions):
        activity = draw(st.sampled_from(activities))
        hour = draw(st.integers(min_value=0, max_value=10))
        sessions.append(Session(activity=activity, label=f"S{i}", start=DAY + timedelta(hours=hour)))

    num_campers = draw(st.integers(min_value=1, max_value=max_campers))
    campers = []
    for i in range(num_campers):
        family_id = f"F{draw(st.integers(min_value=0, max_value=2))}"
        age = draw(st.integers(min_value=5, max_value=45))
        chosen = draw(st.lists(st.sampled_from(activities), min_size=0, max_size=num_activities, unique=True))
        split = draw(st.integers(min_value=0, max_value=len(chosen)))
        priorities = tuple(chosen[:split])
        optional = tuple(chosen[split:])
        campers.append(
            Camper(
                name=f"C{i}",
                family_id=family_id,
                age=age,
                age_group="Adult" if age >= 18 else "Cub",
                priorities=priorities,
                optional=optional,
            )
        )

    return activities, sessions, campers


@given(data=small_camp(), move_seed=st.integers(min_value=0, max_value=2**31 - 1), num_moves=st.integers(min_value=1, max_value=25))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_annealing_moves_never_produce_a_class1_violation(data, move_seed, num_moves):
    activities, sessions, campers = data
    campers_by_family: dict[str, list[Camper]] = defaultdict(list)
    for c in campers:
        campers_by_family[c.family_id].append(c)
    campers_by_family = dict(campers_by_family)

    sessions_by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        sessions_by_activity[s.activity].append(s)

    rng = random.Random(move_seed)
    families = sorted(campers_by_family)
    state = State(campers, sessions)

    for _ in range(num_moves):
        candidate = _propose_move(rng, state, families, sessions, sessions_by_activity, campers_by_family)
        if candidate is not None:
            state = candidate
        report = check_class1(state.to_timetable())
        assert report.is_clean, report


@given(data=small_camp())
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_cp_sat_maximal_solution_never_produces_a_class1_violation(data):
    activities, sessions, campers = data
    model, var_index = build_model(activities, sessions, campers)

    objective = sum(var_index.by_pair.values()) if var_index.by_pair else 0
    model.Maximize(objective)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    timetable = extract_timetable(solver, var_index)
    report = check_class1(timetable)
    assert report.is_clean, report
