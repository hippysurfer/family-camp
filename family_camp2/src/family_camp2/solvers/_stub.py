"""Temporary stub solver registration - replaced in Step 19.

Registered a trivial (always-empty) solver under both "cp_sat" and
"annealing" names so the CLI was fully exercisable end-to-end (Step 11)
before either real solver existed. Step 15 imported the real cp_sat module
(overwriting this file's "cp_sat" registration, see solvers/__init__.py);
Step 19 does the same for "annealing". Once both are replaced, this module
and its import in solvers/__init__.py should be removed.

Accepts and ignores arbitrary constructor kwargs (e.g.
``time_limit_seconds``, ``random_seed``) so it tolerates being constructed
the same way real solvers are during this transitional period.
"""

from __future__ import annotations

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.solvers.base import SolveResult
from family_camp2.solvers.registry import register
from family_camp2.validation.validator import validate


class _StubSolver:
    def __init__(self, **kwargs):
        pass

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
