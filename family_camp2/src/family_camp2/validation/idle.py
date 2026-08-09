"""FR-23: idle-time reporting.

Per OQ-3, idle time is reporting-only (useful for staffing awareness), not
an optimisation objective - so this lives separately from tiers.py.
Deliberately makes no assumption about camp length (FR-3/NFR-5): the time
range covered is derived from the actual sessions passed in, not a
hardcoded number of days.
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


@dataclass
class IdleReport:
    buckets: list[IdleBucket] = field(default_factory=list)


def find_idle_slots(
    timetable: Timetable,
    campers: list[Camper],
    sessions: list[Session],
    granularity: timedelta = timedelta(hours=1),
) -> IdleReport:
    """For each time bucket where at least one session is running, list the
    campers with no assignment overlapping that bucket. Buckets with no
    session running at all (e.g. a lunch break) are skipped entirely, not
    reported as "everyone idle"."""

    if not sessions:
        return IdleReport()

    earliest = min(s.start for s in sessions)
    latest = max(s.end for s in sessions)

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
            buckets.append(IdleBucket(bucket_start, bucket_end, idle))
        bucket_start += granularity

    return IdleReport(buckets)
