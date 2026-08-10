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
    return parser


def _solver_kwargs(args: argparse.Namespace) -> dict:
    kwargs = {"time_limit_seconds": args.time_limit, "random_seed": args.seed}
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
    solver = get_solver(args.solver, **_solver_kwargs(args))
    result = solver.solve(activities, sessions, campers, config)

    print(render_text(result.report))

    if args.out is not None:
        args.out.write_text(_report_to_json(result.report))

    return 0
