import threading
import time

from family_camp2.config import EngineConfig
from family_camp2.solvers.cp_sat import CpSatSolver, _make_get_event, _ProgressCallback
from fixtures import load_small_camp


class FakeReporter:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def report(self, event):
        with self.lock:
            self.events.append(event)


def test_phase_boundary_events_appear_in_order_on_small_fixture():
    activities, sessions, campers = load_small_camp()
    reporter = FakeReporter()

    CpSatSolver(progress_reporter=reporter, progress_interval_seconds=60).solve(
        activities, sessions, campers, EngineConfig()
    )

    stages = [e.stage for e in reporter.events]
    assert stages.index("phase1") < stages.index("phase2") < stages.index("phase3")

    phase1_events = [e for e in reporter.events if e.stage == "phase1"]
    assert phase1_events[0].message == "started"
    assert "finished" in phase1_events[-1].message


def test_get_event_reports_no_solution_yet_before_any_incumbent_is_found():
    start = time.monotonic()
    callback = _ProgressCallback(start)
    get_event = _make_get_event(callback, "phase1", tier_index=0, start_time=start)

    event = get_event()

    assert event is not None
    assert event.stage == "phase1"
    assert "no solution" in event.message
    assert event.tier0_score is None
    assert event.tier1_score is None
    assert event.tier2_score is None


def test_get_event_tags_the_latest_solution_to_the_right_tier_field():
    start = time.monotonic()

    for tier_index, attr in [(0, "tier0_score"), (1, "tier1_score"), (2, "tier2_score")]:
        callback = _ProgressCallback(start)
        callback._latest = (3.5, 42.0)  # simulates on_solution_callback having fired
        get_event = _make_get_event(callback, f"phase{tier_index + 1}", tier_index, start_time=start)

        event = get_event()

        assert getattr(event, attr) is not None
        other_attrs = {"tier0_score", "tier1_score", "tier2_score"} - {attr}
        for other in other_attrs:
            assert getattr(event, other) is None


def test_omitting_progress_reporter_does_not_change_behaviour():
    activities, sessions, campers = load_small_camp()
    result = CpSatSolver().solve(activities, sessions, campers, EngineConfig())
    assert result.report is not None
