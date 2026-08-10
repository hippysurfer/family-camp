"""Design B: the single-chain simulated-annealing core loop.

See DESIGN_OPTIONS.md §4.1. Step 17 (this file, for now) provides one
evolving chain; Step 18 adds a constructive greedy seed and multi-chain
parallel restarts on top of this, plus the full ``AnnealingSolver``.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.moves import (
    State,
    assign_family,
    fix_unsupervised_split,
    move_family,
    remove_family,
    swap_families,
)
from family_camp2.solvers.annealing.scoring import Score, acceptance_probability, compare, score
from family_camp2.validation.class2 import Tier0Weights

__all__ = ["CoolingSchedule", "run_chain"]

_MOVE_KINDS = ("assign", "move", "swap", "remove", "fix_split")


@dataclass(frozen=True)
class CoolingSchedule:
    initial_temperature: float = 100.0
    cooling_rate: float = 0.995  # multiplicative decay applied once per iteration


def _sessions_of_family(state: State, family_id: str, campers_by_family: dict[str, list[Camper]]) -> list[Session]:
    members = campers_by_family.get(family_id, [])
    return [s for c in members for s in state.assigned_sessions[c]]


def _propose_move(
    rng: random.Random,
    state: State,
    families: list[str],
    sessions: list[Session],
    sessions_by_activity: dict[Activity, list[Session]],
    campers_by_family: dict[str, list[Camper]],
) -> State | None:
    if not families or not sessions:
        return None

    kind = rng.choice(_MOVE_KINDS)

    if kind == "assign":
        family_id = rng.choice(families)
        session = rng.choice(sessions)
        return assign_family(state, family_id, session, campers_by_family)

    if kind == "move":
        family_id = rng.choice(families)
        candidate_sessions = _sessions_of_family(state, family_id, campers_by_family)
        if not candidate_sessions:
            return None
        from_session = rng.choice(candidate_sessions)
        parallel = [s for s in sessions_by_activity[from_session.activity] if s != from_session]
        if not parallel:
            return None
        to_session = rng.choice(parallel)
        return move_family(state, family_id, from_session, to_session, campers_by_family)

    if kind == "swap":
        family_a = rng.choice(families)
        family_b = rng.choice(families)
        if family_a == family_b:
            return None
        sessions_a = _sessions_of_family(state, family_a, campers_by_family)
        sessions_b = _sessions_of_family(state, family_b, campers_by_family)
        if not sessions_a or not sessions_b:
            return None
        return swap_families(state, family_a, rng.choice(sessions_a), family_b, rng.choice(sessions_b), campers_by_family)

    if kind == "remove":
        family_id = rng.choice(families)
        candidate_sessions = _sessions_of_family(state, family_id, campers_by_family)
        if not candidate_sessions:
            return None
        session = rng.choice(candidate_sessions)
        return remove_family(state, family_id, session, campers_by_family)

    if kind == "fix_split":
        family_id = rng.choice(families)
        session = rng.choice(sessions)
        return fix_unsupervised_split(state, family_id, session, campers_by_family)

    return None  # pragma: no cover - _MOVE_KINDS is exhaustive


def run_chain(
    initial_state: State,
    campers: list[Camper],
    sessions: list[Session],
    campers_by_family: dict[str, list[Camper]],
    tier0_weights: Tier0Weights,
    compulsory: frozenset[Activity],
    cooling: CoolingSchedule,
    seed: int,
    iterations: int,
) -> State:
    """Run one simulated-annealing chain from initial_state for the given
    number of iterations, and return the best state seen (per `compare`),
    not necessarily the state the chain ends on - the whole point of
    accepting occasional worse moves is to escape local optima, so the
    final state isn't guaranteed to be the best one visited."""

    rng = random.Random(seed)
    families = sorted(campers_by_family)
    sessions_by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        sessions_by_activity[s.activity].append(s)

    current = initial_state
    current_score: Score = score(current, campers, sessions, tier0_weights, compulsory)
    best, best_score = current, current_score
    temperature = cooling.initial_temperature

    for _ in range(iterations):
        candidate = _propose_move(rng, current, families, sessions, sessions_by_activity, campers_by_family)
        if candidate is not None:
            candidate_score = score(candidate, campers, sessions, tier0_weights, compulsory)
            if rng.random() < acceptance_probability(current_score, candidate_score, temperature):
                current, current_score = candidate, candidate_score
                if compare(current_score, best_score) < 0:
                    best, best_score = current, current_score
        temperature *= cooling.cooling_rate

    return best
