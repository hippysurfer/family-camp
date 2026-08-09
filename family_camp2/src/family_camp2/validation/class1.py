"""Class 1 constraints: structurally always satisfiable (DESIGN_OPTIONS.md §2.2).

These can always be met by simply not making an assignment, so there is
never a legitimate reason for a solver to violate them. They are treated as
absolute invariants everywhere in family_camp2 - this module exists as an
independent safety net that can check *any* timetable against them,
regardless of which solver (or hand-built test fixture) produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from family_camp2.domain import Activity, Camper, Session, Timetable, sessions_overlap

__all__ = [
    "sessions_overlap",
    "DoubleBooking",
    "CapacityOverflow",
    "UnrequestedAssignment",
    "DuplicateActivityAssignment",
    "AgeIneligibleAssignment",
    "Class1Report",
    "find_double_bookings",
    "find_capacity_overflows",
    "find_unrequested_assignments",
    "find_duplicate_activity_assignments",
    "find_age_ineligible_assignments",
    "check_class1",
]


@dataclass(frozen=True)
class DoubleBooking:
    camper: Camper
    session_a: Session
    session_b: Session


@dataclass(frozen=True)
class CapacityOverflow:
    session: Session
    count: int
    max_occupancy: int


@dataclass(frozen=True)
class UnrequestedAssignment:
    camper: Camper
    session: Session


@dataclass(frozen=True)
class DuplicateActivityAssignment:
    camper: Camper
    activity: Activity
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class AgeIneligibleAssignment:
    camper: Camper
    session: Session


@dataclass
class Class1Report:
    double_bookings: list[DoubleBooking] = field(default_factory=list)
    capacity_overflows: list[CapacityOverflow] = field(default_factory=list)
    unrequested: list[UnrequestedAssignment] = field(default_factory=list)
    duplicate_activity: list[DuplicateActivityAssignment] = field(default_factory=list)
    age_ineligible: list[AgeIneligibleAssignment] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.double_bookings
            or self.capacity_overflows
            or self.unrequested
            or self.duplicate_activity
            or self.age_ineligible
        )


def find_double_bookings(timetable: Timetable) -> list[DoubleBooking]:
    violations: list[DoubleBooking] = []
    for camper, sessions in timetable.sessions_for_camper.items():
        ordered = sorted(sessions, key=lambda s: (s.start, s.label))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if sessions_overlap(a, b):
                    violations.append(DoubleBooking(camper, a, b))
    return violations


def find_capacity_overflows(timetable: Timetable) -> list[CapacityOverflow]:
    violations: list[CapacityOverflow] = []
    for session, campers in timetable.campers_for_session.items():
        if len(campers) > session.activity.max_occupancy:
            violations.append(CapacityOverflow(session, len(campers), session.activity.max_occupancy))
    return violations


def find_unrequested_assignments(timetable: Timetable) -> list[UnrequestedAssignment]:
    violations: list[UnrequestedAssignment] = []
    for assignment in timetable.assignments:
        camper, session = assignment
        requested = set(camper.priorities) | set(camper.optional)
        if session.activity not in requested:
            violations.append(UnrequestedAssignment(camper, session))
    return violations


def find_duplicate_activity_assignments(timetable: Timetable) -> list[DuplicateActivityAssignment]:
    violations: list[DuplicateActivityAssignment] = []
    for camper, sessions in timetable.sessions_for_camper.items():
        by_activity: dict[Activity, list[Session]] = {}
        for session in sessions:
            by_activity.setdefault(session.activity, []).append(session)
        for activity, activity_sessions in by_activity.items():
            if len(activity_sessions) > 1:
                ordered = tuple(sorted(activity_sessions, key=lambda s: (s.start, s.label)))
                violations.append(DuplicateActivityAssignment(camper, activity, ordered))
    return violations


def find_age_ineligible_assignments(timetable: Timetable) -> list[AgeIneligibleAssignment]:
    violations: list[AgeIneligibleAssignment] = []
    for assignment in timetable.assignments:
        camper, session = assignment
        min_age = session.activity.min_age
        if min_age is not None and camper.age < min_age:
            violations.append(AgeIneligibleAssignment(camper, session))
    return violations


def check_class1(timetable: Timetable) -> Class1Report:
    return Class1Report(
        double_bookings=find_double_bookings(timetable),
        capacity_overflows=find_capacity_overflows(timetable),
        unrequested=find_unrequested_assignments(timetable),
        duplicate_activity=find_duplicate_activity_assignments(timetable),
        age_ineligible=find_age_ineligible_assignments(timetable),
    )
