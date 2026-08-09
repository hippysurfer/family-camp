"""Command-line entry point for the family_camp2 scheduling engine."""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from family_camp2.config import load_config
from family_camp2.io.json_loader import load_json
from family_camp2.io.legacy_cache_loader import load_legacy_cache
from family_camp2.solvers.registry import get_solver
from family_camp2.validation.report import render_text


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
    return parser


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
    solver = get_solver(args.solver)
    result = solver.solve(activities, sessions, campers, config)

    print(render_text(result.report))

    if args.out is not None:
        args.out.write_text(_report_to_json(result.report))

    return 0
