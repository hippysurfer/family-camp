"""The FR-96 Tier A rule set. Each is a frozen dataclass whose fields are
exactly its spreadsheet expression's arguments (e.g.
``no_activities_on_day(2)`` -> ``NoActivitiesOnDay(day=2)``), registered
under the same name the expression uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from family_camp2.constraints.registry import register
from family_camp2.domain import Camper, Session

__all__ = [
    "NoActivitiesOnDay",
    "NoActivityBefore",
    "NoActivityAfter",
    "NoActivitiesBetween",
    "NotOnActivity",
]


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _day_number(session: Session, all_sessions: list[Session]) -> int:
    """1-indexed position of session's calendar date among the distinct
    dates present in all_sessions (FR-3: no fixed camp length is assumed,
    so "day N" is derived from the actual data, not a fixed date)."""
    distinct_dates = sorted({s.start.date() for s in all_sessions})
    return distinct_dates.index(session.start.date()) + 1


@register("no_activities_on_day")
@dataclass(frozen=True)
class NoActivitiesOnDay:
    day: int

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        return _day_number(session, all_sessions) == self.day


@register("no_activity_before")
@dataclass(frozen=True)
class NoActivityBefore:
    time: str  # "HH:MM"

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        return session.start.time() < _parse_time(self.time)


@register("no_activity_after")
@dataclass(frozen=True)
class NoActivityAfter:
    time: str  # "HH:MM"

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        return session.start.time() > _parse_time(self.time)


@register("no_activities_between")
@dataclass(frozen=True)
class NoActivitiesBetween:
    start: str  # "HH:MM"
    end: str  # "HH:MM"

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        t = session.start.time()
        return _parse_time(self.start) <= t <= _parse_time(self.end)


@register("not_on_activity")
@dataclass(frozen=True)
class NotOnActivity:
    activity: str

    def forbids(self, camper: Camper, session: Session, all_sessions: list[Session]) -> bool:
        return session.activity.name == self.activity
