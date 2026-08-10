from family_camp2.config import EngineConfig
from family_camp2.solvers.annealing.solver import AnnealingSolver
from family_camp2.validation.class1 import check_class1
from fixtures import load_small_camp


def _small_solver(**overrides):
    kwargs = dict(num_chains=3, iterations_per_chain=150, random_seed=1)
    kwargs.update(overrides)
    return AnnealingSolver(**kwargs)


def test_solve_returns_class1_clean_result_on_small_camp():
    activities, sessions, campers = load_small_camp()

    result = _small_solver().solve(activities, sessions, campers, EngineConfig())

    assert check_class1(result.timetable).is_clean
    assert result.report.class1.is_clean


def test_solve_is_reproducible_given_the_same_seed():
    activities, sessions, campers = load_small_camp()

    result1 = _small_solver().solve(activities, sessions, campers, EngineConfig())
    result2 = _small_solver().solve(activities, sessions, campers, EngineConfig())

    assert result1.timetable == result2.timetable


def test_solve_result_matches_the_best_individual_chain():
    """run_restarts picks the argmin across chains, so the validated
    report's tier0_score should exactly match the best chain's own score -
    proving the aggregation-and-reporting pipeline is consistent, not just
    "no worse than"."""
    activities, sessions, campers = load_small_camp()

    result = _small_solver().solve(activities, sessions, campers, EngineConfig())

    chain_scores = result.diagnostics["chain_scores"]
    best_chain_score = min(chain_scores)
    assert result.report.tier0_score == best_chain_score[0]
    assert result.report.tier0_score <= min(s[0] for s in chain_scores)  # sanity: still the smallest tier0 seen
