"""A name -> ConstraintRule-class registry, structurally identical to
``solvers/registry.py`` - the spreadsheet expression's function name
(``parser.py``) is looked up here to find which class to instantiate.
"""

from __future__ import annotations

from family_camp2.constraints.base import ConstraintRule

__all__ = ["register", "get_constraint_class", "CONSTRAINT_RULES"]

CONSTRAINT_RULES: dict[str, type[ConstraintRule]] = {}


def register(name: str):
    def decorator(cls: type[ConstraintRule]) -> type[ConstraintRule]:
        CONSTRAINT_RULES[name] = cls
        return cls

    return decorator


def get_constraint_class(name: str) -> type[ConstraintRule]:
    try:
        return CONSTRAINT_RULES[name]
    except KeyError:
        raise KeyError(
            f"No constraint rule registered under name {name!r}. Known rules: {sorted(CONSTRAINT_RULES)}"
        ) from None
