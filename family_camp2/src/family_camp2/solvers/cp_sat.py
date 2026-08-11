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
from math import gcd

from ortools.sat.python import cp_model

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable, sessions_overlap
from family_camp2.solvers.base import SolveResult
from family_camp2.solvers.registry import register
from family_camp2.validation.class2 import Tier0Weights
from family_camp2.validation.validator import validate

__all__ = [
    "VarIndex",
    "build_model",
    "extract_timetable",
    "Class2Vars",
    "add_class2_indicators",
    "tier0_expr",
    "tier1_expr",
    "tier2_expr",
    "solve_phase1",
    "solve_phase2",
    "solve_phase3",
    "CpSatParams",
    "CpSatSolver",
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
    solver._resolved_status = status  # StatusName() with no args is broken on some ortools/Python builds
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT Phase 1 solve failed with status {solver.StatusName(status)}")
    return solver, round(solver.ObjectiveValue())


# --- Tier 1 (FR-20/FR-21) and Tier 2 (FR-22) objectives ---


def _lcm(nums: list[int]) -> int:
    result = 1
    for n in nums:
        result = result * n // gcd(result, n)
    return result


def tier1_expr(var_index: VarIndex, campers: list[Camper]):
    """Integer-exact CP-SAT encoding of validation.tiers.score_tier1: sum,
    over campers, of the fraction of optional requests met.

    To keep this exact in integer arithmetic (CP-SAT has no native
    fractions), every camper's contribution is scaled by a common multiple
    of all distinct optional-request counts present, so each camper's
    per-activity weight (``scale // len(camper.optional)``) is an exact
    integer with no remainder. FR-15 (no duplicate activity, enforced
    structurally in build_model) guarantees a camper has at most one
    session of any given activity, so simply summing that camper's
    optional-activity assignment variables already counts distinct
    activities met - no separate de-duplication is needed here.
    """
    k_values = sorted({len(c.optional) for c in campers if c.optional})
    if not k_values:
        return 0

    scale = _lcm(k_values)
    terms = []
    for c in campers:
        if not c.optional:
            terms.append(scale)  # matches tiers.score_tier1's convention
            continue
        per_activity_weight = scale // len(c.optional)
        met_expr = sum(
            var_index.by_pair[(c, s)] for s in var_index.by_camper.get(c, []) if s.activity in c.optional
        )
        terms.append(per_activity_weight * met_expr)
    return sum(terms)


def tier2_expr(model: cp_model.CpModel, var_index: VarIndex, sessions: list[Session]):
    """A CP-SAT-friendly integer proxy for Tier 2 ("even use of parallel
    sessions"): the sum, over activities with more than one session, of
    (max occupancy - min occupancy) across that activity's sessions.

    This is deliberately simpler than exact population variance, which
    would require quadratic terms and per-activity-group rational scaling
    to normalise across differently-sized groups. Minimising the max-min
    range is a standard, exact-integer proxy that still drives the search
    towards evenly spread occupancy. The authoritative Tier 2 score
    reported to users always comes from the independent shared validator's
    true population-variance calculation (validation.tiers.score_tier2),
    not from this internal proxy.
    """
    by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        by_activity[s.activity].append(s)

    range_terms = []
    for activity, activity_sessions in by_activity.items():
        if len(activity_sessions) <= 1:
            continue
        occ_vars = []
        for s in activity_sessions:
            candidates = var_index.by_session.get(s, [])
            occ_expr = sum(var_index.by_pair[(c, s)] for c in candidates)
            occ_var = model.NewIntVar(0, activity.max_occupancy, f"occ[{activity.name}|{s.label}]")
            model.Add(occ_var == occ_expr)
            occ_vars.append(occ_var)

        max_var = model.NewIntVar(0, activity.max_occupancy, f"occ_max[{activity.name}]")
        min_var = model.NewIntVar(0, activity.max_occupancy, f"occ_min[{activity.name}]")
        model.AddMaxEquality(max_var, occ_vars)
        model.AddMinEquality(min_var, occ_vars)
        range_terms.append(max_var - min_var)

    if not range_terms:
        return 0
    return sum(range_terms)


# --- The three-phase lexicographic solve (DESIGN_OPTIONS.md §3.1) ---
#
# Each later phase pins earlier phases' results with an exact equality
# (tier0 == v0, tier1 == o1), not an inequality. Inequalities ("no worse
# than": tier0 <= v0, tier1 >= o1) look appealing when a phase stops at
# FEASIBLE rather than OPTIMAL (its time limit was hit before it could
# *prove* the best value, only find *a* good one) - matching an unproven
# exact value can be a much harder search than matching-or-beating it. But
# a regression test (test_cp_sat_solver.py,
# test_phase3_can_still_reach_the_true_tier1_optimum_given_a_conservative_o1)
# proved this actually breaks the core guarantee the three phases exist
# for: given a *conservative* (not-yet-proven) o1, the ">=" version let
# Phase 3 silently trade Tier 1 away, down towards that conservative
# floor, in exchange for a better Tier 2 - precisely the "sacrifice a
# higher tier for a lower one" behaviour lexicographic ordering exists to
# forbid (see test_naive_scalarised_objective_would_have_sacrificed_a_satisfiable_request).
# Equality is the correct, if less forgiving, choice: if a phase hasn't
# proven its result optimal, the honest options are to give it more time,
# or to accept that a later phase may fail to find any solution honouring
# that exact value - CpSatSolver.solve() falls back to the previous
# phase's already-valid result in that case, rather than crashing.


def _new_solver(time_limit_seconds: float | None, random_seed: int | None) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    if time_limit_seconds is not None:
        solver.parameters.max_time_in_seconds = time_limit_seconds
    if random_seed is not None:
        solver.parameters.random_seed = random_seed
    return solver


def solve_phase2(
    model: cp_model.CpModel,
    tier0_objective,
    v0: int,
    tier1_objective,
    time_limit_seconds: float | None = None,
    random_seed: int | None = None,
) -> tuple[cp_model.CpSolver, int]:
    """Fix Tier 0 at its Phase 1 optimum (see module note above on why
    this is an exact equality, not an inequality), then maximise Tier 1."""
    model.Add(tier0_objective == v0)
    model.Maximize(tier1_objective)
    solver = _new_solver(time_limit_seconds, random_seed)
    status = solver.Solve(model)
    solver._resolved_status = status
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT Phase 2 solve failed with status {solver.StatusName(status)}")
    return solver, round(solver.ObjectiveValue())


def solve_phase3(
    model: cp_model.CpModel,
    tier0_objective,
    v0: int,
    tier1_objective,
    o1: int,
    tier2_objective,
    time_limit_seconds: float | None = None,
    random_seed: int | None = None,
) -> cp_model.CpSolver:
    """Fix Tier 0 and Tier 1 at their achieved optima (see module note
    above), then minimise Tier 2."""
    model.Add(tier0_objective == v0)
    model.Add(tier1_objective == o1)
    model.Minimize(tier2_objective)
    solver = _new_solver(time_limit_seconds, random_seed)
    status = solver.Solve(model)
    solver._resolved_status = status
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT Phase 3 solve failed with status {solver.StatusName(status)}")
    return solver


@dataclass(frozen=True)
class CpSatParams:
    time_limit_seconds: float | None = None
    random_seed: int | None = None


@register("cp_sat")
class CpSatSolver:
    """Design A (DESIGN_OPTIONS.md §3): the full three-phase lexicographic solve.

    Takes ``time_limit_seconds``/``random_seed`` directly (rather than a
    single params object) so it can be constructed uniformly via
    ``registry.get_solver(name, **kwargs)`` from CLI flags (Step 15).
    """

    def __init__(self, time_limit_seconds: float | None = None, random_seed: int | None = None):
        self.params = CpSatParams(time_limit_seconds=time_limit_seconds, random_seed=random_seed)

    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config: EngineConfig,
    ) -> SolveResult:
        model, var_index = build_model(activities, sessions, campers)
        compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)
        class2_vars = add_class2_indicators(model, var_index, campers, sessions, compulsory)

        t0 = tier0_expr(class2_vars, config.tier0_weights)
        t1 = tier1_expr(var_index, campers)
        t2 = tier2_expr(model, var_index, sessions)

        kwargs = {
            "time_limit_seconds": self.params.time_limit_seconds,
            "random_seed": self.params.random_seed,
        }

        solver1, v0 = solve_phase1(model, t0, **kwargs)
        solver2, o1 = solve_phase2(model, t0, v0, t1, **kwargs)

        try:
            solver3 = solve_phase3(model, t0, v0, t1, o1, t2, **kwargs)
            final_solver = solver3
            phase3_status = solver3.StatusName(solver3._resolved_status)
        except RuntimeError:
            # Phase 3 pins Tier 0/Tier 1 with an exact equality (see the
            # module note above solve_phase2) and can fail to find *any*
            # solution honouring it within its time budget at large scale,
            # even though Phase 2's own solution already satisfies that
            # exact pin by construction. Fall back to it rather than
            # losing an already-valid result to a crash - it just won't
            # have been optimised for Tier 2 evenness.
            final_solver = solver2
            phase3_status = "SKIPPED (found no solution in time; used Phase 2's result instead)"

        timetable = extract_timetable(final_solver, var_index)
        report = validate(timetable, campers, sessions, tier0_weights=config.tier0_weights, compulsory=compulsory)

        diagnostics = {
            "solver": "cp_sat",
            "phase1_status": solver1.StatusName(solver1._resolved_status),
            "phase2_status": solver2.StatusName(solver2._resolved_status),
            "phase3_status": phase3_status,
            "tier0_optimum": v0,
            "tier1_optimum": o1,
            "tier2_proxy_value": t2 if isinstance(t2, int) else final_solver.Value(t2),
        }
        return SolveResult(timetable=timetable, report=report, diagnostics=diagnostics)
