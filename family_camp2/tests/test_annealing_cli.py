import time

from family_camp2 import cli
from family_camp2.config import EngineConfig
from family_camp2.solvers.annealing.solver import AnnealingSolver
from family_camp2.validation.class1 import check_class1
from fixtures import SMALL_CAMP_JSON, generate_medium_instance


def test_cli_solves_small_camp_fully_feasibly_with_annealing(capsys):
    exit_code = cli.main([
        "solve", "--solver", "annealing", "--data", str(SMALL_CAMP_JSON),
        "--num-chains", "4", "--iterations-per-chain", "500", "--seed", "1",
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Feasible: True" in out
    assert "Tier 0 (violation) score: 0" in out


def test_annealing_solves_medium_synthetic_instance_quickly_with_zero_class1_violations():
    activities, sessions, campers = generate_medium_instance()

    start = time.monotonic()
    result = AnnealingSolver(num_chains=4, iterations_per_chain=1000, random_seed=1).solve(
        activities, sessions, campers, EngineConfig()
    )
    elapsed = time.monotonic() - start

    assert elapsed < 30
    assert check_class1(result.timetable).is_clean
