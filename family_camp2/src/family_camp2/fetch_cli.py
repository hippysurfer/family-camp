"""CLI: download Family Camp schedule input data from a Google Sheet via
the OAuth dance, and save it as a JSON file ready for ``family_camp2``'s
``--data`` flag.

Usage::

    python -m family_camp2.fetch_cli --sheet-id <SHEET_ID_OR_URL>
    family_camp2-fetch --sheet-id <SHEET_ID_OR_URL>   # console script

Writes ``<out-dir>/<camp_name>.json``, where ``camp_name`` is derived
from the spreadsheet's own title (e.g. "Willesley 2026" ->
"willesley_2026.json") - no separate ``--camp-name`` flag needed, and
``cli.py``'s ``solve``/``revalidate`` recover the same camp name later
from this file's own name (see ``naming.py``).

The first run opens a browser for you to sign in to Google and grant
read-only access; gspread caches the resulting token so later runs don't
repeat that step (see io/google_sheets.py).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from family_camp2.io.google_sheets import (
    DEFAULT_ACTIVITIES_WORKSHEET,
    DEFAULT_CAMPERS_WORKSHEET,
    DEFAULT_CONSTRAINTS_WORKSHEET,
    DEFAULT_SESSIONS_WORKSHEET,
    fetch_schedule_data,
    get_client,
)
from family_camp2.io.json_loader import dump_json
from family_camp2.naming import slugify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family_camp2-fetch",
        description="Download Family Camp schedule input data from Google Sheets and save it as a JSON --data file.",
    )
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID, or its full URL.")
    parser.add_argument(
        "--out-dir", type=Path, default=Path("fetched_data"),
        help="Directory to write <camp_name>.json into (created if needed; default 'fetched_data').",
    )
    parser.add_argument(
        "--activities-worksheet", default=DEFAULT_ACTIVITIES_WORKSHEET,
        help=f"Worksheet tab name for activities (default: {DEFAULT_ACTIVITIES_WORKSHEET!r}).",
    )
    parser.add_argument(
        "--sessions-worksheet", default=DEFAULT_SESSIONS_WORKSHEET,
        help=f"Worksheet tab name for sessions (default: {DEFAULT_SESSIONS_WORKSHEET!r}).",
    )
    parser.add_argument(
        "--campers-worksheet", default=DEFAULT_CAMPERS_WORKSHEET,
        help=f"Worksheet tab name for camper registrations (default: {DEFAULT_CAMPERS_WORKSHEET!r}).",
    )
    parser.add_argument(
        "--constraints-worksheet", nargs="?", const=DEFAULT_CONSTRAINTS_WORKSHEET, default=None,
        help=(
            "Worksheet tab name for custom constraints (REQUIREMENTS.md "
            f"§3.5) - optional, not fetched unless given; pass with no "
            f"value to use the default ({DEFAULT_CONSTRAINTS_WORKSHEET!r})."
        ),
    )
    parser.add_argument(
        "--credentials", type=Path, default=None,
        help="OAuth client secrets JSON file (defaults to gspread's own config location).",
    )
    parser.add_argument(
        "--authorized-user", type=Path, default=None,
        help="Where to cache the OAuth token (defaults to gspread's own config location).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    client = get_client(credentials_path=args.credentials, authorized_user_path=args.authorized_user)
    camp_name, activities, sessions, campers, constraint_records = fetch_schedule_data(
        client,
        args.sheet_id,
        activities_worksheet=args.activities_worksheet,
        sessions_worksheet=args.sessions_worksheet,
        campers_worksheet=args.campers_worksheet,
        constraints_worksheet=args.constraints_worksheet,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{slugify(camp_name)}.json"
    dump_json(activities, sessions, campers, out_path, constraint_records)
    print(
        f"Wrote {len(activities)} activities, {len(sessions)} sessions, "
        f"{len(campers)} campers, {len(constraint_records)} constraints to {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
