import pytest

from family_camp2.cli import build_parser


def test_accepts_cp_sat_solver():
    args = build_parser().parse_args(["solve", "--solver", "cp_sat", "--data", "dummy.json"])
    assert args.solver == "cp_sat"


def test_accepts_annealing_solver():
    args = build_parser().parse_args(["solve", "--solver", "annealing", "--data", "dummy.json"])
    assert args.solver == "annealing"


def test_rejects_unknown_solver():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["solve", "--solver", "bogus", "--data", "dummy.json"])


def test_solver_defaults_to_cp_sat():
    args = build_parser().parse_args(["solve", "--data", "dummy.json"])
    assert args.solver == "cp_sat"


def test_requires_a_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--data", "dummy.json"])


def test_revalidate_requires_schedule_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["revalidate", "--data", "dummy.json"])


def test_revalidate_accepts_schedule_argument():
    args = build_parser().parse_args(["revalidate", "--data", "dummy.json", "schedule.csv"])
    assert str(args.schedule) == "schedule.csv"


def test_fetch_requires_a_url_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["fetch"])


def test_fetch_accepts_a_url_argument():
    args = build_parser().parse_args(["fetch", "https://docs.google.com/spreadsheets/d/abc123"])
    assert args.url == "https://docs.google.com/spreadsheets/d/abc123"


def test_annealing_tuning_flags_default_to_the_solver_classs_own_defaults():
    args = build_parser().parse_args(["solve", "--data", "dummy.json"])
    assert args.num_chains == 8
    assert args.iterations_per_chain == 2000


def test_time_limit_and_seed_default_to_none():
    args = build_parser().parse_args(["solve", "--data", "dummy.json"])
    assert args.time_limit is None
    assert args.seed is None
