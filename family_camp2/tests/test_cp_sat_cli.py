import random
import time
from datetime import datetime, timedelta

from family_camp2 import cli
from family_camp2.config import EngineConfig
from family_camp2.domain import Activity, Camper, Session
from family_camp2.solvers.cp_sat import CpSatSolver
from family_camp2.validation.class1 import check_class1
from fixtures import SMALL_CAMP_JSON

DAY = datetime(2026, 8, 1, 9, 0)


def test_cli_solves_small_camp_fully_feasibly_with_cp_sat(capsys):
    exit_code = cli.main(["--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Feasible: True" in out
    assert "Tier 0 (violation) score: 0" in out


def _generate_medium_instance(num_campers=30, num_activities=6, num_sessions=10, seed=42):
    rng = random.Random(seed)

    activities = [
        Activity(
            name=f"Activity{i}",
            duration=timedelta(minutes=45),
            min_occupancy=1,
            max_occupancy=8,
        )
        for i in range(num_activities)
    ]

    sessions = []
    for i in range(num_sessions):
        day = i // 5
        hour = 9 + (i % 5)
        activity = activities[i % num_activities]
        sessions.append(
            Session(activity=activity, label=f"S{i}", start=DAY + timedelta(days=day, hours=hour - 9))
        )

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


def test_cp_sat_solves_medium_synthetic_instance_quickly_with_zero_class1_violations():
    activities, sessions, campers = _generate_medium_instance()

    start = time.monotonic()
    result = CpSatSolver(time_limit_seconds=20).solve(activities, sessions, campers, EngineConfig())
    elapsed = time.monotonic() - start

    assert elapsed < 30
    assert check_class1(result.timetable).is_clean
