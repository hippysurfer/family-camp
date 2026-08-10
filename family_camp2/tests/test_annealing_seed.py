import random
from collections import defaultdict

from family_camp2.solvers.annealing.seed import greedy_seed
from family_camp2.validation.class1 import check_class1
from fixtures import load_small_camp


def _campers_by_family(campers):
    d = defaultdict(list)
    for c in campers:
        d[c.family_id].append(c)
    return dict(d)


def test_greedy_seed_is_class1_clean():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    state = greedy_seed(activities, sessions, campers, campers_by_family, random.Random(1))

    report = check_class1(state.to_timetable())
    assert report.is_clean, report


def test_greedy_seed_makes_some_assignments():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    state = greedy_seed(activities, sessions, campers, campers_by_family, random.Random(1))

    assert len(state.to_timetable()) > 0


def test_greedy_seed_is_reproducible_given_the_same_rng_seed():
    activities, sessions, campers = load_small_camp()
    campers_by_family = _campers_by_family(campers)

    state1 = greedy_seed(activities, sessions, campers, campers_by_family, random.Random(42))
    state2 = greedy_seed(activities, sessions, campers, campers_by_family, random.Random(42))

    assert state1.to_timetable() == state2.to_timetable()
