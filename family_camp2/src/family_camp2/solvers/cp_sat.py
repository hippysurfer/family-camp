"""Design A: constraint programming via Google OR-Tools CP-SAT.

See DESIGN_OPTIONS.md §3. This module is built up over several
implementation-plan steps: Step 12 (this one) builds the decision
variables and Class 1 structural constraints only; Step 13 adds Class 2
violation indicators and the Tier 0 objective; Step 14 completes the
three-phase lexicographic solve and the ``CpSatSolver`` itself.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from ortools.sat.python import cp_model

from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable, sessions_overlap
from family_camp2.validation.class2 import Tier0Weights

__all__ = [
    "VarIndex",
    "build_model",
    "extract_timetable",
    "Class2Vars",
    "add_class2_indicators",
    "tier0_expr",
    "solve_phase1",
]

# An arbitrary fixed reference point used to convert datetimes to the small
# integer offsets CP-SAT's interval variables require. Any fixed epoch
# works; this one just keeps the resulting integers small and readable.
_EPOCH = datetime(2000, 1, 1)


def _to_minutes(dt: datetime) -> int:
    return int((dt - _EPOCH).total_seconds() // 60)


@dataclass
class VarIndex:
    """Maps (camper, session) -> BoolVar, for eligible pairs only.

    A pair is only eligible - and only gets a variable - if the camper
    requested the session's activity (priority or optional) and is
    age-eligible for it (OQ-8). This is what makes Class 1's
    unrequested-activity and age-eligibility rules structural rather than
    something the objective has to discourage (DESIGN_OPTIONS.md §3.1):
    the model has no way to represent an invalid assignment at all.
    """

    by_pair: dict[tuple[Camper, Session], cp_model.IntVar] = field(default_factory=dict)
    by_camper: dict[Camper, list[Session]] = field(default_factory=dict)
    by_session: dict[Session, list[Camper]] = field(default_factory=dict)

    def get(self, camper: Camper, session: Session) -> cp_model.IntVar | None:
        return self.by_pair.get((camper, session))

    def __contains__(self, pair: tuple[Camper, Session]) -> bool:
        return pair in self.by_pair


def _is_eligible(camper: Camper, session: Session) -> bool:
    activity = session.activity
    requested = activity in camper.priorities or activity in camper.optional
    if not requested:
        return False
    if activity.min_age is not None and camper.age < activity.min_age:
        return False
    return True


def build_model(
    activities: list[Activity], sessions: list[Session], campers: list[Camper]
) -> tuple[cp_model.CpModel, VarIndex]:
    model = cp_model.CpModel()

    by_pair: dict[tuple[Camper, Session], cp_model.IntVar] = {}
    by_camper: dict[Camper, list[Session]] = {c: [] for c in campers}
    by_session: dict[Session, list[Camper]] = {s: [] for s in sessions}

    for camper in campers:
        for session in sessions:
            if _is_eligible(camper, session):
                var = model.NewBoolVar(f"x[{camper.name}|{session.activity.name}|{session.label}]")
                by_pair[(camper, session)] = var
                by_camper[camper].append(session)
                by_session[session].append(camper)

    var_index = VarIndex(by_pair=by_pair, by_camper=by_camper, by_session=by_session)

    # FR-10: no double-booking. A no-overlap constraint over each camper's
    # candidate sessions, using optional intervals gated by the assignment
    # variable itself - only sessions actually chosen participate.
    for camper in campers:
        candidate_sessions = by_camper[camper]
        if len(candidate_sessions) < 2:
            continue
        intervals = []
        for session in candidate_sessions:
            var = by_pair[(camper, session)]
            start = _to_minutes(session.start)
            end = _to_minutes(session.end)
            intervals.append(
                model.NewOptionalIntervalVar(
                    start, end - start, end, var, f"iv[{camper.name}|{session.activity.name}|{session.label}]"
                )
            )
        model.AddNoOverlap(intervals)

    # FR-12 (max side): session capacity.
    for session in sessions:
        candidate_campers = by_session[session]
        if not candidate_campers:
            continue
        model.Add(sum(by_pair[(c, session)] for c in candidate_campers) <= session.activity.max_occupancy)

    # FR-15: no duplicate activity. Eligibility alone doesn't rule this out
    # (a camper can be eligible for two different session instances of the
    # same activity, e.g. a morning and an afternoon slot) - unlike
    # unrequested-activity and age-eligibility, this needs an explicit
    # constraint, not just a restricted variable domain.
    for camper in campers:
        sessions_by_activity: dict[Activity, list[cp_model.IntVar]] = {}
        for session in by_camper[camper]:
            sessions_by_activity.setdefault(session.activity, []).append(by_pair[(camper, session)])
        for activity_vars in sessions_by_activity.values():
            if len(activity_vars) > 1:
                model.Add(sum(activity_vars) <= 1)

    return model, var_index


def extract_timetable(solver: cp_model.CpSolver, var_index: VarIndex) -> Timetable:
    assignments = {
        Assignment(camper, session)
        for (camper, session), var in var_index.by_pair.items()
        if solver.Value(var)
    }
    return Timetable(frozenset(assignments))


# --- Class 2: demand-driven violation indicators and the Tier 0 objective ---
#
# Each indicator below is a BoolVar reified against the assignment
# variables so it is forced to 1 exactly when the corresponding violation
# genuinely occurs, and free to be 0 otherwise - that "free to be 0" is
# what lets Tier 0's objective (minimising a weighted sum of these) push
# the solver towards fewer violations, while still allowing them when the
# input data makes them unavoidable (FR-30/FR-31).


@dataclass
class Class2Vars:
    missing_priority: list[cp_model.IntVar] = field(default_factory=list)
    family_conflict: list[cp_model.IntVar] = field(default_factory=list)
    unsupervised_split: list[cp_model.IntVar] = field(default_factory=list)
    under_minimum: list[cp_model.IntVar] = field(default_factory=list)
    unmet_compulsory: list[cp_model.IntVar] = field(default_factory=list)


def _reify_at_least_one(model: cp_model.CpModel, member_vars: list[cp_model.IntVar], name: str) -> cp_model.IntVar:
    """A BoolVar equal to 1 iff at least one of member_vars is 1."""
    if not member_vars:
        var = model.NewBoolVar(name)
        model.Add(var == 0)
        return var
    if len(member_vars) == 1:
        return member_vars[0]
    var = model.NewBoolVar(name)
    model.AddMaxEquality(var, member_vars)
    return var


def _reify_activity_missing(
    model: cp_model.CpModel, camper: Camper, activity: Activity, var_index: VarIndex, name: str
) -> cp_model.IntVar:
    """A BoolVar equal to 1 iff camper has zero assigned sessions of activity."""
    session_vars = [
        var_index.by_pair[(camper, s)] for s in var_index.by_camper.get(camper, []) if s.activity == activity
    ]
    missing = model.NewBoolVar(name)
    if not session_vars:
        # No eligible session exists for this activity at all (e.g. an
        # age-restricted priority the camper can never reach) - always missing.
        model.Add(missing == 1)
        return missing
    total = sum(session_vars)
    model.Add(total == 0).OnlyEnforceIf(missing)
    model.Add(total >= 1).OnlyEnforceIf(missing.Not())
    return missing


def _reify_under_minimum(model: cp_model.CpModel, occ_expr, min_occupancy: int, name: str) -> cp_model.IntVar:
    """A BoolVar equal to 1 iff 0 < occ_expr < min_occupancy."""
    nonzero = model.NewBoolVar(f"{name}|nonzero")
    model.Add(occ_expr >= 1).OnlyEnforceIf(nonzero)
    model.Add(occ_expr == 0).OnlyEnforceIf(nonzero.Not())

    below_min = model.NewBoolVar(f"{name}|below_min")
    model.Add(occ_expr <= min_occupancy - 1).OnlyEnforceIf(below_min)
    model.Add(occ_expr >= min_occupancy).OnlyEnforceIf(below_min.Not())

    under = model.NewBoolVar(name)
    model.AddBoolAnd([nonzero, below_min]).OnlyEnforceIf(under)
    model.AddBoolOr([nonzero.Not(), below_min.Not()]).OnlyEnforceIf(under.Not())
    return under


def _family_present_vars(
    model: cp_model.CpModel,
    campers_by_family: dict[str, list[Camper]],
    var_index: VarIndex,
    sessions: list[Session],
) -> dict[tuple[str, Session], cp_model.IntVar]:
    """present[(family_id, session)] = 1 iff any of the given family members is assigned to that session."""
    result: dict[tuple[str, Session], cp_model.IntVar] = {}
    for family_id, members in campers_by_family.items():
        for session in sessions:
            member_vars = [var_index.by_pair[(c, session)] for c in members if (c, session) in var_index]
            if not member_vars:
                continue
            result[(family_id, session)] = _reify_at_least_one(
                model, member_vars, f"present[{family_id}|{session.activity.name}|{session.label}]"
            )
    return result


def add_class2_indicators(
    model: cp_model.CpModel,
    var_index: VarIndex,
    campers: list[Camper],
    sessions: list[Session],
    compulsory: frozenset[Activity] = frozenset(),
) -> Class2Vars:
    result = Class2Vars()
    campers_by_family: dict[str, list[Camper]] = defaultdict(list)
    for c in campers:
        campers_by_family[c.family_id].append(c)

    # FR-13: missing priorities.
    for c in campers:
        for activity in c.priorities:
            result.missing_priority.append(
                _reify_activity_missing(model, c, activity, var_index, f"missing_priority[{c.name}|{activity.name}]")
            )

    # FR-16: unmet compulsory activities.
    for c in campers:
        for activity in compulsory:
            result.unmet_compulsory.append(
                _reify_activity_missing(model, c, activity, var_index, f"unmet_compulsory[{c.name}|{activity.name}]")
            )

    # FR-11: family time conflicts. Two overlapping sessions both containing
    # a member of the same family is a conflict - since Class 1's
    # no-double-booking constraint already guarantees no single camper can
    # be in both, "family present in both" necessarily means two different
    # members, matching the shared validator's definition (class2.py).
    present = _family_present_vars(model, campers_by_family, var_index, sessions)
    overlapping_pairs = [
        (a, b) for i, a in enumerate(sessions) for b in sessions[i + 1 :] if sessions_overlap(a, b)
    ]
    for family_id in campers_by_family:
        for session_a, session_b in overlapping_pairs:
            pa = present.get((family_id, session_a))
            pb = present.get((family_id, session_b))
            if pa is None or pb is None:
                continue
            conflict = model.NewBoolVar(f"conflict[{family_id}|{session_a.label}|{session_b.label}]")
            model.AddBoolAnd([pa, pb]).OnlyEnforceIf(conflict)
            model.AddBoolOr([pa.Not(), pb.Not()]).OnlyEnforceIf(conflict.Not())
            result.family_conflict.append(conflict)

    # FR-12 (min side): under-minimum sessions.
    for session in sessions:
        candidates = var_index.by_session.get(session, [])
        if not candidates:
            continue
        occ_expr = sum(var_index.by_pair[(c, session)] for c in candidates)
        result.under_minimum.append(
            _reify_under_minimum(
                model, occ_expr, session.activity.min_occupancy, f"under_minimum[{session.activity.name}|{session.label}]"
            )
        )

    # OQ-7: unsupervised family splits - restricted to activities that are a
    # priority for the specific family members involved, per the shared
    # validator's definition (class2.find_unsupervised_family_splits).
    priority_activities_by_family: dict[str, set[Activity]] = defaultdict(set)
    for c in campers:
        for a in c.priorities:
            priority_activities_by_family[c.family_id].add(a)

    for family_id, members in campers_by_family.items():
        for activity in priority_activities_by_family[family_id]:
            priority_members = [c for c in members if activity in c.priorities]
            activity_sessions = [s for s in sessions if s.activity == activity]
            priority_present = _family_present_vars(
                model, {family_id: priority_members}, var_index, activity_sessions
            )
            relevant_sessions = [s for s in activity_sessions if (family_id, s) in priority_present]
            if len(relevant_sessions) < 2:
                continue  # can't be "split" across fewer than 2 sessions

            sum_present = sum(priority_present[(family_id, s)] for s in relevant_sessions)
            is_split = model.NewBoolVar(f"split[{family_id}|{activity.name}]")
            model.Add(sum_present >= 2).OnlyEnforceIf(is_split)
            model.Add(sum_present <= 1).OnlyEnforceIf(is_split.Not())

            adult_members = [c for c in priority_members if c.is_adult]
            for session in relevant_sessions:
                p = priority_present[(family_id, session)]
                adult_vars = [var_index.by_pair[(c, session)] for c in adult_members if (c, session) in var_index]
                adult_present = _reify_at_least_one(
                    model, adult_vars, f"adult_present[{family_id}|{activity.name}|{session.label}]"
                )

                unsupervised = model.NewBoolVar(f"unsupervised[{family_id}|{activity.name}|{session.label}]")
                model.AddBoolAnd([p, is_split, adult_present.Not()]).OnlyEnforceIf(unsupervised)
                model.AddBoolOr([p.Not(), is_split.Not(), adult_present]).OnlyEnforceIf(unsupervised.Not())
                result.unsupervised_split.append(unsupervised)

    return result


def tier0_expr(class2_vars: Class2Vars, weights: Tier0Weights = Tier0Weights()):
    """The Tier 0 objective: a severity-weighted sum of Class 2 violation
    indicators, mirroring validation.class2.score_tier0 exactly so the
    solver's own objective and the independent validator agree."""
    return (
        sum(class2_vars.missing_priority) * weights.missing_priority
        + (sum(class2_vars.family_conflict) + sum(class2_vars.unsupervised_split)) * weights.family_safety
        + sum(class2_vars.under_minimum) * weights.under_minimum
        + sum(class2_vars.unmet_compulsory) * weights.compulsory
    )


def solve_phase1(
    model: cp_model.CpModel,
    objective,
    time_limit_seconds: float | None = None,
    random_seed: int | None = None,
) -> tuple[cp_model.CpSolver, int]:
    """Minimise the Tier 0 objective. Returns the solved CpSolver (so
    variable values can still be inspected) and the achieved optimum."""
    model.Minimize(objective)
    solver = cp_model.CpSolver()
    if time_limit_seconds is not None:
        solver.parameters.max_time_in_seconds = time_limit_seconds
    if random_seed is not None:
        solver.parameters.random_seed = random_seed
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT Phase 1 solve failed with status {solver.StatusName(status)}")
    return solver, round(solver.ObjectiveValue())
