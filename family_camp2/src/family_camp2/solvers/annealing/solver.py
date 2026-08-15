"""Design B: the simulated-annealing solver (DESIGN_OPTIONS.md §4.1).

``run_chain`` is a single evolving chain. ``run_restarts`` runs many
independent chains (optionally in parallel, mirroring the current
system's use of ``multiprocessing`` for fitness evaluation - see DESIGN.md
§2.3) from independent constructive seeds (seed.py) and keeps the best
result across all of them, per DESIGN_OPTIONS.md §4.1's restart strategy -
the main lever Design B has for compensating for any single chain's lack
of an optimality guarantee. ``AnnealingSolver`` wraps this as a ``Solver``.
"""

from __future__ import annotations

import multiprocessing
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field

from family_camp2.config import EngineConfig
from family_camp2.constraints.base import ConstraintInstance
from family_camp2.domain import Activity, Camper, Session
from family_camp2.progress import NullProgressReporter, ProgressEvent, ProgressReporter
from family_camp2.solvers.annealing.moves import (
    State,
    assign_family,
    fix_lone_adult_split,
    fix_unsupervised_split,
    move_family,
    remove_family,
    swap_families,
)
from family_camp2.solvers.annealing.scoring import Score, acceptance_probability, compare, score
from family_camp2.solvers.annealing.seed import greedy_seed
from family_camp2.solvers.base import SolveResult
from family_camp2.solvers.registry import register
from family_camp2.validation.class2 import Tier0Weights
from family_camp2.validation.validator import validate

__all__ = ["CoolingSchedule", "run_chain", "run_restarts", "AnnealingParams", "AnnealingSolver"]

_MOVE_KINDS = ("assign", "move", "swap", "remove", "fix_split", "fix_lone_adult")


@dataclass(frozen=True)
class CoolingSchedule:
    initial_temperature: float = 100.0
    cooling_rate: float = 0.995  # multiplicative decay applied once per iteration


def _sessions_of_family(state: State, family_id: str, campers_by_family: dict[str, list[Camper]]) -> list[Session]:
    members = campers_by_family.get(family_id, [])
    return [s for c in members for s in state.assigned_sessions[c]]


def _propose_move(
    rng: random.Random,
    state: State,
    families: list[str],
    sessions: list[Session],
    sessions_by_activity: dict[Activity, list[Session]],
    campers_by_family: dict[str, list[Camper]],
) -> State | None:
    if not families or not sessions:
        return None

    kind = rng.choice(_MOVE_KINDS)

    if kind == "assign":
        family_id = rng.choice(families)
        session = rng.choice(sessions)
        return assign_family(state, family_id, session, campers_by_family)

    if kind == "move":
        family_id = rng.choice(families)
        candidate_sessions = _sessions_of_family(state, family_id, campers_by_family)
        if not candidate_sessions:
            return None
        from_session = rng.choice(candidate_sessions)
        parallel = [s for s in sessions_by_activity[from_session.activity] if s != from_session]
        if not parallel:
            return None
        to_session = rng.choice(parallel)
        return move_family(state, family_id, from_session, to_session, campers_by_family)

    if kind == "swap":
        family_a = rng.choice(families)
        family_b = rng.choice(families)
        if family_a == family_b:
            return None
        sessions_a = _sessions_of_family(state, family_a, campers_by_family)
        sessions_b = _sessions_of_family(state, family_b, campers_by_family)
        if not sessions_a or not sessions_b:
            return None
        return swap_families(state, family_a, rng.choice(sessions_a), family_b, rng.choice(sessions_b), campers_by_family)

    if kind == "remove":
        family_id = rng.choice(families)
        candidate_sessions = _sessions_of_family(state, family_id, campers_by_family)
        if not candidate_sessions:
            return None
        session = rng.choice(candidate_sessions)
        return remove_family(state, family_id, session, campers_by_family)

    if kind == "fix_split":
        family_id = rng.choice(families)
        session = rng.choice(sessions)
        return fix_unsupervised_split(state, family_id, session, campers_by_family)

    if kind == "fix_lone_adult":
        family_id = rng.choice(families)
        session = rng.choice(sessions)
        return fix_lone_adult_split(state, family_id, session, campers_by_family)

    return None  # pragma: no cover - _MOVE_KINDS is exhaustive


_DEADLINE_CHECK_INTERVAL = 100  # iterations between wall-clock checks, to keep the check's own overhead negligible


def run_chain(
    initial_state: State,
    campers: list[Camper],
    sessions: list[Session],
    campers_by_family: dict[str, list[Camper]],
    tier0_weights: Tier0Weights,
    compulsory: frozenset[Activity],
    cooling: CoolingSchedule,
    seed: int,
    iterations: int,
    deadline: float | None = None,
) -> State:
    """Run one simulated-annealing chain from initial_state for up to the
    given number of iterations (or until `deadline`, a `time.monotonic()`
    timestamp, if given - checked periodically rather than every iteration
    to keep its overhead negligible), and return the best state seen (per
    `compare`), not necessarily the state the chain ends on - the whole
    point of accepting occasional worse moves is to escape local optima,
    so the final state isn't guaranteed to be the best one visited."""

    rng = random.Random(seed)
    families = sorted(campers_by_family)
    sessions_by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        sessions_by_activity[s.activity].append(s)

    current = initial_state
    current_score: Score = score(current, campers, sessions, tier0_weights, compulsory)
    best, best_score = current, current_score
    temperature = cooling.initial_temperature

    for i in range(iterations):
        if deadline is not None and i % _DEADLINE_CHECK_INTERVAL == 0 and time.monotonic() > deadline:
            break

        candidate = _propose_move(rng, current, families, sessions, sessions_by_activity, campers_by_family)
        if candidate is not None:
            candidate_score = score(candidate, campers, sessions, tier0_weights, compulsory)
            if rng.random() < acceptance_probability(current_score, candidate_score, temperature):
                current, current_score = candidate, candidate_score
                if compare(current_score, best_score) < 0:
                    best, best_score = current, current_score
        temperature *= cooling.cooling_rate

    return best


def _run_single_chain_from_seed(
    activities: list[Activity],
    sessions: list[Session],
    campers: list[Camper],
    campers_by_family: dict[str, list[Camper]],
    tier0_weights: Tier0Weights,
    compulsory: frozenset[Activity],
    cooling: CoolingSchedule,
    seed: int,
    iterations: int,
    deadline: float | None,
    constraints: list[ConstraintInstance] = (),
) -> State:
    """Module-level (picklable) helper so multiprocessing.Pool can call it."""
    rng = random.Random(seed)
    initial = greedy_seed(activities, sessions, campers, campers_by_family, rng, constraints)
    return run_chain(
        initial, campers, sessions, campers_by_family, tier0_weights, compulsory, cooling, seed, iterations, deadline
    )


def _run_single_chain_from_seed_args(args: tuple) -> tuple[int, State]:
    """Adapter for pool.imap_unordered, which (unlike starmap) only passes
    one argument per call - returns (seed, state) so the seed survives the
    call even though imap_unordered yields results in completion order,
    not submission order."""
    state = _run_single_chain_from_seed(*args)
    seed = args[7]  # (activities, sessions, campers, campers_by_family, tier0_weights, compulsory, cooling, seed, ...)
    return seed, state


def _report_chain_results(
    results,
    total: int,
    campers: list[Camper],
    sessions: list[Session],
    tier0_weights: Tier0Weights,
    compulsory: frozenset[Activity],
    progress_reporter: ProgressReporter,
    start_time: float,
) -> dict[int, State]:
    """Consumes an iterable of (seed, state) pairs as they arrive - reports
    a progress event for each. Chain-completion, not a wall-clock timer, is
    the progress unit here: chains run in separate worker processes (see
    the module note above run_restarts), so a PeriodicHeartbeat like
    CP-SAT's isn't directly usable without a cross-process progress queue
    - and measured on real ~283-camper data, a full multi-chain run
    completes in a couple of minutes, i.e. individual chains land well
    inside the OQ-9 60-second default cadence in practice anyway."""
    results_by_seed: dict[int, State] = {}
    completed = 0
    for seed, state in results:
        completed += 1
        results_by_seed[seed] = state
        chain_score = score(state, campers, sessions, tier0_weights, compulsory)
        progress_reporter.report(
            ProgressEvent(
                stage="restarts",
                message=f"chain seed={seed} finished ({completed}/{total})",
                elapsed_seconds=time.monotonic() - start_time,
                tier0_score=chain_score[0],
                tier1_score=-chain_score[1],
                tier2_score=chain_score[2],
            )
        )
    return results_by_seed


def run_restarts(
    activities: list[Activity],
    sessions: list[Session],
    campers: list[Camper],
    campers_by_family: dict[str, list[Camper]],
    tier0_weights: Tier0Weights,
    compulsory: frozenset[Activity],
    cooling: CoolingSchedule,
    seeds: list[int],
    iterations: int,
    deadline: float | None = None,
    use_multiprocessing: bool = True,
    progress_reporter: ProgressReporter = NullProgressReporter(),
    constraints: list[ConstraintInstance] = (),
) -> tuple[State, list[Score]]:
    """Run one independently-seeded chain per entry in `seeds` (each
    starting from its own greedy_seed construction), optionally in
    parallel, and return the best resulting state across all of them (per
    `compare`) plus every chain's own final score (for diagnostics)."""

    start_time = time.monotonic()
    call_args = [
        (
            activities, sessions, campers, campers_by_family, tier0_weights, compulsory, cooling, seed,
            iterations, deadline, constraints,
        )
        for seed in seeds
    ]

    progress_reporter.report(
        ProgressEvent(stage="restarts", message=f"started ({len(seeds)} chains)", elapsed_seconds=0.0)
    )

    if use_multiprocessing and len(seeds) > 1:
        with multiprocessing.Pool() as pool:
            results = pool.imap_unordered(_run_single_chain_from_seed_args, call_args)
            results_by_seed = _report_chain_results(
                results, len(seeds), campers, sessions, tier0_weights, compulsory, progress_reporter, start_time
            )
    else:
        results = ((a[7], _run_single_chain_from_seed(*a)) for a in call_args)
        results_by_seed = _report_chain_results(
            results, len(seeds), campers, sessions, tier0_weights, compulsory, progress_reporter, start_time
        )

    states = [results_by_seed[seed] for seed in seeds]
    scores = [score(s, campers, sessions, tier0_weights, compulsory) for s in states]
    best_index = min(range(len(states)), key=lambda i: scores[i])

    progress_reporter.report(
        ProgressEvent(
            stage="restarts",
            message="all chains finished",
            elapsed_seconds=time.monotonic() - start_time,
            tier0_score=scores[best_index][0],
            tier1_score=-scores[best_index][1],
            tier2_score=scores[best_index][2],
        )
    )
    return states[best_index], scores


@dataclass(frozen=True)
class AnnealingParams:
    time_limit_seconds: float | None = None
    random_seed: int | None = None
    num_chains: int = 8
    iterations_per_chain: int = 2000
    cooling: CoolingSchedule = field(default_factory=CoolingSchedule)
    progress_reporter: ProgressReporter = field(default_factory=NullProgressReporter)


@register("annealing")
class AnnealingSolver:
    """Design B (DESIGN_OPTIONS.md §4): multi-restart simulated annealing.

    Takes the same ``time_limit_seconds``/``random_seed``/``progress_reporter``
    constructor kwargs as ``CpSatSolver`` (plus annealing-specific tuning
    knobs) so it can be constructed uniformly via
    ``registry.get_solver(name, **kwargs)``. Unlike CP-SAT there's no
    ``progress_interval_seconds`` - progress is reported per chain
    completion (see the module note above ``run_restarts``), not on a
    fixed timer.
    """

    def __init__(
        self,
        time_limit_seconds: float | None = None,
        random_seed: int | None = None,
        num_chains: int = 8,
        iterations_per_chain: int = 2000,
        cooling: CoolingSchedule | None = None,
        progress_reporter: ProgressReporter = NullProgressReporter(),
    ):
        self.params = AnnealingParams(
            time_limit_seconds=time_limit_seconds,
            random_seed=random_seed,
            num_chains=num_chains,
            iterations_per_chain=iterations_per_chain,
            cooling=cooling or CoolingSchedule(),
            progress_reporter=progress_reporter,
        )

    def solve(
        self,
        activities: list[Activity],
        sessions: list[Session],
        campers: list[Camper],
        config: EngineConfig,
    ) -> SolveResult:
        campers_by_family: dict[str, list[Camper]] = defaultdict(list)
        for c in campers:
            campers_by_family[c.family_id].append(c)
        campers_by_family = dict(campers_by_family)

        compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)

        base_seed = self.params.random_seed if self.params.random_seed is not None else 0
        seeds = [base_seed + i for i in range(self.params.num_chains)]

        deadline = None
        if self.params.time_limit_seconds is not None:
            deadline = time.monotonic() + self.params.time_limit_seconds

        best_state, chain_scores = run_restarts(
            activities,
            sessions,
            campers,
            campers_by_family,
            config.tier0_weights,
            compulsory,
            self.params.cooling,
            seeds,
            self.params.iterations_per_chain,
            deadline=deadline,
            progress_reporter=self.params.progress_reporter,
            constraints=config.constraints,
        )

        timetable = best_state.to_timetable()
        report = validate(timetable, campers, sessions, tier0_weights=config.tier0_weights, compulsory=compulsory)

        diagnostics = {
            "solver": "annealing",
            "num_chains": self.params.num_chains,
            "iterations_per_chain": self.params.iterations_per_chain,
            "seeds": seeds,
            "chain_scores": chain_scores,
        }
        return SolveResult(timetable=timetable, report=report, diagnostics=diagnostics)
