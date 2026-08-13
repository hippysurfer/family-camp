import time

from family_camp2.progress import (
    NullProgressReporter,
    PeriodicHeartbeat,
    PrintProgressReporter,
    ProgressEvent,
)


class FakeReporter:
    def __init__(self):
        self.events = []

    def report(self, event):
        self.events.append(event)


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met within timeout")


def test_null_progress_reporter_is_a_no_op():
    NullProgressReporter().report(
        ProgressEvent(stage="x", message="y", elapsed_seconds=1.0)
    )  # must not raise


def test_print_progress_reporter_writes_to_stdout_like_stream(capsys):
    reporter = PrintProgressReporter("-")
    reporter.report(ProgressEvent(stage="phase1", message="started", elapsed_seconds=12.3, tier0_score=0))

    out = capsys.readouterr().out
    assert "phase1" in out
    assert "started" in out
    assert "tier0=0" in out


def test_print_progress_reporter_writes_to_a_file(tmp_path):
    path = tmp_path / "progress.log"
    reporter = PrintProgressReporter(str(path))
    reporter.report(ProgressEvent(stage="restarts", message="chain 1/8 finished", elapsed_seconds=5.0))
    reporter.close()

    content = path.read_text()
    assert "restarts" in content
    assert "chain 1/8 finished" in content


def test_periodic_heartbeat_reports_repeatedly_on_a_short_interval():
    reporter = FakeReporter()
    call_count = {"n": 0}

    def get_event():
        call_count["n"] += 1
        return ProgressEvent(stage="phase2", message="heartbeat", elapsed_seconds=float(call_count["n"]))

    heartbeat = PeriodicHeartbeat(reporter, interval_seconds=0.02, get_event=get_event)

    with heartbeat:
        _wait_until(lambda: len(reporter.events) >= 3)

    # __exit__ has returned: the thread must have stopped promptly, not be left running.
    assert not heartbeat._thread.is_alive()
    assert reporter.events[0].stage == "phase2"


def test_periodic_heartbeat_skips_reporting_when_get_event_returns_none():
    reporter = FakeReporter()

    heartbeat = PeriodicHeartbeat(reporter, interval_seconds=0.02, get_event=lambda: None)

    with heartbeat:
        time.sleep(0.07)  # several intervals' worth

    assert reporter.events == []


def test_periodic_heartbeat_exit_does_not_block_waiting_for_a_long_interval():
    """__exit__ must interrupt a pending wait immediately, not block for up
    to the full interval (this is the whole point of using Event.wait
    rather than a plain sleep as the timer)."""
    heartbeat = PeriodicHeartbeat(FakeReporter(), interval_seconds=999, get_event=lambda: None)

    start = time.monotonic()
    with heartbeat:
        time.sleep(0.01)  # let the thread actually start and enter its wait
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
