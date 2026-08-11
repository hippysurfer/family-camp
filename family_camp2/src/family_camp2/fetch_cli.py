"""CLI: download Family Camp schedule input data from a Google Sheet via
the OAuth dance, and save it as a JSON file ready for ``family_camp2``'s
``--data`` flag.

Usage::

    python -m family_camp2.fetch_cli --sheet-id <SHEET_ID_OR_URL> --out data.json
    family_camp2-fetch --sheet-id <SHEET_ID_OR_URL> --out data.json   # console script

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
    DEFAULT_SESSIONS_WORKSHEET,
    fetch_schedule_data,
    get_client,
)
from family_camp2.io.json_loader import dump_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="family_camp2-fetch",
        description="Download Family Camp schedule input data from Google Sheets and save it as a JSON --data file.",
    )
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID, or its full URL.")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the resulting JSON file.")
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
    activities, sessions, campers = fetch_schedule_data(
        client,
        args.sheet_id,
        activities_worksheet=args.activities_worksheet,
        sessions_worksheet=args.sessions_worksheet,
        campers_worksheet=args.campers_worksheet,
    )

    dump_json(activities, sessions, campers, args.out)
    print(
        f"Wrote {len(activities)} activities, {len(sessions)} sessions, "
        f"{len(campers)} campers to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
