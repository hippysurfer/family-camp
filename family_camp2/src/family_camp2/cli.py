"""Command-line entry point for the family_camp2 scheduling engine.

Three subcommands (OQ-15, extended by the unified-CLI request that added
``fetch``): ``fetch`` downloads camp data from a Google Sheet and caches
it locally; ``solve`` generates a schedule with a solver; ``revalidate``
takes a previously exported, possibly hand-edited schedule
(REQUIREMENTS.md §4.9, FR-86-89) and runs it through the same
validation/reporting pipeline *without* invoking a solver. ``solve``/
``revalidate`` share the data-source flags (``_add_data_source_args``)
and the output machinery (``_add_output_args``/``_write_outputs``), so
the two entry points can never drift apart on how a report gets written
out.

Every report is generated unconditionally, into one fresh
``<out-dir>/<camp_name>_<run timestamp>/`` folder per run (``naming.py``)
- there's no per-report opt-in/opt-out flag, and nothing is ever written
outside that folder (see ``_output_dir``). ``camp_name`` comes from the
``camp_name`` field ``fetch`` writes into its cached JSON (itself the
Google Sheet's own title), falling back to the input file's own name
when that field is absent (e.g. a hand-written ``--data`` file, or
``--legacy-cache``, which predates the field).

``solve``/``revalidate`` don't require ``--data``/``--legacy-cache`` -
omitting both falls back to ``<out-dir>/camp.json``, the file ``fetch``
writes, so the common path is just ``fetch`` then ``solve`` with no
further flags. If that file doesn't exist either, both stop with a
clear error naming ``fetch`` as the fix, rather than a bare
``FileNotFoundError``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from datetime import datetime
from pathlib import Path

from family_camp2.config import EngineConfig, load_config
from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.io.google_sheets import (
    DEFAULT_ACTIVITIES_WORKSHEET,
    DEFAULT_CAMPERS_WORKSHEET,
    DEFAULT_CONSTRAINTS_WORKSHEET,
    DEFAULT_SESSIONS_WORKSHEET,
    fetch_schedule_data,
    get_client,
)
from family_camp2.io.json_loader import dump_json, load_json, peek_camp_name
from family_camp2.io.legacy_cache_loader import load_legacy_cache
from family_camp2.io.schedule_export import dump_schedule_csv, dump_schedule_json, load_schedule_csv, load_schedule_json
from family_camp2.naming import run_folder_name
from family_camp2.pdf_reports import (
    PageSpec,
    render_activities_pdf,
    render_available_adults_pdf,
    render_available_families_pdf,
    render_campers_pdf,
)
from family_camp2.progress import PrintProgressReporter
from family_camp2.reporting import (
    render_activity_roster,
    render_family_itinerary,
    render_idle_report,
    render_unfeasible_families_report,
    render_unmet_optional_report,
)
from family_camp2.solvers.registry import get_solver
from family_camp2.status_report import SolverInfo, render_status_report_pdf
from family_camp2.validation.feasibility import find_overdemanding_families
from family_camp2.validation.idle import find_idle_slots
from family_camp2.validation.report import ValidationReport, render_text
from family_camp2.validation.tiers import find_unmet_optional_requests
from family_camp2.validation.validator import validate

# Every audience-specific PDF (FR-80/81/84/85) is now generated in both of
# these (paper size, orientation) combinations unconditionally, rather than
# the organiser picking one at a time - matches how fetched_data/pdfs/ was
# already being produced by hand (a compact portrait copy plus a larger
# landscape one), just automated.
_PDF_VARIANTS = (("a4", "portrait"), ("a3", "landscape"))

# The fixed filename 'fetch' writes into --out-dir, and solve/revalidate
# fall back to when neither --data nor --legacy-cache is given - "the
# downloaded file", singular, matching a one-camp-per-out-dir workflow.
_FETCHED_DATA_FILENAME = "camp.json"


def _add_data_source_args(parser: argparse.ArgumentParser) -> None:
    data_source = parser.add_mutually_exclusive_group()
    data_source.add_argument(
        "--data", type=Path,
        help="Path to a JSON camp file (see io/json_loader.py). Defaults to <out-dir>/"
        f"{_FETCHED_DATA_FILENAME} (written by 'fetch') if omitted.",
    )
    data_source.add_argument(
        "--legacy-cache", type=Path, help="Path to an existing family_camp .cache.pickle file."
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to an EngineConfig JSON file.")


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out-dir", type=Path, default=Path("fetched_data"), dest="out_dir",
        help="Directory to look for fetched data in and create this run's report folder in "
        "(default 'fetched_data') - every report (validation report, exported schedule, text "
        "reports, PDFs, status report) is always generated, into "
        "<out-dir>/<camp_name>_<run timestamp>/. Nothing is ever written outside that folder.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family_camp2",
        description="Fetch, generate, or validate a Family Camp activity schedule.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch", help="Download camp data from a Google Sheet, ready for 'solve'/'revalidate'."
    )
    fetch_parser.add_argument("--url", required=True, help="Google Sheets URL (or a bare sheet ID).")
    fetch_parser.add_argument(
        "--out-dir", type=Path, default=Path("fetched_data"), dest="out_dir",
        help=f"Directory to write {_FETCHED_DATA_FILENAME} into (created if needed; default "
        "'fetched_data') - the same directory 'solve'/'revalidate' default --out-dir to.",
    )
    fetch_parser.add_argument(
        "--activities-worksheet", default=DEFAULT_ACTIVITIES_WORKSHEET,
        help=f"Worksheet tab name for activities (default: {DEFAULT_ACTIVITIES_WORKSHEET!r}).",
    )
    fetch_parser.add_argument(
        "--sessions-worksheet", default=DEFAULT_SESSIONS_WORKSHEET,
        help=f"Worksheet tab name for sessions (default: {DEFAULT_SESSIONS_WORKSHEET!r}).",
    )
    fetch_parser.add_argument(
        "--campers-worksheet", default=DEFAULT_CAMPERS_WORKSHEET,
        help=f"Worksheet tab name for camper registrations (default: {DEFAULT_CAMPERS_WORKSHEET!r}).",
    )
    fetch_parser.add_argument(
        "--constraints-worksheet", nargs="?", const=DEFAULT_CONSTRAINTS_WORKSHEET, default=None,
        help=(
            "Worksheet tab name for custom constraints (REQUIREMENTS.md "
            f"§3.5) - optional, not fetched unless given; pass with no "
            f"value to use the default ({DEFAULT_CONSTRAINTS_WORKSHEET!r})."
        ),
    )
    fetch_parser.add_argument(
        "--credentials", type=Path, default=None,
        help="OAuth client secrets JSON file (defaults to gspread's own config location).",
    )
    fetch_parser.add_argument(
        "--authorized-user", type=Path, default=None,
        help="Where to cache the OAuth token (defaults to gspread's own config location).",
    )
    fetch_parser.set_defaults(func=_run_fetch)

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


def _resolve_data_path(args: argparse.Namespace) -> Path:
    """The actual input file this run will use: an explicit ``--data``/
    ``--legacy-cache`` override if given, else the file ``fetch`` writes
    into ``--out-dir``. Computed once and reused for both loading the
    data and naming the output folder, so they can never disagree.
    Raises a clear, descriptive error (not a bare ``FileNotFoundError``)
    when nothing was fetched yet and no override was given."""
    if args.data is not None:
        return args.data
    if args.legacy_cache is not None:
        return args.legacy_cache

    default_path = args.out_dir / _FETCHED_DATA_FILENAME
    if not default_path.exists():
        raise SystemExit(
            f"No downloaded camp data found at {default_path}.\n"
            f"Run 'family_camp2 fetch --url <GOOGLE_SHEET_URL>' first "
            f"(or pass --data/--legacy-cache explicitly)."
        )
    return default_path


def _load_data(args: argparse.Namespace, data_path: Path):
    """Returns (activities, sessions, campers, constraints). --legacy-cache
    predates custom constraints (REQUIREMENTS.md §3.5) and has no way to
    express them, so that path always yields an empty constraint list."""
    if args.legacy_cache is not None:
        activities, sessions, campers = load_legacy_cache(data_path)
        return activities, sessions, campers, []
    return load_json(data_path)


def _camp_name(data_path: Path) -> str:
    """Prefers the ``camp_name`` embedded in the JSON (written by ``fetch``
    from the Google Sheet's own title); falls back to the input file's
    own name for a hand-written ``--data`` file without that field, or
    for ``--legacy-cache`` (which predates it entirely)."""
    if data_path.suffix == ".json":
        embedded = peek_camp_name(data_path)
        if embedded:
            return embedded
    return data_path.stem


def _output_dir(out_dir_root: Path, camp_name: str) -> Path:
    """A fresh ``<out-dir>/<camp_name>_<run timestamp>/`` folder for this
    run (FR-111) - every run gets its own folder, so a later run never
    overwrites an earlier one's reports, and nothing is ever written
    outside it. The timestamp alone is only second-precision, so two
    runs started in the same second append a numeric suffix (``_2``,
    ``_3``, ...) rather than silently colliding into the same folder."""
    base_name = run_folder_name(camp_name, datetime.now())
    out_dir = out_dir_root / base_name
    suffix = 1
    while out_dir.exists():
        suffix += 1
        out_dir = out_dir_root / f"{base_name}_{suffix}"
    out_dir.mkdir(parents=True)
    return out_dir


def _write_outputs(
    activities: list[Activity],
    timetable: Timetable,
    report: ValidationReport,
    campers: list[Camper],
    sessions: list[Session],
    config: EngineConfig,
    solver_info: SolverInfo,
    out_dir: Path,
) -> None:
    """Every report this engine can produce, unconditionally, into the
    given output folder - shared verbatim between ``solve`` and
    ``revalidate`` (FR-89) so the two entry points can never write
    reports differently."""
    (out_dir / "report.json").write_text(_report_to_json(report))

    dump_schedule_csv(timetable, out_dir / "schedule.csv")
    dump_schedule_json(timetable, out_dir / "schedule.json")

    idle_report = find_idle_slots(timetable, campers, sessions)
    unmet_optional = find_unmet_optional_requests(timetable, campers)
    overdemand = find_overdemanding_families(sessions, campers)
    (out_dir / "family_itinerary.txt").write_text(render_family_itinerary(timetable, campers))
    (out_dir / "activity_roster.txt").write_text(render_activity_roster(timetable, sessions))
    (out_dir / "idle_report.txt").write_text(render_idle_report(idle_report))
    (out_dir / "unmet_optional_report.txt").write_text(render_unmet_optional_report(unmet_optional, overdemand))
    (out_dir / "unfeasible_families_report.txt").write_text(render_unfeasible_families_report(overdemand))

    for paper_size, orientation in _PDF_VARIANTS:
        page_spec = PageSpec(paper_size=paper_size, orientation=orientation)
        suffix = f"{paper_size}_{orientation}"
        render_activities_pdf(timetable, sessions, out_dir / f"activities_{suffix}.pdf", page_spec)
        render_campers_pdf(timetable, campers, out_dir / f"campers_{suffix}.pdf", page_spec)
        render_available_adults_pdf(idle_report, out_dir / f"available_adults_{suffix}.pdf", page_spec)
        render_available_families_pdf(idle_report, out_dir / f"available_families_{suffix}.pdf", page_spec)

    render_status_report_pdf(
        activities, sessions, campers, timetable, report, config, solver_info, out_dir / "status_report.pdf"
    )


def _run_fetch(args: argparse.Namespace) -> int:
    client = get_client(credentials_path=args.credentials, authorized_user_path=args.authorized_user)
    camp_name, activities, sessions, campers, constraint_records = fetch_schedule_data(
        client,
        args.url,
        activities_worksheet=args.activities_worksheet,
        sessions_worksheet=args.sessions_worksheet,
        campers_worksheet=args.campers_worksheet,
        constraints_worksheet=args.constraints_worksheet,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / _FETCHED_DATA_FILENAME
    dump_json(activities, sessions, campers, out_path, constraint_records, camp_name=camp_name)
    print(
        f"Wrote {len(activities)} activities, {len(sessions)} sessions, "
        f"{len(campers)} campers, {len(constraint_records)} constraints "
        f"for {camp_name!r} to {out_path}"
    )
    return 0


def _run_solve(args: argparse.Namespace) -> int:
    data_path = _resolve_data_path(args)
    activities, sessions, campers, constraints = _load_data(args, data_path)
    config = dataclasses.replace(load_config(args.config), constraints=tuple(constraints))

    progress_reporter = PrintProgressReporter(args.progress_output)
    try:
        solver = get_solver(args.solver, **_solver_kwargs(args, progress_reporter))
        start = time.monotonic()
        result = solver.solve(activities, sessions, campers, config)
        duration_seconds = time.monotonic() - start
    finally:
        progress_reporter.close()

    print(render_text(result.report))
    solver_info = SolverInfo(solver_name=args.solver, duration_seconds=duration_seconds, diagnostics=result.diagnostics)
    out_dir = _output_dir(args.out_dir, _camp_name(data_path))
    _write_outputs(activities, result.timetable, result.report, campers, sessions, config, solver_info, out_dir)
    print(f"Reports written to {out_dir}")
    return 0


def _run_revalidate(args: argparse.Namespace) -> int:
    data_path = _resolve_data_path(args)
    activities, sessions, campers, constraints = _load_data(args, data_path)
    config = dataclasses.replace(load_config(args.config), constraints=tuple(constraints))

    if args.schedule.suffix == ".json":
        timetable = load_schedule_json(args.schedule, activities, sessions, campers)
    else:
        timetable = load_schedule_csv(args.schedule, activities, sessions, campers)

    compulsory = frozenset(a for a in activities if a.name in config.compulsory_activities)
    report = validate(
        timetable,
        campers,
        sessions,
        tier0_weights=config.tier0_weights,
        compulsory=compulsory,
        constraints=config.constraints,
    )

    print(render_text(report))
    out_dir = _output_dir(args.out_dir, _camp_name(data_path))
    _write_outputs(activities, timetable, report, campers, sessions, config, SolverInfo(), out_dir)
    print(f"Reports written to {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
