"""Command-line entry point for the family_camp2 scheduling engine."""

import argparse


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"solver={args.solver}")
    return 0
