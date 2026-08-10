from collections import defaultdict

from family_camp2.solvers.annealing.moves import State
from family_camp2.solvers.annealing.scoring import compare, score
from family_camp2.solvers.annealing.solver import CoolingSchedule, run_chain
from family_camp2.validation.class1 import check_class1
from family_camp2.validation.class2 import Tier0Weights
from fixtures import load_small_camp


def _campers_by_family(campers):
    d = defaultdict(list)
    for c in campers:
        d[c.family_id].append(c)
    return dict(d)


def _run(campers, sessions, campers_by_family, seed, iterations=200):
    initial = State(campers, sessions)
    cooling = CoolingSchedule(initial_temperature=10.0, cooling_rate=0.98)
    return run_chain(
        initial,
        campers,
        sessions,
        campers_by_family,
        tier0_weights=Tier0Weights(),
        compulsory=frozenset(),
        cooling=cooling,
        seed=seed,
        iterations=iterations,
    )


def test_run_chain_is_reproducible_given_the_same_seed():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    result1 = _run(campers, sessions, campers_by_family, seed=123)
    result2 = _run(campers, sessions, campers_by_family, seed=123)

    assert result1.to_timetable() == result2.to_timetable()


def test_run_chain_never_makes_class1_unclean():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    result = _run(campers, sessions, campers_by_family, seed=7, iterations=300)

    report = check_class1(result.to_timetable())
    assert report.is_clean, report


def test_run_chain_never_ends_up_worse_than_the_empty_starting_state():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    weights = Tier0Weights()
    initial_score = score(State(campers, sessions), campers, sessions, weights, frozenset())

    result = _run(campers, sessions, campers_by_family, seed=99, iterations=300)
    result_score = score(result, campers, sessions, weights, frozenset())

    assert compare(result_score, initial_score) <= 0  # best-seen is never worse than doing nothing
