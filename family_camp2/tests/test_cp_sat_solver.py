from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.cp_sat import (
    CpSatSolver,
    add_class2_indicators,
    build_model,
    extract_timetable,
    solve_phase1,
    solve_phase2,
    solve_phase3,
    tier0_expr,
    tier1_expr,
    tier2_expr,
)
from fixtures import load_small_camp

DAY = datetime(2026, 8, 1)


def _craft_attendee_count(timetable, craft, campers):
    return sum(1 for c in campers if any(s.activity == craft for s in timetable.sessions_of(c)))


def _build_lexicographic_trap():
    """Three campers who all optionally want the same activity, which runs
    as two sessions of capacity 2 each (total capacity 4, so all three CAN
    be seated, but never evenly: the only way to fit all three is a 2/1
    split, range=1). A single scalarised objective that weighs "one missed
    optional request" against "one unit of spread range" too cheaply will
    happily sacrifice a satisfiable request for a perfectly even 1/1 split
    among only two attendees - which strict lexicographic ordering must
    never do, since Tier 1 (FR-20) has to be maximised unconditionally
    before Tier 2 is considered at all.

    Hand-verified optimum for Minimize(-1*tier1 + 2*tier2) (all craft
    session/attendee combinations enumerated):
      3 attend (2+1 split, the only feasible way to fit 3): tier1=3, tier2=1 -> -1
      2 attend (1+1 split):                                 tier1=2, tier2=0 -> -2  (unique minimum)
      2 attend (2+0 split):                                 tier1=2, tier2=2 -> +2
      1 attends:                                             tier1=1, tier2=1 -> +1
      0 attend:                                              tier1=0, tier2=0 ->  0
    So the naive objective's unique optimum sacrifices one attendee to get
    a perfectly even split, while the true lexicographic optimum keeps all
    three (tier1=3) and only then minimises spread among tier1=3 solutions
    (forced to range=1, since 3 people can never split evenly across two
    capacity-2 sessions).
    """
    reg = Activity("Reg", timedelta(minutes=60), min_occupancy=1, max_occupancy=5)
    craft = Activity("CraftX", timedelta(minutes=60), min_occupancy=1, max_occupancy=2)

    reg_session = Session(activity=reg, label="Reg", start=DAY + timedelta(hours=8))
    craft_morning = Session(activity=craft, label="Morning", start=DAY + timedelta(hours=10))
    craft_afternoon = Session(activity=craft, label="Afternoon", start=DAY + timedelta(hours=14))

    campers = [
        Camper(name=n, family_id=f"F{n}", age=30, age_group="Adult", priorities=(reg,), optional=(craft,))
        for n in ("Alice", "Bob", "Carol")
    ]

    activities = [reg, craft]
    sessions = [reg_session, craft_morning, craft_afternoon]
    return activities, sessions, campers, craft


def test_phased_solve_maximises_tier1_before_ever_considering_tier2():
    activities, sessions, campers, craft = _build_lexicographic_trap()

    result = CpSatSolver().solve(activities, sessions, campers, EngineConfig())

    assert result.report.is_feasible  # Reg is trivially satisfiable for all three
    attendees = _craft_attendee_count(result.timetable, craft, campers)
    assert attendees == 3  # nobody's satisfiable optional request is sacrificed
    assert result.diagnostics["tier0_optimum"] == 0
    assert result.diagnostics["tier1_optimum"] == 3  # scale=1 here (each camper has exactly 1 optional request)
    assert result.diagnostics["tier2_proxy_value"] == 1  # the best achievable spread once all 3 attend


def test_naive_scalarised_objective_would_have_sacrificed_a_satisfiable_request():
    """Proves the three-phase solve isn't accidentally equivalent to a
    single weighted objective: a plausible-looking single-pass combination
    (-tier1 + 2*tier2) provably picks a worse outcome (see
    _build_lexicographic_trap's docstring for the hand-verified enumeration)."""
    activities, sessions, campers, craft = _build_lexicographic_trap()

    model, var_index = build_model(activities, sessions, campers)
    class2_vars = add_class2_indicators(model, var_index, campers, sessions)
    t1 = tier1_expr(var_index, campers)
    t2 = tier2_expr(model, var_index, sessions)

    model.Minimize(-1 * t1 + 2 * t2)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    timetable = extract_timetable(solver, var_index)
    attendees = _craft_attendee_count(timetable, craft, campers)
    assert attendees == 2  # the naive objective sacrifices one satisfiable request


def test_phase3_pins_tier1_exactly_even_when_a_better_value_is_reachable():
    """Regression guard for a real design mistake made and caught during
    development (see the module-level note above solve_phase2 in
    cp_sat.py): Phase 3 must pin Tier 1 with an *exact* equality, not a
    "no worse than" inequality. An inequality looks appealing when Phase 2
    stops at FEASIBLE rather than OPTIMAL (matching an unproven exact
    value can be a harder search than matching-or-beating it), but it lets
    Phase 3 silently trade Tier 1 away for a better Tier 2 whenever a
    strictly-better Tier 1 value is reachable but happens to force a worse
    Tier 2 - exactly the "sacrifice a higher tier for a lower one"
    behaviour lexicographic ordering exists to forbid. Here, a truly
    reachable, strictly-better Tier 1 value exists (true_o1); Phase 3 must
    still land exactly on the deliberately-lowered value it was given."""
    activities, sessions, campers, craft = _build_lexicographic_trap()

    model, var_index = build_model(activities, sessions, campers)
    class2_vars = add_class2_indicators(model, var_index, campers, sessions)
    t0 = tier0_expr(class2_vars)
    t1 = tier1_expr(var_index, campers)
    t2 = tier2_expr(model, var_index, sessions)

    _, v0 = solve_phase1(model, t0)
    _, true_o1 = solve_phase2(model, t0, v0, t1)

    conservative_o1 = true_o1 - 1  # simulates Phase 2 having stopped early
    solver3 = solve_phase3(model, t0, v0, t1, conservative_o1, t2)

    assert solver3.Value(t1) == conservative_o1  # exact pin honoured, not silently improved


def test_solver_runs_end_to_end_on_small_camp_fixture():
    activities, sessions, campers = load_small_camp()
    result = CpSatSolver().solve(activities, sessions, campers, EngineConfig())

    assert result.report is not None
    assert result.diagnostics["phase3_status"] in ("OPTIMAL", "FEASIBLE")


def test_solve_falls_back_to_phase2_result_when_phase3_finds_nothing(monkeypatch):
    """If Phase 3 can't find any solution honouring the exact Tier 0/Tier 1
    pin within its time budget (observed on a real ~283-camper instance),
    the overall solve must not crash - it should fall back to Phase 2's
    already-valid (just not Tier-2-optimised) result."""
    import family_camp2.solvers.cp_sat as cp_sat_module

    def _always_fail(*args, **kwargs):
        raise RuntimeError("CP-SAT Phase 3 solve failed with status UNKNOWN")

    monkeypatch.setattr(cp_sat_module, "solve_phase3", _always_fail)

    activities, sessions, campers = load_small_camp()
    result = CpSatSolver().solve(activities, sessions, campers, EngineConfig())

    assert result.report is not None
    assert "SKIPPED" in result.diagnostics["phase3_status"]
    assert result.report.tier0_score == result.diagnostics["tier0_optimum"]
