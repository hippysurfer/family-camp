"""A name -> Solver-class registry, so the CLI can pick a solver by string."""

from __future__ import annotations

from family_camp2.solvers.base import Solver

__all__ = ["register", "get_solver", "SOLVERS"]

SOLVERS: dict[str, type[Solver]] = {}


def register(name: str):
    def decorator(cls: type[Solver]) -> type[Solver]:
        SOLVERS[name] = cls
        return cls

    return decorator


def get_solver(name: str) -> Solver:
    try:
        cls = SOLVERS[name]
    except KeyError:
        raise KeyError(f"No solver registered under name {name!r}. Known solvers: {sorted(SOLVERS)}") from None
    return cls()
