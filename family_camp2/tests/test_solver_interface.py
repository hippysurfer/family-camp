import pytest

from family_camp2.config import EngineConfig
from family_camp2.solvers.base import SolveResult
from family_camp2.solvers.registry import SOLVERS, get_solver, register
from family_camp2.validation.report import ValidationReport

from fixtures import FakeSolver


def test_register_and_get_solver_round_trips():
    register("fake-for-test")(FakeSolver)
    solver = get_solver("fake-for-test")
    assert isinstance(solver, FakeSolver)
    del SOLVERS["fake-for-test"]  # keep the global registry clean for other tests


def test_get_unregistered_solver_raises_clear_error():
    with pytest.raises(KeyError, match="bogus-solver-name"):
        get_solver("bogus-solver-name")


def test_fake_solver_solve_returns_real_validation_report():
    solver = FakeSolver()
    result = solver.solve(activities=[], sessions=[], campers=[], config=EngineConfig())

    assert isinstance(result, SolveResult)
    assert isinstance(result.report, ValidationReport)
    assert result.report.is_feasible is True
