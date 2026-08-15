"""The constraint-rule contract (REQUIREMENTS.md §3.5/§4.10, FR-90).

A **Tier A** rule - everything this phase implements (FR-96), per OQ-22 -
is one that reduces to a per-(camper, session) predicate: "would this
session violate the rule for this camper?" That's deliberately the same
shape as the eligibility check that already makes Class 1 structurally
guaranteed in both solvers (``_is_eligible`` in ``solvers/cp_sat.py`` and
``solvers/annealing/moves.py``) - a hard Tier A constraint plugs into
that existing mechanism directly, with no new solver-specific modeling
per rule (FR-94). A soft one is scored the same way Class 2 already
scores ``missing_priority``/etc. (FR-95).

Tier B rules (relational, e.g. "must always be with camper X"; aggregate,
e.g. "no more than 2 activities per day") don't fit this single-session
shape and are an explicitly deferred extension (IMPLEMENTATION_PLAN.md
§6) - the registry (``registry.py``) doesn't prevent registering one, but
nothing here helps enforce it automatically the way Tier A rules are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from family_camp2.domain import Camper, Session

__all__ = ["ConstraintRule", "ConstraintInstance", "Severity"]

Severity = Literal["hard", "soft"]


class ConstraintRule(Protocol):
    """A named, parameterised rule. Instances are built by
    ``registry.get_constraint_class(name)(*args, **kwargs)`` from a
    parsed spreadsheet expression (``parser.py``) - so a concrete rule is
    typically a frozen dataclass whose fields are exactly the expression's
    arguments (e.g. ``NoActivitiesOnDay(day=2)``).
    """

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        """True if assigning ``camper`` to ``session`` would violate this
        rule. ``all_sessions`` is the full camp session list - most rules
        (time-of-day, activity-name) ignore it, but a rule like "day N"
        needs the whole list to know which calendar date *is* day N
        (REQUIREMENTS.md FR-3: no fixed camp length is assumed, so "day N"
        is derived from the distinct dates actually present, not a fixed
        date)."""
        ...


@dataclass(frozen=True)
class ConstraintInstance:
    """A rule bound to its already-resolved targets (``parser.resolve_target``)
    and severity (§3.5's "Target"/"Severity" fields) - what the rest of the
    engine actually consumes. ``targets`` already carries each camper's own
    ``family_id``/``name``, so no separate identifier is kept here; ``note``
    is retained for diagnostics/reporting only, never interpreted."""

    targets: tuple[Camper, ...]
    rule: ConstraintRule
    severity: Severity
    note: str = ""
