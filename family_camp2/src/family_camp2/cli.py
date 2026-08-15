"""Command-line entry point for the family_camp2 scheduling engine.

Two subcommands (OQ-15): ``solve`` generates a schedule with a solver;
``revalidate`` takes a previously exported, possibly hand-edited schedule
(REQUIREMENTS.md §4.9, FR-86-89) and runs it through the same
validation/reporting pipeline *without* invoking a solver. Both share the
data-source flags (``_add_data_source_args``) and the output flags
(``_add_output_args``/``_write_outputs``), so the two entry points can
never drift apart on how a report gets written out.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from family_camp2.config import load_config
from family_camp2.domain import Camper, Session, Timetable
from family_camp2.io.json_loader import load_json
from family_camp2.io.legacy_cache_loader import load_legacy_cache
from family_camp2.io.schedule_export import dump_schedule_csv, dump_schedule_json, load_schedule_csv, load_schedule_json
from family_camp2.progress import PrintProgressReporter
from family_camp2.reporting import (
    render_activity_roster,
    render_family_itinerary,
    render_idle_report,
    render_unfeasible_families_report,
    render_unmet_optional_report,
)
from family_camp2.solvers.registry import get_solver
from family_camp2.validation.feasibility import find_overdemanding_families
from family_camp2.validation.idle import find_idle_slots
from family_camp2.validation.report import ValidationReport, render_text
from family_camp2.validation.tiers import find_unmet_optional_requests
from family_camp2.validation.validator import validate


def _add_data_source_args(parser: argparse.ArgumentParser) -> None:
    data_source = parser.add_mutually_exclusive_group(required=True)
    data_source.add_argument("--data", type=Path, help="Path to a JSON camp file (see io/json_loader.py).")
    data_source.add_argument(
        "--legacy-cache", type=Path, help="Path to an existing family_camp .cache.pickle file."
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to an EngineConfig JSON file.")


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out", type=Path, default=None, help="If given, also write the full report as JSON to this path."
    )
    parser.add_argument(
        "--export-schedule", type=Path, default=None, dest="export_schedule",
        help="If given, write the actual generated timetable (not the validation report) to "
        "<path>.csv and <path>.json (any extension on <path> is stripped first; OQ-11).",
    )
    parser.add_argument(
        "--report-dir", type=Path, default=None, dest="report_dir",
        help="If given, write family_itinerary.txt, activity_roster.txt, and idle_report.txt "
        "into this directory (created if needed) (FR-72/FR-73/FR-74).",
    )
    parser.add_argument(
        "--pdf-dir", type=Path, default=None, dest="pdf_dir",
        help="If given, write activities.pdf, campers.pdf, available_adults.pdf, and "
        "available_families.pdf into this directory (created if needed) "
        "(FR-80/FR-81/FR-84/FR-85). Requires the 'pdf' extra (pip install -e \".[pdf]\").",
    )
    parser.add_argument(
        "--pdf-paper", choices=["a4", "a3"], default="a4", dest="pdf_paper",
        help="Paper size for --pdf-dir output (default a4).",
    )
    parser.add_argument(
        "--pdf-orientation", choices=["portrait", "landscape"], default="portrait", dest="pdf_orientation",
        help="Orientation for --pdf-dir output (default portrait).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family_camp2",
        description="Generate or validate a Family Camp activity schedule.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    solve_parser = subparsers.add_parser("solve", help="Generate a schedule using a solver.")
    solve_parser.add_argument(
        "--solver",
        required=True,
        choices=["cp_sat", "annealing"],
        help="Which solver to use to generate the schedule.",
    )
    _add_data_source_args(solve_parser)
    solve_parser.add_argument(
        "--time-limit", type=float, default=None, dest="time_limit",
        help="Solver time limit in seconds (solver-dependent; NFR-2).",
    )
    solve_parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility (NFR-3)."
    )
    solve_parser.add_argument(
        "--num-chains", type=int, default=None, dest="num_chains",
        help="Annealing only: number of independent restart chains (NFR-4).",
    )
    solve_parser.add_argument(
        "--iterations-per-chain", type=int, default=None, dest="iterations_per_chain",
        help="Annealing only: iterations per chain (NFR-4).",
    )
    solve_parser.add_argument(
        "--progress-output", type=str, default="-", dest="progress_output",
        help='Where to write progress updates: "-" for stdout (default), or a file path (OQ-10). '
        "There's no separate on/off switch - redirect to a file you won't read (or /dev/null) to silence it.",
    )
    solve_parser.add_argument(
        "--progress-interval", type=float, default=60.0, dest="progress_interval",
        help="Wall-clock seconds between progress updates (OQ-9, default 60). CP-SAT only - "
        "annealing reports per restart-chain completion instead (see solvers/annealing/solver.py).",
    )
    _add_output_args(solve_parser)
    solve_parser.set_defaults(func=_run_solve)

    revalidate_parser = subparsers.add_parser(
        "revalidate",
        help="Validate and report a previously exported (optionally hand-edited) schedule, "
        "without running a solver (FR-86-89).",
    )
    _add_data_source_args(revalidate_parser)
    revalidate_parser.add_argument(
        "--schedule", type=Path, required=True,
        help="Path to a schedule previously written by --export-schedule (.csv or .json, "
        "dispatched by extension) - possibly hand-edited.",
    )
    _add_output_args(revalidate_parser)
    revalidate_parser.set_defaults(func=_run_revalidate)

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


def _load_data(args: argparse.Namespace):
    """Returns (activities, sessions, campers, constraints). --legacy-cache
    predates custom constraints (REQUIREMENTS.md §3.5) and has no way to
    express them, so that path always yields an empty constraint list."""
    if args.data is not None:
        return load_json(args.data)
    activities, sessions, campers = load_legacy_cache(args.legacy_cache)
    return activities, sessions, campers, []


def _write_outputs(
    timetable: Timetable,
    report: ValidationReport,
    campers: list[Camper],
    sessions: list[Session],
    args: argparse.Namespace,
) -> None:
    """Everything that can happen to a (Timetable, ValidationReport) pair
    after it exists, shared verbatim between ``solve`` and ``revalidate``
    (FR-89) so the two entry points can never write reports differently."""

    if args.out is not None:
        args.out.write_text(_report_to_json(report))

    if args.export_schedule is not None:
        stem = args.export_schedule.with_suffix("")
        dump_schedule_csv(timetable, stem.with_suffix(".csv"))
        dump_schedule_json(timetable, stem.with_suffix(".json"))

    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        idle_report = find_idle_slots(timetable, campers, sessions)
        unmet_optional = find_unmet_optional_requests(timetable, campers)
        overdemand = find_overdemanding_families(sessions, campers)
        (args.report_dir / "family_itinerary.txt").write_text(render_family_itinerary(timetable, campers))
        (args.report_dir / "activity_roster.txt").write_text(render_activity_roster(timetable, sessions))
        (args.report_dir / "idle_report.txt").write_text(render_idle_report(idle_report))
        (args.report_dir / "unmet_optional_report.txt").write_text(
            render_unmet_optional_report(unmet_optional, overdemand)
        )
        (args.report_dir / "unfeasible_families_report.txt").write_text(
            render_unfeasible_families_report(overdemand)
        )

    if args.pdf_dir is not None:
        try:
            from family_camp2.pdf_reports import (
                PageSpec,
                render_activities_pdf,
                render_available_adults_pdf,
                render_available_families_pdf,
                render_campers_pdf,
            )
        except ImportError as exc:  # pragma: no cover - exercised only when reportlab isn't installed
            raise ImportError(
                "reportlab is required for --pdf-dir. Install it with: pip install -e \".[pdf]\""
            ) from exc

        args.pdf_dir.mkdir(parents=True, exist_ok=True)
        page_spec = PageSpec(paper_size=args.pdf_paper, orientation=args.pdf_orientation)
        render_activities_pdf(timetable, sessions, args.pdf_dir / "activities.pdf", page_spec)
        render_campers_pdf(timetable, campers, args.pdf_dir / "campers.pdf", page_spec)
        idle_report = find_idle_slots(timetable, campers, sessions)
        render_available_adults_pdf(idle_report, args.pdf_dir / "available_adults.pdf", page_spec)
        render_available_families_pdf(idle_report, args.pdf_dir / "available_families.pdf", page_spec)


def _run_solve(args: argparse.Namespace) -> int:
    activities, sessions, campers, constraints = _load_data(args)
    config = dataclasses.replace(load_config(args.config), constraints=tuple(constraints))

    progress_reporter = PrintProgressReporter(args.progress_output)
    try:
        solver = get_solver(args.solver, **_solver_kwargs(args, progress_reporter))
        result = solver.solve(activities, sessions, campers, config)
    finally:
        progress_reporter.close()

    print(render_text(result.report))
    _write_outputs(result.timetable, result.report, campers, sessions, args)
    return 0


def _run_revalidate(args: argparse.Namespace) -> int:
    activities, sessions, campers, constraints = _load_data(args)
    config = dataclasses.replace(load_config(args.config), constraints=tuple(constraints))

    if args.schedule.suffix == ".json":
        timetable = load_schedule_json(args.schedule, activities, sessions, campers)
    else:
        timetable = load_schedule_csv(args.schedule, activities, sessions, campers)

    compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)
    report = validate(timetable, campers, sessions, tier0_weights=config.tier0_weights, compulsory=compulsory)

    print(render_text(report))
    _write_outputs(timetable, report, campers, sessions, args)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
