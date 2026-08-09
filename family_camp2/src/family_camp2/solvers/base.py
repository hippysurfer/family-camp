"""The common shape every solver (CP-SAT, annealing, or a future one) implements.

DESIGN_OPTIONS.md §2 deliberately keeps this interface thin: a solver's
only job is to search for a good assignment. Deciding whether it's
*correct* and how good it is belongs entirely to
family_camp2.validation.validator.validate - not to the solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.report import ValidationReport

__all__ = ["SolveResult", "Solver"]


@dataclass
class SolveResult:
    timetable: Timetable
    report: ValidationReport
    diagnostics: dict[str, Any] = field(default_factory=dict)


class Solver(Protocol):
    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config: EngineConfig,
    ) -> SolveResult: ...
