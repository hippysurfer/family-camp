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

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.domain import Activity, Camper, Session, Timetable, sessions_overlap
from family_camp2.validation.custom_constraints import CustomConstraintViolation, find_custom_constraint_violations

__all__ = [
    "MissingPriority",
    "FamilyTimeConflict",
    "UnsupervisedFamilySplit",
    "FamilySplitOccurrence",
    "UnderMinimumSession",
    "UnmetCompulsoryActivity",
    "Class2Report",
    "Tier0Weights",
    "find_missing_priorities",
    "find_family_time_conflicts",
    "find_unsupervised_family_splits",
    "find_family_splits",
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
    reason: str  # "lone_adult" or "unaccompanied_child" - see find_unsupervised_family_splits


@dataclass(frozen=True)
class FamilySplitOccurrence:
    family_id: str
    activity: Activity
    sessions: tuple[Session, ...]


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
    # FR-24: every (family, activity) split across >1 session, regardless of
    # how well-supervised each session is (unsupervised_splits is the
    # separate, safety-focused check for that). A merely-occurring split is
    # not itself a Class 2 violation - it's a last-resort outcome, not
    # something that's ever wrong to have happened - so it's deliberately
    # excluded from is_clean below, even though score_tier0 penalises it.
    family_splits: list[FamilySplitOccurrence] = field(default_factory=list)
    # FR-95: soft custom-constraint violations (REQUIREMENTS.md §4.10).
    # Excluded from is_clean for the same reason family_splits is: the
    # organiser explicitly marked these "soft" (best-effort), so failing
    # to honour one shouldn't flip Feasible to False - it's still scored
    # via score_tier0, at a higher severity than missing_priority.
    custom_constraint_violations: list[CustomConstraintViolation] = field(default_factory=list)

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
    """Severity ordering, most severe first: **custom constraint**
    (FR-95 - an organiser-authored soft constraint outranks even a
    missing priority) > priority > family safety (time conflicts /
    poorly supervised splits) > family split occurrence (FR-24 - avoided
    as a last resort, even when properly supervised) > min occupancy >
    compulsory.

    The ratios between these defaults are chosen to be large (1,000x)
    relative to the scale in REQUIREMENTS.md NFR-1 (upper bound: 500
    campers), so that no plausible number of lower-severity violations can
    numerically outweigh a single higher-severity one in the weighted sum -
    this is what makes ``score_tier0`` behave as a severity ranking rather
    than an arbitrary trade-off.

    CP-SAT rejects a model as ``MODEL_INVALID`` once the objective's
    integer coefficients get large enough to risk overflow internally, so
    these weights can't simply be scaled up arbitrarily to add more bands
    or headroom. Unlike the other five bands, ``custom_constraint``'s term
    count is *not* intrinsically bounded to a small number by the camp's
    structure (one term per family/activity pair, one per session, etc.)
    - it is one term per (camper, session) pair that some soft constraint
    forbids, so a single constraint row that broadly targets most of the
    camp with a rule matching most sessions can in principle push the
    objective towards overflow (empirically, above roughly 9,000 such
    terms against a real ~283-camper dataset). This is out of scope for
    the per-camper/per-family constraints this feature is designed for
    (FR-90); a rule intended to apply camp-wide belongs in the core
    scheduling model (e.g. ``Activity.min_age``, compulsory activities),
    not this extension point. Configurable per NFR-4.
    """

    custom_constraint: int = 10**15
    missing_priority: int = 10**12
    family_safety: int = 10**9
    family_split: int = 10**6
    under_minimum: int = 10**3
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


def _split_groups(timetable: Timetable) -> dict[tuple[str, Activity], set[Session]]:
    """(family_id, activity) -> the set of sessions of that activity the
    family's members are spread across, for every activity (priority or
    optional) - not just priorities, unlike the pre-FR-17 version of this
    check. Shared by find_unsupervised_family_splits and find_family_splits
    so both agree on exactly what counts as "split"."""

    grouping: dict[tuple[str, Activity], set[Session]] = defaultdict(set)
    for assignment in timetable.assignments:
        camper, session = assignment
        grouping[(camper.family_id, session.activity)].add(session)
    return grouping


def find_unsupervised_family_splits(timetable: Timetable, campers: list[Camper]) -> list[UnsupervisedFamilySplit]:
    """FR-17: when a family is split across several sessions of the same
    activity, every one of those sessions must be jointly attended by at
    least one adult (18+) AND at least one non-adult family member - no
    lone adults, no unaccompanied children - EXCEPT a children-only
    session is still fine if some adult in the family (whether or not they
    requested this activity themselves) has no assignment overlapping that
    session's time, and so is free to informally accompany them. There is
    no equivalent exception for an adults-only session.

    Takes the full ``campers`` list (not just those with an assignment)
    because the idle-adult exception needs to know about every adult in
    the family, including one who isn't assigned to anything at all - the
    most straightforwardly "idle" case there is.

    If no non-adult member of the family ever requested this particular
    activity, "a child attends" can never happen for it no matter what the
    solver does - flagging every split session as a lone-adult violation
    in that case would be a permanent, unfixable penalty rather than a
    useful signal, so such (family, activity) pairs are skipped entirely.
    """

    campers_by_family: dict[str, list[Camper]] = defaultdict(list)
    for c in campers:
        campers_by_family[c.family_id].append(c)

    violations: list[UnsupervisedFamilySplit] = []
    for (family_id, activity), sessions in _split_groups(timetable).items():
        if len(sessions) <= 1:
            continue  # not split across multiple sessions - nothing to supervise

        family_members = campers_by_family.get(family_id, [])
        family_adults = [c for c in family_members if c.is_adult]
        a_child_could_attend = any(
            not c.is_adult and (activity in c.priorities or activity in c.optional) for c in family_members
        )
        if not a_child_could_attend:
            continue

        for session in sorted(sessions, key=lambda s: (s.start, s.label)):
            attendees = [c for c in timetable.campers_in(session) if c.family_id == family_id]
            has_adult = any(c.is_adult for c in attendees)
            has_child = any(not c.is_adult for c in attendees)

            if has_adult and has_child:
                continue  # properly mixed - fine
            if has_adult and not has_child:
                violations.append(UnsupervisedFamilySplit(family_id, activity, session, reason="lone_adult"))
                continue

            # Remaining case: has_child and not has_adult (attendees is
            # non-empty by construction, so one of the two must hold).
            idle_adult_available = any(
                not any(sessions_overlap(session, other) for other in timetable.sessions_of(adult))
                for adult in family_adults
            )
            if not idle_adult_available:
                violations.append(
                    UnsupervisedFamilySplit(family_id, activity, session, reason="unaccompanied_child")
                )
    return violations


def find_family_splits(timetable: Timetable) -> list[FamilySplitOccurrence]:
    """FR-24: every (family, activity) pair where the family's attending
    members are spread across more than one session of that activity,
    regardless of how well-supervised each session is (that's the separate
    concern find_unsupervised_family_splits checks) - used to drive the
    "prefer not splitting families at all" objective."""

    return [
        FamilySplitOccurrence(family_id, activity, tuple(sorted(sessions, key=lambda s: (s.start, s.label))))
        for (family_id, activity), sessions in _split_groups(timetable).items()
        if len(sessions) > 1
    ]


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
    sessions: list[Session] = (),
    constraints: list[ConstraintInstance] = (),
) -> Class2Report:
    return Class2Report(
        missing_priorities=find_missing_priorities(timetable, campers),
        family_time_conflicts=find_family_time_conflicts(timetable),
        unsupervised_splits=find_unsupervised_family_splits(timetable, campers),
        under_minimum_sessions=find_under_minimum_sessions(timetable),
        unmet_compulsory=find_unmet_compulsory_activities(timetable, campers, compulsory),
        family_splits=find_family_splits(timetable),
        custom_constraint_violations=find_custom_constraint_violations(timetable, sessions, constraints),
    )


def score_tier0(report: Class2Report, weights: Tier0Weights = Tier0Weights()) -> int:
    return (
        len(report.custom_constraint_violations) * weights.custom_constraint
        + len(report.missing_priorities) * weights.missing_priority
        + (len(report.family_time_conflicts) + len(report.unsupervised_splits)) * weights.family_safety
        + len(report.family_splits) * weights.family_split
        + len(report.under_minimum_sessions) * weights.under_minimum
        + len(report.unmet_compulsory) * weights.compulsory
    )
