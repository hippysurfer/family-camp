"""Class 2 constraints: demand-driven, can genuinely conflict (DESIGN_OPTIONS.md §2.2).

Whether these can all be satisfied depends on how registration demand
compares to capacity, so real inputs may make them jointly infeasible.
This module also provides the Tier 0 weighted score used to rank
best-effort schedules (FR-30/FR-31): a solution with fewer severe
violations always beats one with more, provided the default weights'
relative sizes comfortably exceed the largest plausible violation count at
the scale in REQUIREMENTS.md NFR-1 (so a lower-severity tier's violations
can never numerically outweigh a single higher-severity one).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from family_camp2.domain import Activity, Camper, Session, Timetable, sessions_overlap

__all__ = [
    "MissingPriority",
    "FamilyTimeConflict",
    "UnsupervisedFamilySplit",
    "UnderMinimumSession",
    "UnmetCompulsoryActivity",
    "Class2Report",
    "Tier0Weights",
    "find_missing_priorities",
    "find_family_time_conflicts",
    "find_unsupervised_family_splits",
    "find_under_minimum_sessions",
    "find_unmet_compulsory_activities",
    "check_class2",
    "score_tier0",
]


@dataclass(frozen=True)
class MissingPriority:
    camper: Camper
    activity: Activity


@dataclass(frozen=True)
class FamilyTimeConflict:
    family_id: str
    camper_a: Camper
    session_a: Session
    camper_b: Camper
    session_b: Session


@dataclass(frozen=True)
class UnsupervisedFamilySplit:
    family_id: str
    activity: Activity
    session: Session


@dataclass(frozen=True)
class UnderMinimumSession:
    session: Session
    count: int
    min_occupancy: int


@dataclass(frozen=True)
class UnmetCompulsoryActivity:
    camper: Camper
    activity: Activity


@dataclass
class Class2Report:
    missing_priorities: list[MissingPriority] = field(default_factory=list)
    family_time_conflicts: list[FamilyTimeConflict] = field(default_factory=list)
    unsupervised_splits: list[UnsupervisedFamilySplit] = field(default_factory=list)
    under_minimum_sessions: list[UnderMinimumSession] = field(default_factory=list)
    unmet_compulsory: list[UnmetCompulsoryActivity] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.missing_priorities
            or self.family_time_conflicts
            or self.unsupervised_splits
            or self.under_minimum_sessions
            or self.unmet_compulsory
        )


@dataclass(frozen=True)
class Tier0Weights:
    """Severity ordering, most severe first: priority > family safety > min occupancy > compulsory.

    The ratios between these defaults are chosen to be large (10,000x)
    relative to the scale in REQUIREMENTS.md NFR-1 (upper bound: 500
    campers), so that no plausible number of lower-severity violations can
    numerically outweigh a single higher-severity one in the weighted sum -
    this is what makes ``score_tier0`` behave as a severity ranking rather
    than an arbitrary trade-off. Configurable per NFR-4.
    """

    missing_priority: int = 10**12
    family_safety: int = 10**8
    under_minimum: int = 10**4
    compulsory: int = 1


def find_missing_priorities(timetable: Timetable, campers: list[Camper]) -> list[MissingPriority]:
    violations: list[MissingPriority] = []
    for camper in campers:
        assigned_activities = {s.activity for s in timetable.sessions_of(camper)}
        for activity in camper.priorities:
            if activity not in assigned_activities:
                violations.append(MissingPriority(camper, activity))
    return violations


def find_family_time_conflicts(timetable: Timetable) -> list[FamilyTimeConflict]:
    violations: list[FamilyTimeConflict] = []
    by_family: dict[str, list] = defaultdict(list)
    for assignment in timetable.assignments:
        by_family[assignment.camper.family_id].append(assignment)

    for family_id, assignments in by_family.items():
        ordered = sorted(assignments, key=lambda a: (a.session.start, a.session.label, a.camper.name))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                if a.camper == b.camper or a.session == b.session:
                    continue
                if sessions_overlap(a.session, b.session):
                    violations.append(
                        FamilyTimeConflict(family_id, a.camper, a.session, b.camper, b.session)
                    )
    return violations


def find_unsupervised_family_splits(timetable: Timetable) -> list[UnsupervisedFamilySplit]:
    """OQ-7: a family split across several sessions of the same priority
    activity is acceptable, but every one of those sessions must contain at
    least one adult (18+) from the family."""

    violations: list[UnsupervisedFamilySplit] = []
    grouping: dict[tuple[str, Activity], set[Session]] = defaultdict(set)
    for assignment in timetable.assignments:
        camper, session = assignment
        if session.activity in camper.priorities:
            grouping[(camper.family_id, session.activity)].add(session)

    for (family_id, activity), sessions in grouping.items():
        if len(sessions) <= 1:
            continue  # not split across multiple sessions - nothing to supervise
        for session in sorted(sessions, key=lambda s: (s.start, s.label)):
            members_here = [c for c in timetable.campers_in(session) if c.family_id == family_id]
            if not any(c.is_adult for c in members_here):
                violations.append(UnsupervisedFamilySplit(family_id, activity, session))
    return violations


def find_under_minimum_sessions(timetable: Timetable) -> list[UnderMinimumSession]:
    violations: list[UnderMinimumSession] = []
    for session, campers in timetable.campers_for_session.items():
        count = len(campers)
        if 0 < count < session.activity.min_occupancy:
            violations.append(UnderMinimumSession(session, count, session.activity.min_occupancy))
    return violations


def find_unmet_compulsory_activities(
    timetable: Timetable, campers: list[Camper], compulsory: frozenset[Activity]
) -> list[UnmetCompulsoryActivity]:
    violations: list[UnmetCompulsoryActivity] = []
    if not compulsory:
        return violations
    for camper in campers:
        assigned_activities = {s.activity for s in timetable.sessions_of(camper)}
        for activity in compulsory:
            if activity not in assigned_activities:
                violations.append(UnmetCompulsoryActivity(camper, activity))
    return violations


def check_class2(
    timetable: Timetable,
    campers: list[Camper],
    compulsory: frozenset[Activity] = frozenset(),
) -> Class2Report:
    return Class2Report(
        missing_priorities=find_missing_priorities(timetable, campers),
        family_time_conflicts=find_family_time_conflicts(timetable),
        unsupervised_splits=find_unsupervised_family_splits(timetable),
        under_minimum_sessions=find_under_minimum_sessions(timetable),
        unmet_compulsory=find_unmet_compulsory_activities(timetable, campers, compulsory),
    )


def score_tier0(report: Class2Report, weights: Tier0Weights = Tier0Weights()) -> int:
    return (
        len(report.missing_priorities) * weights.missing_priority
        + (len(report.family_time_conflicts) + len(report.unsupervised_splits)) * weights.family_safety
        + len(report.under_minimum_sessions) * weights.under_minimum
        + len(report.unmet_compulsory) * weights.compulsory
    )
