"""Solver-agnostic progress reporting (REQUIREMENTS.md §4.6, FR-60/FR-61).

Every solver's default is a no-op (``NullProgressReporter``), so reporting
never costs anything unless requested (NFR-9). ``PeriodicHeartbeat`` makes
reporting genuinely wall-clock-cadenced (60s default) rather than tied to
how often a solver happens to find something new to report - a plain
"report when something improves" hook would go silent during a long
stall in the search, leaving no signal that the run is still alive.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, TextIO

__all__ = [
    "ProgressEvent",
    "ProgressReporter",
    "NullProgressReporter",
    "PrintProgressReporter",
    "PeriodicHeartbeat",
]


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    message: str
    elapsed_seconds: float
    tier0_score: int | None = None
    tier1_score: float | None = None
    tier2_score: float | None = None


class ProgressReporter(Protocol):
    def report(self, event: ProgressEvent) -> None: ...


class NullProgressReporter:
    def report(self, event: ProgressEvent) -> None:
        pass


class PrintProgressReporter:
    """Writes one formatted line per event to a resolved destination.

    ``destination`` is resolved once, at construction, not per call (a
    single write per report is the whole cost - NFR-9): ``"-"`` resolves
    to stdout (the default); anything else is opened as a file path for
    writing.
    """

    def __init__(self, destination: str = "-"):
        self._owns_stream = destination != "-"
        self._stream: TextIO = sys.stdout if destination == "-" else open(Path(destination), "w")

    def report(self, event: ProgressEvent) -> None:
        parts = [f"[{event.elapsed_seconds:8.1f}s]", f"{event.stage}:", event.message]
        scores = []
        if event.tier0_score is not None:
            scores.append(f"tier0={event.tier0_score}")
        if event.tier1_score is not None:
            scores.append(f"tier1={event.tier1_score:.2f}")
        if event.tier2_score is not None:
            scores.append(f"tier2={event.tier2_score:.4f}")
        if scores:
            parts.append(f"({', '.join(scores)})")
        print(" ".join(parts), file=self._stream, flush=True)

    def close(self) -> None:
        if self._owns_stream:
            self._stream.close()


class PeriodicHeartbeat:
    """Runs a background daemon thread that calls ``get_event`` and reports
    its result (if not None) every ``interval_seconds``, for as long as
    it's active - independent of whatever else is happening concurrently
    (e.g. a blocking ``CpSolver.Solve()`` call on the calling thread).

    Used as a context manager::

        with PeriodicHeartbeat(reporter, 60, get_event):
            solver.Solve(model, callback)

    Uses ``threading.Event.wait(interval)`` rather than ``time.sleep`` as
    its timer: this doubles as the shutdown signal, so ``__exit__``
    interrupts a pending wait immediately instead of blocking for up to a
    full interval (or forever, if the wait mechanism can't be woken) for
    the thread to notice it should stop. Tests can use a short
    ``interval_seconds`` to keep this fast without needing a fake clock.
    """

    def __init__(
        self,
        reporter: ProgressReporter,
        interval_seconds: float,
        get_event: Callable[[], ProgressEvent | None],
    ):
        self._reporter = reporter
        self._interval = interval_seconds
        self._get_event = get_event
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            event = self._get_event()
            if event is not None:
                self._reporter.report(event)

    def __enter__(self) -> "PeriodicHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stop.set()
        self._thread.join()
