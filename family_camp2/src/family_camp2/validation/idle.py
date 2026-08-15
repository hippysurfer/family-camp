"""FR-74: idle-time reporting for staffing/supervision planning - who has
nothing scheduled at a given time, and two more targeted views on top of
that plain camper-level list.

Idle time is reporting-only (useful for staffing awareness), not an
optimisation objective - so this lives separately from tiers.py.
Deliberately makes no assumption about camp length (FR-3/NFR-5): the time
range covered is derived from the actual sessions passed in, not a
hardcoded number of days.

A whole family with *nobody* active is a different signal than "this
specific adult happens to be free": the former flags a possible
scheduling gap for that family, the latter flags who could help
elsewhere. Both are derived from the same active-session scan already
needed for ``idle_campers`` - no second full pass over campers/sessions
(NFR-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from family_camp2.domain import Camper, Session, Timetable

__all__ = ["IdleBucket", "IdleReport", "find_idle_slots"]


@dataclass(frozen=True)
class IdleBucket:
    start: datetime
    end: datetime
    idle_campers: tuple[Camper, ...]
    idle_families: tuple[str, ...]
    idle_adults: tuple[Camper, ...]


@dataclass
class IdleReport:
    buckets: list[IdleBucket] = field(default_factory=list)


def find_idle_slots(
    timetable: Timetable,
    campers: list[Camper],
    sessions: list[Session],
    granularity: timedelta = timedelta(hours=1),
) -> IdleReport:
    """For each time bucket where at least one session is running: the
    campers with no assignment overlapping that bucket (``idle_campers``),
    the families where *every* member is idle (``idle_families`` - FR-74),
    and the subset of ``idle_campers`` who are adults (``idle_adults`` -
    FR-74). Buckets with no session running at all (e.g. a lunch break)
    are skipped entirely, not reported as "everyone idle"."""

    if not sessions:
        return IdleReport()

    earliest = min(s.start for s in sessions)
    latest = max(s.end for s in sessions)
    all_family_ids = {c.family_id for c in campers if c.family_id}

    buckets: list[IdleBucket] = []
    bucket_start = earliest
    while bucket_start < latest:
        bucket_end = bucket_start + granularity
        active_sessions = [s for s in sessions if s.start < bucket_end and bucket_start < s.end]
        if active_sessions:
            active_campers: set[Camper] = set()
            for s in active_sessions:
                active_campers |= timetable.campers_in(s)

            idle = tuple(c for c in campers if c not in active_campers)
            active_family_ids = {c.family_id for c in active_campers if c.family_id}
            idle_families = tuple(sorted(all_family_ids - active_family_ids))
            idle_adults = tuple(c for c in idle if c.is_adult)

            buckets.append(IdleBucket(bucket_start, bucket_end, idle, idle_families, idle_adults))
        bucket_start += granularity

    return IdleReport(buckets)
