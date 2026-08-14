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


def test_requires_solver_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["solve", "--data", "dummy.json"])


def test_requires_a_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--data", "dummy.json"])


def test_revalidate_requires_schedule_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["revalidate", "--data", "dummy.json"])


def test_revalidate_accepts_schedule_argument():
    args = build_parser().parse_args(["revalidate", "--data", "dummy.json", "--schedule", "schedule.csv"])
    assert str(args.schedule) == "schedule.csv"
