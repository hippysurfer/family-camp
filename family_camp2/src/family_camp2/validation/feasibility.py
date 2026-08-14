"""FR-77: a structural, time-based feasibility check independent of any
particular timetable or solver run.

Even with unlimited session capacity, a camper can only ever be in one
place at a time. This module answers "how many non-overlapping session
slots could this camper possibly occupy across the whole camp, given
their age eligibility" and flags campers whose combined priority+optional
request count exceeds that ceiling - a request count that ceiling can
never satisfy, no matter how well (or long) a solver runs.

This is a *necessary*, not *sufficient*, infeasibility check: staying
under the ceiling does not guarantee every request can be met (sessions of
the specific activities requested might still clash with each other, even
when the camper's overall schedule has spare time elsewhere) - it exists
to help distinguish "not enough capacity" from "not enough time" as the
reason an optional request went unmet (FR-77).
"""

from __future__ import annotations

from dataclasses import dataclass

from family_camp2.domain import Camper, Session

__all__ = ["CamperOverdemand", "max_non_overlapping_sessions", "find_overdemanding_campers"]


def max_non_overlapping_sessions(sessions: list[Session]) -> int:
    """The classic interval-scheduling-maximisation greedy (sort by end
    time, take a session whenever it doesn't overlap the last one taken) -
    provably optimal for "how many of these could all be attended by one
    person", since this only counts slots, not which activities fill
    them (so there's no per-activity grouping constraint to trip it up)."""

    ordered = sorted(sessions, key=lambda s: s.end)
    count = 0
    last_end = None
    for session in ordered:
        if last_end is None or session.start >= last_end:
            count += 1
            last_end = session.end
    return count


@dataclass(frozen=True)
class CamperOverdemand:
    camper: Camper
    requested_count: int
    available_timeslots: int


def find_overdemanding_campers(sessions: list[Session], campers: list[Camper]) -> list[CamperOverdemand]:
    """For each camper, compare the number of distinct activities they
    requested (priorities + optional) against the maximum number of
    non-overlapping, age-eligible session slots available to them anywhere
    in the camp (``max_non_overlapping_sessions``). Only campers where
    demand exceeds that ceiling are returned."""

    overdemanding: list[CamperOverdemand] = []
    for camper in campers:
        requested = set(camper.priorities) | set(camper.optional)
        if not requested:
            continue
        eligible = [s for s in sessions if s.activity.min_age is None or camper.age >= s.activity.min_age]
        available = max_non_overlapping_sessions(eligible)
        if len(requested) > available:
            overdemanding.append(CamperOverdemand(camper, len(requested), available))
    return overdemanding
