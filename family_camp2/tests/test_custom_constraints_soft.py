"""FR-95: soft custom-constraint scoring.

Unit tests for validation.custom_constraints.find_custom_constraint_violations,
plus cross-checks that CP-SAT's own soft-constraint modeling
(add_class2_indicators' custom_constraint indicators, tier0_expr's new
weighted term) and annealing's scoring (solvers.annealing.scoring.score)
both agree with the independent validator - the same pattern already used
for family-split (test_cp_sat_family_split.py) and hard custom constraints
(test_constraints_enforcement.py).
"""

from datetime import datetime, timedelta

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.constraints.rules import NoActivityBefore
from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable
from family_camp2.solvers.annealing.moves import State
from family_camp2.solvers.annealing.scoring import score
from family_camp2.solvers.cp_sat import add_class2_indicators, build_model, extract_timetable, solve_phase1, tier0_expr
from family_camp2.validation.class2 import Tier0Weights, check_class2
from family_camp2.validation.custom_constraints import find_custom_constraint_violations

DAY1 = datetime(2026, 8, 1, 9, 0)


def activity(name="Archery", minutes=60, min_occ=1, max_occ=10):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ)


def camper(name="Emma", family="022/Glen", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


# --- find_custom_constraint_violations (unit) ---


def test_finds_a_violation_when_the_camper_is_assigned_to_a_forbidden_session():
    archery = activity()
    early = Session(archery, "Morning", DAY1)
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="soft")

    timetable = Timetable(frozenset({Assignment(emma, early)}))
    violations = find_custom_constraint_violations(timetable, [early], [constraint])

    assert len(violations) == 1
    assert violations[0].camper == emma
    assert violations[0].session == early
    assert violations[0].constraint == constraint


def test_no_violation_when_the_camper_is_not_assigned_to_the_forbidden_session():
    archery = activity()
    late = Session(archery, "Afternoon", DAY1 + timedelta(hours=4))
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="soft")

    timetable = Timetable(frozenset({Assignment(emma, late)}))
    violations = find_custom_constraint_violations(timetable, [late], [constraint])

    assert violations == []


def test_hard_constraints_are_ignored_by_the_soft_violation_finder():
    """Hard violations are structurally impossible in a real solve (they're
    enforced via eligibility filtering) - if one somehow appears in a
    hand-built timetable, it must not be double-counted here as well."""
    archery = activity()
    early = Session(archery, "Morning", DAY1)
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="hard")

    timetable = Timetable(frozenset({Assignment(emma, early)}))
    violations = find_custom_constraint_violations(timetable, [early], [constraint])

    assert violations == []


# --- CP-SAT agreement ---


def test_cp_sat_avoids_a_soft_forbidden_session_when_a_compliant_alternative_exists():
    archery = activity(max_occ=4)
    early = Session(archery, "Morning", DAY1)
    late = Session(archery, "Afternoon", DAY1 + timedelta(hours=4))
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="soft")

    model, var_index = build_model([archery], [early, late], [emma])
    class2_vars = add_class2_indicators(model, var_index, [emma], [early, late], constraints=[constraint])
    objective = tier0_expr(class2_vars, Tier0Weights())
    solver, v0 = solve_phase1(model, objective)
    timetable = extract_timetable(solver, var_index)

    assert v0 == 0
    assert emma in timetable.campers_in(late)
    assert emma not in timetable.campers_in(early)

    report = check_class2(timetable, [emma], sessions=[early, late], constraints=[constraint])
    assert report.custom_constraint_violations == []


def test_cp_sat_prefers_a_missing_priority_over_a_soft_custom_constraint_violation():
    """REQUIREMENTS.md OQ-21: custom-constraint ranks ABOVE missing_priority,
    so when the only session that would satisfy a priority also violates a
    soft custom constraint, the solver leaves the priority unmet rather
    than accept the (more severe) soft violation."""
    archery = activity(max_occ=4)
    early = Session(archery, "Morning", DAY1)
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="soft")

    model, var_index = build_model([archery], [early], [emma])
    class2_vars = add_class2_indicators(model, var_index, [emma], [early], constraints=[constraint])
    objective = tier0_expr(class2_vars, Tier0Weights())
    solver, v0 = solve_phase1(model, objective)
    timetable = extract_timetable(solver, var_index)

    assert emma not in timetable.campers_in(early)

    report = check_class2(timetable, [emma], sessions=[early], constraints=[constraint])
    assert report.custom_constraint_violations == []
    assert len(report.missing_priorities) == 1
    assert v0 == Tier0Weights().missing_priority


# --- annealing agreement ---


def test_annealing_score_counts_a_soft_custom_constraint_violation():
    archery = activity(max_occ=4)
    early = Session(archery, "Morning", DAY1)
    emma = camper(priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="soft")

    state = State([emma], [early], [constraint])
    state._add(emma, early)

    weights = Tier0Weights()
    tier0_score, _, _ = score(state, [emma], [early], weights)

    assert tier0_score == weights.custom_constraint
