"""End-to-end proof that a hard custom constraint (REQUIREMENTS.md
§4.10, FR-94) is genuinely enforced by both solvers, via the shared
eligibility-filtering mechanism (constraints.base.hard_rules_by_camper) -
not just that the data reaches config.constraints (test_cli.py already
covers that plumbing)."""

from datetime import datetime, timedelta

from family_camp2.config import EngineConfig
from family_camp2.constraints.base import ConstraintInstance
from family_camp2.constraints.rules import NoActivitiesOnDay, NoActivityBefore
from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.annealing.solver import AnnealingSolver
from family_camp2.solvers.cp_sat import CpSatSolver

DAY1 = datetime(2026, 8, 1, 9, 0)
DAY2 = datetime(2026, 8, 2, 9, 0)


def _annealing():
    return AnnealingSolver(num_chains=4, iterations_per_chain=500, random_seed=1)


def test_hard_no_activity_before_blocks_the_only_eligible_session_in_both_solvers():
    """Emma's only priority-satisfying session is too early - a hard
    constraint means neither solver may ever assign her to it, so it
    surfaces as an ordinary missing_priority violation (FR-94), not a
    crash or a silently dropped priority."""
    archery = Activity("Archery", timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    early_session = Session(activity=archery, label="Morning", start=DAY1)

    emma = Camper(name="Emma", family_id="022/Glen", age=10, age_group="Cub", priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="hard")
    config = EngineConfig(constraints=(constraint,))

    for solver in (CpSatSolver(), _annealing()):
        result = solver.solve([archery], [early_session], [emma], config)

        assert emma not in result.timetable.campers_in(early_session)
        assert len(result.report.class2.missing_priorities) == 1
        assert result.report.class2.missing_priorities[0].camper == emma
        assert result.report.class2.missing_priorities[0].activity == archery


def test_hard_constraint_does_not_affect_an_untargeted_camper():
    """The same setup, but for a camper the constraint doesn't target -
    they should be assigned normally, proving the restriction is scoped
    to its actual target, not applied camp-wide by accident."""
    archery = Activity("Archery", timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    early_session = Session(activity=archery, label="Morning", start=DAY1)

    emma = Camper(name="Emma", family_id="022/Glen", age=10, age_group="Cub", priorities=(archery,))
    sam = Camper(name="Sam", family_id="022/Glen", age=9, age_group="Cub", priorities=(archery,))
    constraint = ConstraintInstance(targets=(emma,), rule=NoActivityBefore(time="11:00"), severity="hard")
    config = EngineConfig(constraints=(constraint,))

    for solver in (CpSatSolver(), _annealing()):
        result = solver.solve([archery], [early_session], [emma, sam], config)

        assert sam in result.timetable.campers_in(early_session)
        assert not any(v.camper == sam for v in result.report.class2.missing_priorities)


def test_hard_no_activities_on_day_applies_to_every_family_member():
    """A family-level target (no single camper_name) forbids the session
    for every member, not just one."""
    craft = Activity("Craft", timedelta(minutes=45), min_occupancy=1, max_occupancy=6)
    day1_session = Session(activity=craft, label="A", start=DAY1)
    day2_session = Session(activity=craft, label="B", start=DAY2)

    chris = Camper(name="Chris", family_id="022/Glen", age=40, age_group="Adult", optional=(craft,))
    sam = Camper(name="Sam", family_id="022/Glen", age=9, age_group="Cub", optional=(craft,))
    constraint = ConstraintInstance(targets=(chris, sam), rule=NoActivitiesOnDay(day=2), severity="hard")
    config = EngineConfig(constraints=(constraint,))

    for solver in (CpSatSolver(), _annealing()):
        result = solver.solve([craft], [day1_session, day2_session], [chris, sam], config)

        assert result.timetable.campers_in(day2_session) == set()
