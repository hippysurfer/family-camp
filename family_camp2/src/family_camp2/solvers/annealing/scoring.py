"""Lexicographic scoring and acceptance for the simulated-annealing search.

See DESIGN_OPTIONS.md §4.1. The accept/reject *decision* always uses
strict lexicographic tuple comparison (``compare``), never a scalarised
combination - this is what lets Design B honour the tier ranking (a
higher tier must never be traded away for a better lower tier) inside a
local-search acceptance rule. A scalar magnitude is still used, but only
to drive the annealing temperature's acceptance *probability* for moves
that are lexicographically worse - never to decide whether a move is
better or worse in the first place.
"""

from __future__ import annotations

import math

from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.moves import State
from family_camp2.validation.class2 import Tier0Weights, check_class2, score_tier0
from family_camp2.validation.tiers import score_tier1, score_tier2

__all__ = ["Score", "score", "compare", "acceptance_probability"]

Score = tuple[int, float, float]


def score(
    state: State,
    campers: list[Camper],
    sessions: list[Session],
    tier0_weights: Tier0Weights = Tier0Weights(),
    compulsory: frozenset[Activity] = frozenset(),
) -> Score:
    """(tier0_score, -tier1_score, tier2_score) - lower is better in every
    position, so plain tuple ordering already gives the right lexicographic
    ranking (tier0 first, then tier1 - negated so "more satisfied" sorts
    as "better" alongside the others - then tier2)."""

    timetable = state.to_timetable()
    class2_report = check_class2(timetable, campers, compulsory, sessions, state.constraints)
    return (
        score_tier0(class2_report, tier0_weights),
        -score_tier1(timetable, campers),
        score_tier2(timetable, sessions),
    )


def compare(score_a: Score, score_b: Score) -> int:
    """-1 if a is better than b, 1 if worse, 0 if tied - strict lexicographic order."""
    if score_a < score_b:
        return -1
    if score_a > score_b:
        return 1
    return 0


def _magnitude(s: Score) -> float:
    """A rough scalar "badness" proxy used *only* to size the SA acceptance
    probability below - never for the accept/reject decision itself, which
    is always `compare`. Reuses tier0's own huge severity-weight scale
    (Tier0Weights) so that, consistent with (not a replacement for) strict
    lexicographic ordering, a difference at a higher tier dominates the
    exponential decay here too."""
    tier0_score, neg_tier1_score, tier2_score = s
    return tier0_score + neg_tier1_score * 1000.0 + tier2_score


def acceptance_probability(current: Score, candidate: Score, temperature: float) -> float:
    """1.0 if candidate is at least as good as current (per `compare`);
    otherwise the standard SA exponential-decay probability, sized by how
    much worse the candidate is (see `_magnitude`)."""
    if compare(candidate, current) <= 0:
        return 1.0
    if temperature <= 0:
        return 0.0
    delta = _magnitude(candidate) - _magnitude(current)
    return math.exp(-delta / temperature)
