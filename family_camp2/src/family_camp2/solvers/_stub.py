"""Temporary stub solver registrations - replaced in Steps 15 and 19.

Registers a trivial (always-empty) solver under both "cp_sat" and
"annealing" names so the CLI is fully exercisable end-to-end (Step 11)
before either real solver exists. Step 15 imports the real cp_sat module
(overwriting this file's "cp_sat" registration); Step 19 does the same for
"annealing". Once both are replaced, this module and its import in
solvers/__init__.py are removed.
"""

from __future__ import annotations

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.solvers.base import SolveResult
from family_camp2.solvers.registry import register
from family_camp2.validation.validator import validate


class _StubSolver:
    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config: EngineConfig,
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
        return SolveResult(timetable=timetable, report=report, diagnostics={"solver": "stub"})


register("cp_sat")(_StubSolver)
register("annealing")(_StubSolver)
