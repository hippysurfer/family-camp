"""Shared test-only fixtures and helpers (not part of the installed package)."""

import random
from datetime import datetime, timedelta
from pathlib import Path

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.io.json_loader import load_json
from family_camp2.solvers.base import SolveResult
from family_camp2.validation.validator import validate

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SMALL_CAMP_JSON = FIXTURES_DIR / "small_camp.json"


def load_small_camp() -> tuple[list[Activity], list[Session], list[Camper]]:
    """Discards small_camp.json's (empty) constraints list - most callers
    don't care, and there'd be dozens of call sites to update across the
    test suite for a value they'd never use. Use load_json directly for a
    test that specifically needs the fourth element."""
    activities, sessions, campers, _constraints = load_json(SMALL_CAMP_JSON)
    return activities, sessions, campers


def generate_medium_instance(num_campers=30, num_activities=6, num_sessions=10, seed=42):
    """A synthetic ~30-camper/6-activity/10-session instance, used to check
    both solvers stay fast at a scale still well under NFR-1's upper bound
    (500 campers / 30 activities / 50 sessions)."""
    rng = random.Random(seed)
    day = datetime(2026, 8, 1, 9, 0)

    activities = [
        Activity(name=f"Activity{i}", duration=timedelta(minutes=45), min_occupancy=1, max_occupancy=8)
        for i in range(num_activities)
    ]

    sessions = []
    for i in range(num_sessions):
        d = i // 5
        hour = 9 + (i % 5)
        activity = activities[i % num_activities]
        sessions.append(Session(activity=activity, label=f"S{i}", start=day + timedelta(days=d, hours=hour - 9)))

    campers = []
    for i in range(num_campers):
        family_id = f"F{i // 2}"
        age = rng.choice([8, 10, 12, 16, 40])
        num_priorities = rng.randint(1, 2)
        num_optional = rng.randint(0, 2)
        chosen = rng.sample(activities, k=min(num_priorities + num_optional, num_activities))
        priorities = tuple(chosen[:num_priorities])
        optional = tuple(chosen[num_priorities : num_priorities + num_optional])
        campers.append(
            Camper(
                name=f"Camper{i}",
                family_id=family_id,
                age=age,
                age_group="Adult" if age >= 18 else "Cub",
                priorities=priorities,
                optional=optional,
            )
        )

    return activities, sessions, campers


class FakeSolver:
    """A trivial Solver that never assigns anyone to anything.

    Exists purely to prove the Solver interface, registry, and (later) CLI
    wiring work end-to-end before either real solver (CP-SAT, annealing) is
    built.
    """

    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config,
    ) -> SolveResult:
        timetable = Timetable()
        compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)
        report = validate(
            timetable,
            campers,
            sessions,
            tier0_weights=config.tier0_weights,
            compulsory=compulsory,
        )
        return SolveResult(timetable=timetable, report=report, diagnostics={"solver": "fake"})
