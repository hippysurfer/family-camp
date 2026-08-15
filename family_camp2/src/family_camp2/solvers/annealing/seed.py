"""Design B: a constructive starting point for each annealing chain.

The spirit of the old system's ``gen_seed_individual`` (DESIGN.md §2.4),
rewritten from scratch against the new State/move primitives: walk every
session, and for each family that wants that session's activity, admit
them with a weighted coin-flip (more likely if it's a priority for someone
in the family, less likely if only optional) - biasing the starting point
towards a reasonably good state without needing to be valid or complete,
since the annealing search (solver.py) repairs and improves it from there.
"""

from __future__ import annotations

import random

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.moves import State, assign_family

__all__ = ["greedy_seed"]

_PRIORITY_ADMIT_PROBABILITY = 0.75
_OPTIONAL_ADMIT_PROBABILITY = 0.25


def greedy_seed(
    activities: list[Activity],
    sessions: list[Session],
    campers: list[Camper],
    campers_by_family: dict[str, list[Camper]],
    rng: random.Random,
    constraints: list[ConstraintInstance] = (),
) -> State:
    state = State(campers, sessions, constraints)
    families = sorted(campers_by_family)

    for session in sessions:
        shuffled_families = list(families)
        rng.shuffle(shuffled_families)

        for family_id in shuffled_families:
            members = campers_by_family[family_id]
            is_priority = any(session.activity in c.priorities for c in members)
            is_optional = any(session.activity in c.optional for c in members)
            if not (is_priority or is_optional):
                continue

            probability = _PRIORITY_ADMIT_PROBABILITY if is_priority else _OPTIONAL_ADMIT_PROBABILITY
            if rng.random() >= probability:
                continue

            new_state = assign_family(state, family_id, session, campers_by_family)
            if new_state is not None:
                state = new_state

    return state
