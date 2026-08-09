"""Shared test-only fixtures and helpers (not part of the installed package)."""

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.solvers.base import SolveResult
from family_camp2.validation.validator import validate


class FakeSolver:
    """A trivial Solver that never assigns anyone to anything.

    Exists purely to prove the Solver interface, registry, and (later) CLI
    wiring work end-to-end before either real solver (CP-SAT, annealing) is
    built.
    """

    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config,
    ) -> SolveResult:
        timetable = Timetable()
        compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)
        report = validate(
            timetable,
            campers,
            sessions,
            tier0_weights=config.tier0_weights,
            compulsory=compulsory,
        )
        return SolveResult(timetable=timetable, report=report, diagnostics={"solver": "fake"})
