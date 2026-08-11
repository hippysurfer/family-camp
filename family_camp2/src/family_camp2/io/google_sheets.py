"""Fetches Family Camp schedule input data live from a Google Sheet.

This is the tool that *produces* the prerequisite REQUIREMENTS.md §1.2
treats Google Sheets access as - it doesn't widen family_camp2's scope,
it's an on-ramp: run this, then use the resulting JSON file with
``--data`` exactly like any hand-written one (see fetch_cli.py).

Authenticates via the interactive user OAuth flow ("the OAuth dance":
``get_client`` opens a browser for one-time consent and caches the
resulting token) rather than the service-account flow the old
``family_camp/schedule/google_.py`` uses - appropriate for a tool a camp
organiser runs themselves from their own Google account, with no shared
service-account key to manage. Read-only scopes only (``gspread.auth.READONLY_SCOPES``)
- this tool never writes back to the sheet.

Reuses ``legacy_cache_loader.parse_worksheet_rows`` for the actual
row-to-domain-object parsing, since a live gspread worksheet's
``get_all_values()`` returns the exact same raw-row shape as the pickled
cache the legacy loader reads - only how the rows are obtained differs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from family_camp2.domain import Activity, Camper, Session
from family_camp2.io.legacy_cache_loader import parse_worksheet_rows

__all__ = [
    "DEFAULT_ACTIVITIES_WORKSHEET",
    "DEFAULT_SESSIONS_WORKSHEET",
    "DEFAULT_CAMPERS_WORKSHEET",
    "GoogleSheetsClient",
    "get_client",
    "open_spreadsheet",
    "fetch_schedule_data",
]

# Matches the worksheet names the existing family_camp/schedule/fetch_data.py
# expects, per README.rst - the "campers" data (registrations and activity
# preferences) confusingly lives on a tab just called "Activities".
DEFAULT_ACTIVITIES_WORKSHEET = "Activities for schedule"
DEFAULT_SESSIONS_WORKSHEET = "Sessions for schedule"
DEFAULT_CAMPERS_WORKSHEET = "Activities"


class GoogleSheetsClient(Protocol):
    """The (small) subset of gspread.Client's interface this module relies
    on - lets tests inject a fake client instead of performing real
    OAuth/network calls."""

    def open_by_key(self, key: str): ...

    def open_by_url(self, url: str): ...


def get_client(
    credentials_path: Path | str | None = None,
    authorized_user_path: Path | str | None = None,
) -> GoogleSheetsClient:
    """Perform the OAuth dance and return an authorized client.

    On first run this opens a browser for the user to sign in and consent;
    gspread caches the resulting token (at ``authorized_user_path``, or its
    own default location) so subsequent runs don't need to repeat it.
    Requires a real browser and network access - not exercised by the test
    suite, which injects a fake client into ``fetch_schedule_data`` instead.
    """
    try:
        import gspread
        import gspread.auth
    except ImportError as exc:  # pragma: no cover - exercised only when gspread isn't installed
        raise ImportError(
            "gspread is required to fetch data from Google Sheets. "
            "Install it with: pip install -e '.[google]'"
        ) from exc

    kwargs = {"scopes": gspread.auth.READONLY_SCOPES}
    if credentials_path is not None:
        kwargs["credentials_filename"] = Path(credentials_path)
    if authorized_user_path is not None:
        kwargs["authorized_user_filename"] = Path(authorized_user_path)
    return gspread.oauth(**kwargs)


def open_spreadsheet(client: GoogleSheetsClient, sheet_id_or_url: str):
    if sheet_id_or_url.startswith("http://") or sheet_id_or_url.startswith("https://"):
        return client.open_by_url(sheet_id_or_url)
    return client.open_by_key(sheet_id_or_url)


def fetch_schedule_data(
    client: GoogleSheetsClient,
    sheet_id_or_url: str,
    activities_worksheet: str = DEFAULT_ACTIVITIES_WORKSHEET,
    sessions_worksheet: str = DEFAULT_SESSIONS_WORKSHEET,
    campers_worksheet: str = DEFAULT_CAMPERS_WORKSHEET,
) -> tuple[list[Activity], list[Session], list[Camper]]:
    """Fetch the three schedule worksheets from an already-open spreadsheet
    and parse them into domain objects.

    Takes an already-authorized client (typically from ``get_client``) so
    the OAuth dance and the fetch-and-parse logic can be tested
    independently - this function itself needs no real network access if
    ``client`` is a test double exposing the same
    open_by_key/open_by_url/worksheet/get_all_values interface as
    ``gspread.Client``.
    """
    spreadsheet = open_spreadsheet(client, sheet_id_or_url)
    acts_wks = spreadsheet.worksheet(activities_worksheet).get_all_values()
    session_wks = spreadsheet.worksheet(sessions_worksheet).get_all_values()
    campers_wks = spreadsheet.worksheet(campers_worksheet).get_all_values()

    return parse_worksheet_rows(acts_wks, session_wks, campers_wks)
