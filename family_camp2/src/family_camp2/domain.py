"""Core, solver-independent data model.

See REQUIREMENTS.md §3 for the input data contract these types implement,
and DESIGN_OPTIONS.md §2.1 for the rationale behind keeping this module
free of any solver-specific concerns.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NamedTuple


@dataclass(frozen=True)
class Activity:
    name: str
    duration: timedelta
    min_occupancy: int
    max_occupancy: int
    min_age: int | None = None


@dataclass(frozen=True, eq=False)
class Session:
    """A single scheduled occurrence of an activity.

    Two sessions are considered the same session if they share an activity
    name, label, and start time - not necessarily the same ``Activity``
    object - so a session loaded twice from the same source data (e.g. once
    while building a model, once in a test fixture) compares equal.
    """

    activity: Activity
    label: str
    start: datetime

    @property
    def end(self) -> datetime:
        return self.start + self.activity.duration

    def _identity(self) -> tuple[str, str, datetime]:
        return (self.activity.name, self.label, self.start)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Session):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())

    def __repr__(self) -> str:
        return f"Session({self.activity.name!r}, {self.label!r}, {self.start!r})"


def sessions_overlap(a: Session, b: Session) -> bool:
    return a.start < b.end and b.start < a.end


@dataclass(frozen=True)
class Camper:
    name: str
    family_id: str
    age: int
    age_group: str
    priorities: tuple[Activity, ...] = field(default_factory=tuple)
    optional: tuple[Activity, ...] = field(default_factory=tuple)

    @property
    def is_adult(self) -> bool:
        return self.age >= 18


class Assignment(NamedTuple):
    camper: Camper
    session: Session


class Timetable:
    """An immutable set of (camper, session) assignments, with indexes."""

    def __init__(self, assignments: frozenset[Assignment] | set[Assignment] = frozenset()):
        self.assignments: frozenset[Assignment] = frozenset(assignments)

        sessions_for_camper: dict[Camper, set[Session]] = defaultdict(set)
        campers_for_session: dict[Session, set[Camper]] = defaultdict(set)
        for a in self.assignments:
            sessions_for_camper[a.camper].add(a.session)
            campers_for_session[a.session].add(a.camper)

        self.sessions_for_camper: dict[Camper, set[Session]] = dict(sessions_for_camper)
        self.campers_for_session: dict[Session, set[Camper]] = dict(campers_for_session)

    def __len__(self) -> int:
        return len(self.assignments)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Timetable):
            return NotImplemented
        return self.assignments == other.assignments

    def __repr__(self) -> str:
        return f"Timetable({len(self.assignments)} assignments)"

    def sessions_of(self, camper: Camper) -> set[Session]:
        return self.sessions_for_camper.get(camper, set())

    def campers_in(self, session: Session) -> set[Camper]:
        return self.campers_for_session.get(session, set())

    def with_assignment(self, camper: Camper, session: Session) -> Timetable:
        return Timetable(self.assignments | {Assignment(camper, session)})

    def without_assignment(self, camper: Camper, session: Session) -> Timetable:
        return Timetable(self.assignments - {Assignment(camper, session)})
