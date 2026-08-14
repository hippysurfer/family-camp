"""Tier 1 (FR-20/FR-21) and Tier 2 (FR-22) objective scoring.

See DESIGN_OPTIONS.md §2.3. FR-23 (idle time) is deliberately not scored
here - per OQ-3 it is reporting-only (see idle.py), not an objective.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import pvariance

from family_camp2.domain import Activity, Camper, Session, Timetable

__all__ = ["score_tier1", "score_tier2", "UnmetOptionalRequest", "find_unmet_optional_requests"]


def score_tier1(timetable: Timetable, campers: list[Camper]) -> float:
    """Sum, over campers, of the fraction of each camper's optional-activity
    requests that were met.

    A camper with zero optional requests contributes 1.0 (fully "satisfied"
    by having nothing left to want) rather than 0 or being excluded, so
    they don't distort the total either way. Because each camper
    contributes a 0-1 value regardless of how many optional activities they
    asked for, this already satisfies FR-21's fairness requirement by
    construction - a camper who asked for one thing isn't easier to
    "fully satisfy" than one who asked for five.
    """

    total = 0.0
    for camper in campers:
        if not camper.optional:
            total += 1.0
            continue
        assigned = {s.activity for s in timetable.sessions_of(camper)}
        met = len(set(camper.optional) & assigned)
        total += met / len(camper.optional)
    return total


def score_tier2(timetable: Timetable, sessions: list[Session]) -> float:
    """Average, across activities that run as more than one parallel
    session, of the population variance of occupancy across that
    activity's sessions. Lower is better (more even use of parallel
    sessions).

    Activities with only a single session are excluded entirely (there is
    no "spread" to measure), rather than counted as a variance of 0 -
    including them would dilute the average with values that don't reflect
    anything about spread quality. An instance with no multi-session
    activities at all scores 0.0.
    """

    by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for session in sessions:
        by_activity[session.activity].append(session)

    variances = []
    for activity_sessions in by_activity.values():
        if len(activity_sessions) <= 1:
            continue
        occupancies = [len(timetable.campers_in(s)) for s in activity_sessions]
        variances.append(pvariance(occupancies))

    if not variances:
        return 0.0
    return sum(variances) / len(variances)


@dataclass(frozen=True)
class UnmetOptionalRequest:
    camper: Camper
    activity: Activity


def find_unmet_optional_requests(timetable: Timetable, campers: list[Camper]) -> list[UnmetOptionalRequest]:
    """FR-76: the per-request breakdown behind ``score_tier1`` - which
    specific optional requests were not met, and by whom. Unlike Class 2's
    ``find_missing_priorities``, this is not a violation (optional
    requests are explicitly best-effort, not required for feasibility) -
    it exists purely to let an organiser see where demand for optional
    activities went unsatisfied."""

    unmet: list[UnmetOptionalRequest] = []
    for camper in campers:
        assigned = {s.activity for s in timetable.sessions_of(camper)}
        for activity in camper.optional:
            if activity not in assigned:
                unmet.append(UnmetOptionalRequest(camper, activity))
    return unmet
