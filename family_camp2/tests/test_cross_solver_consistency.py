"""Empirically validates the comparative claim in DESIGN_OPTIONS.md §5:
CP-SAT's Tier 0 result is provably optimal, so annealing's best-found
result can only tie or trail it, never beat it - the concrete, automated
version of the "provable vs. best-found" gap discussed in
DESIGN_OPTIONS.md §4.6.
"""

from datetime import datetime, timedelta

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.solver import AnnealingSolver
from family_camp2.solvers.cp_sat import CpSatSolver
from fixtures import generate_medium_instance, load_small_camp

DAY = datetime(2026, 8, 1, 9, 0)


def _oversubscribed_fixture():
    """Two campers who both need the same single-seat activity as a
    priority - infeasible to fully satisfy, true minimum Tier 0 is exactly
    one missing_priority violation (hand-verified, matches
    test_cp_sat_tier0.py's equivalent fixture)."""
    craft = Activity("Craft", timedelta(minutes=60), min_occupancy=1, max_occupancy=1)
    c1 = Camper(name="Kid1", family_id="F1", age=10, age_group="Cub", priorities=(craft,))
    c2 = Camper(name="Kid2", family_id="F2", age=10, age_group="Cub", priorities=(craft,))
    session = Session(activity=craft, label="A", start=DAY)
    return [craft], [session], [c1, c2]


def _annealing():
    return AnnealingSolver(num_chains=6, iterations_per_chain=800, random_seed=1)


def _assert_consistent(activities, sessions, campers, expect_feasible: bool):
    cp_sat_result = CpSatSolver().solve(activities, sessions, campers, EngineConfig())
    annealing_result = _annealing().solve(activities, sessions, campers, EngineConfig())

    assert cp_sat_result.report.class1.is_clean, cp_sat_result.report.class1
    assert annealing_result.report.class1.is_clean, annealing_result.report.class1

    assert annealing_result.report.tier0_score >= cp_sat_result.report.tier0_score

    if expect_feasible:
        assert cp_sat_result.report.tier0_score == 0
        assert annealing_result.report.tier0_score == 0


def test_consistent_on_small_camp_fixture():
    activities, sessions, campers = load_small_camp()
    _assert_consistent(activities, sessions, campers, expect_feasible=True)


def test_consistent_on_oversubscribed_fixture():
    activities, sessions, campers = _oversubscribed_fixture()
    _assert_consistent(activities, sessions, campers, expect_feasible=False)


def test_consistent_on_medium_synthetic_instance():
    activities, sessions, campers = generate_medium_instance()
    _assert_consistent(activities, sessions, campers, expect_feasible=False)
