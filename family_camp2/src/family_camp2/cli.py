"""Command-line entry point for the family_camp2 scheduling engine."""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from family_camp2.config import load_config
from family_camp2.io.json_loader import load_json
from family_camp2.io.legacy_cache_loader import load_legacy_cache
from family_camp2.io.schedule_export import dump_schedule_csv, dump_schedule_json
from family_camp2.progress import PrintProgressReporter
from family_camp2.reporting import (
    render_activity_roster,
    render_family_itinerary,
    render_idle_report,
    render_unfeasible_families_report,
    render_unmet_optional_report,
)
from family_camp2.solvers.registry import get_solver
from family_camp2.validation.feasibility import find_overdemanding_campers
from family_camp2.validation.idle import find_idle_slots
from family_camp2.validation.report import render_text
from family_camp2.validation.tiers import find_unmet_optional_requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family_camp2",
        description="Generate or validate a Family Camp activity schedule.",
    )
    parser.add_argument(
        "--solver",
        required=True,
        choices=["cp_sat", "annealing"],
        help="Which solver to use to generate the schedule.",
    )

    data_source = parser.add_mutually_exclusive_group(required=True)
    data_source.add_argument("--data", type=Path, help="Path to a JSON camp file (see io/json_loader.py).")
    data_source.add_argument(
        "--legacy-cache", type=Path, help="Path to an existing family_camp .cache.pickle file."
    )

    parser.add_argument("--config", type=Path, default=None, help="Path to an EngineConfig JSON file.")
    parser.add_argument(
        "--out", type=Path, default=None, help="If given, also write the full report as JSON to this path."
    )
    parser.add_argument(
        "--time-limit", type=float, default=None, dest="time_limit",
        help="Solver time limit in seconds (solver-dependent; NFR-2).",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility (NFR-3)."
    )
    parser.add_argument(
        "--num-chains", type=int, default=None, dest="num_chains",
        help="Annealing only: number of independent restart chains (NFR-4).",
    )
    parser.add_argument(
        "--iterations-per-chain", type=int, default=None, dest="iterations_per_chain",
        help="Annealing only: iterations per chain (NFR-4).",
    )
    parser.add_argument(
        "--progress-output", type=str, default="-", dest="progress_output",
        help='Where to write progress updates: "-" for stdout (default), or a file path (OQ-10). '
        "There's no separate on/off switch - redirect to a file you won't read (or /dev/null) to silence it.",
    )
    parser.add_argument(
        "--progress-interval", type=float, default=60.0, dest="progress_interval",
        help="Wall-clock seconds between progress updates (OQ-9, default 60). CP-SAT only - "
        "annealing reports per restart-chain completion instead (see solvers/annealing/solver.py).",
    )
    parser.add_argument(
        "--export-schedule", type=Path, default=None, dest="export_schedule",
        help="If given, write the actual generated timetable (not the validation report) to "
        "<path>.csv and <path>.json (any extension on <path> is stripped first; OQ-11).",
    )
    parser.add_argument(
        "--report-dir", type=Path, default=None, dest="report_dir",
        help="If given, write family_itinerary.txt, activity_roster.txt, and idle_report.txt "
        "into this directory (created if needed) after solving (FR-72/FR-73/FR-74).",
    )
    return parser


def _solver_kwargs(args: argparse.Namespace, progress_reporter) -> dict:
    kwargs = {
        "time_limit_seconds": args.time_limit,
        "random_seed": args.seed,
        "progress_reporter": progress_reporter,
    }
    if args.solver == "cp_sat":
        kwargs["progress_interval_seconds"] = args.progress_interval
    if args.solver == "annealing":
        if args.num_chains is not None:
            kwargs["num_chains"] = args.num_chains
        if args.iterations_per_chain is not None:
            kwargs["iterations_per_chain"] = args.iterations_per_chain
    return kwargs


def _report_to_json(report) -> str:
    return json.dumps(dataclasses.asdict(report), indent=2, default=str)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.data is not None:
        activities, sessions, campers = load_json(args.data)
    else:
        activities, sessions, campers = load_legacy_cache(args.legacy_cache)

    config = load_config(args.config)
    progress_reporter = PrintProgressReporter(args.progress_output)
    try:
        solver = get_solver(args.solver, **_solver_kwargs(args, progress_reporter))
        result = solver.solve(activities, sessions, campers, config)
    finally:
        progress_reporter.close()

    print(render_text(result.report))

    if args.out is not None:
        args.out.write_text(_report_to_json(result.report))

    if args.export_schedule is not None:
        stem = args.export_schedule.with_suffix("")
        dump_schedule_csv(result.timetable, stem.with_suffix(".csv"))
        dump_schedule_json(result.timetable, stem.with_suffix(".json"))

    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        idle_report = find_idle_slots(result.timetable, campers, sessions)
        unmet_optional = find_unmet_optional_requests(result.timetable, campers)
        overdemand = find_overdemanding_campers(sessions, campers)
        (args.report_dir / "family_itinerary.txt").write_text(render_family_itinerary(result.timetable, campers))
        (args.report_dir / "activity_roster.txt").write_text(render_activity_roster(result.timetable, sessions))
        (args.report_dir / "idle_report.txt").write_text(render_idle_report(idle_report))
        (args.report_dir / "unmet_optional_report.txt").write_text(
            render_unmet_optional_report(unmet_optional, overdemand)
        )
        (args.report_dir / "unfeasible_families_report.txt").write_text(
            render_unfeasible_families_report(overdemand)
        )

    return 0
