"""FR-77: a structural, time-based feasibility check independent of any
particular timetable or solver run.

The relevant unit here is the *family*, not the individual camper: Class
2's family-time-conflict rule (see class2.py's ``find_family_time_conflicts``)
means no two members of the same family may ever be in overlapping
sessions, even if they're in two different sessions of two different
activities. So a family behaves, time-wise, like a single indivisible
camper - it can only ever occupy one non-overlapping session slot at a
time, collectively.

This module answers "how many non-overlapping session slots could this
family possibly occupy across the whole camp, given its members' combined
age eligibility" and flags families whose total *distinct* requested-
activity count (the union of every member's priorities + optional
requests) exceeds that ceiling - a request count that ceiling can never
satisfy, no matter how well (or long) a solver runs.

This is a *necessary*, not *sufficient*, infeasibility check: staying
under the ceiling does not guarantee every request can be met (sessions of
the specific activities requested might still clash with each other, even
when the family's overall schedule has spare time elsewhere) - it exists
to help distinguish "not enough capacity" from "not enough time" as the
reason an optional request went unmet (FR-77).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from family_camp2.domain import Camper, Session

__all__ = ["FamilyOverdemand", "max_non_overlapping_sessions", "find_overdemanding_families"]


def max_non_overlapping_sessions(sessions: list[Session]) -> int:
    """The classic interval-scheduling-maximisation greedy (sort by end
    time, take a session whenever it doesn't overlap the last one taken) -
    provably optimal for "how many of these could all be attended by one
    person (or, here, one family)", since this only counts slots, not
    which activities fill them (so there's no per-activity grouping
    constraint to trip it up)."""

    ordered = sorted(sessions, key=lambda s: s.end)
    count = 0
    last_end = None
    for session in ordered:
        if last_end is None or session.start >= last_end:
            count += 1
            last_end = session.end
    return count


@dataclass(frozen=True)
class FamilyOverdemand:
    family_id: str
    members: tuple[Camper, ...]
    requested_count: int
    available_timeslots: int


def find_overdemanding_families(sessions: list[Session], campers: list[Camper]) -> list[FamilyOverdemand]:
    """For each family, compare the number of distinct activities
    requested by anyone in it (priorities + optional, unioned across
    members) against the maximum number of non-overlapping session slots
    available to the family collectively (``max_non_overlapping_sessions``).
    A session counts as available to the family if any one member is
    age-eligible for it, since different members can fill different
    sessions as long as those sessions don't overlap each other. Only
    families where demand exceeds that ceiling are returned."""

    by_family: dict[str, list[Camper]] = defaultdict(list)
    for camper in campers:
        by_family[camper.family_id].append(camper)

    overdemanding: list[FamilyOverdemand] = []
    for family_id, members in by_family.items():
        requested: set = set()
        for member in members:
            requested |= set(member.priorities) | set(member.optional)
        if not requested:
            continue

        eligible = [
            s
            for s in sessions
            if s.activity.min_age is None or any(m.age >= s.activity.min_age for m in members)
        ]
        available = max_non_overlapping_sessions(eligible)
        if len(requested) > available:
            overdemanding.append(FamilyOverdemand(family_id, tuple(members), len(requested), available))
    return overdemanding
