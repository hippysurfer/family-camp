"""FR-95: soft custom-constraint violations (REQUIREMENTS.md §3.5/§4.10) -
the same demand-driven, best-effort treatment Class 2 already gives
``missing_priority``/``family_split``/etc. Hard constraints need no
equivalent check here: they're structurally guaranteed by eligibility
filtering (``constraints.base.hard_rules_by_camper``, consumed by both
solvers' ``_is_eligible``), so a hard violation is never actually
assignable in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.domain import Camper, Session, Timetable

__all__ = ["CustomConstraintViolation", "find_custom_constraint_violations"]


@dataclass(frozen=True)
class CustomConstraintViolation:
    camper: Camper
    session: Session
    constraint: ConstraintInstance


def find_custom_constraint_violations(
    timetable: Timetable, sessions: list[Session], constraints: list[ConstraintInstance]
) -> list[CustomConstraintViolation]:
    violations: list[CustomConstraintViolation] = []
    for instance in constraints:
        if instance.severity != "soft":
            continue
        for camper in instance.targets:
            for session in timetable.sessions_of(camper):
                if instance.rule.forbids(camper, session, sessions):
                    violations.append(CustomConstraintViolation(camper, session, instance))
    return violations
