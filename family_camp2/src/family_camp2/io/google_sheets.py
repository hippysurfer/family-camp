"""Fetches Family Camp schedule input data live from a Google Sheet.

This is the tool that *produces* the prerequisite REQUIREMENTS.md §1.2
treats Google Sheets access as - it doesn't widen family_camp2's scope,
it's an on-ramp: run ``cli.py``'s ``fetch`` subcommand, then ``solve``/
``revalidate`` use the resulting JSON file automatically (or via
``--data`` explicitly, like any hand-written one).

Authenticates via the interactive user OAuth flow ("the OAuth dance":
``get_client`` opens a browser for one-time consent and caches the
resulting token) rather than the service-account flow the old
``family_camp/schedule/google_.py`` uses - appropriate for a tool a camp
organiser runs themselves from their own Google account, with no shared
service-account key to manage. Read-only scopes only (``gspread.auth.READONLY_SCOPES``)
- this tool never writes back to the sheet.

Parsing here is deliberately **not** shared with
``legacy_cache_loader.parse_worksheet_rows``: that function's column
indices are frozen to match a specific historical ``.cache.pickle``
layout, but a real, currently-in-use spreadsheet's columns drift from
year to year (verified against a live "Willesley 2026" sheet - e.g. its
camper worksheet has "Group Name"/"First Name"/"Surname" as separate
columns in a different order than the legacy pickle format assumes, plus
an extra "Extra" column between "Priority" and "Other" that shifts
everything after it). Parsing by **header name** here, rather than a
fixed position, is what makes this resilient to that kind of drift - and
it fails loudly (naming the missing column) rather than silently
misreading data if a sheet's structure changes further.
"""

from __future__ import annotations

import warnings
from datetime import datetime
from itertools import dropwhile, takewhile
from pathlib import Path
from typing import Protocol

from family_camp2.domain import Activity, Camper, Session
from family_camp2.io.legacy_cache_loader import _parse_duration

__all__ = [
    "DEFAULT_ACTIVITIES_WORKSHEET",
    "DEFAULT_SESSIONS_WORKSHEET",
    "DEFAULT_CAMPERS_WORKSHEET",
    "DEFAULT_CONSTRAINTS_WORKSHEET",
    "GoogleSheetsClient",
    "GoogleSheetsFetchError",
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
# REQUIREMENTS.md §3.5/§4.10 - a new tab, unlike the three above it has no
# precedent in the old family_camp/schedule/fetch_data.py to match.
DEFAULT_CONSTRAINTS_WORKSHEET = "Constraints for schedule"

# The first cell of each worksheet's header row, used to locate it amongst
# any preamble rows above it (both the activities and sessions worksheets
# happen to use the same marker).
_ACTIVITIES_HEADER_MARKER = "Activity"
_SESSIONS_HEADER_MARKER = "Activity"
_CAMPERS_HEADER_MARKER = "Group Ref"
# Reuses "Group Ref" (the Campers tab's own family-identifier column name)
# so organisers recognise it as the same identifier, not a new concept.
_CONSTRAINTS_HEADER_MARKER = "Group Ref"


class GoogleSheetsFetchError(ValueError):
    """Raised when a fetched worksheet is missing an expected column, or
    references an unknown activity."""


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


def _extract_table(rows: list[list[str]], header_marker: str) -> tuple[list[str], list[list[str]]]:
    """Finds the header row (its first cell equal to header_marker,
    skipping any preamble above it), then returns (header, data_rows):
    any immediate blank-first-cell row(s) right after the header are
    dropped, and data collection stops at the first blank-first-cell row
    once real data has started (dropping footer notes below it).

    This is a fresh, from-scratch reimplementation of what
    family_camp/schedule/fetch_data.py's remove_title_rows/remove_bad_rows
    do to a raw worksheet dump - not imported from the old package, and
    driven by the header's own marker text rather than a fixed row offset.
    """
    for i, row in enumerate(rows):
        if row and row[0] == header_marker:
            header = row
            remainder = rows[i + 1 :]
            break
    else:
        raise GoogleSheetsFetchError(f"Could not find a header row starting with {header_marker!r}")

    after_leading_blanks = dropwhile(lambda r: not r or r[0] == "", remainder)
    data_rows = list(takewhile(lambda r: bool(r) and r[0] != "", after_leading_blanks))
    return header, data_rows


def _column_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise GoogleSheetsFetchError(f"Expected column {name!r} not found in header {header!r}") from None


def _parse_activities(rows: list[list[str]]) -> dict[str, Activity]:
    header, data_rows = _extract_table(rows, _ACTIVITIES_HEADER_MARKER)
    name_col = _column_index(header, "Activity")
    duration_col = _column_index(header, "Duration (mins)")
    min_col = _column_index(header, "Min")
    max_col = _column_index(header, "Limit")

    activities_by_name: dict[str, Activity] = {}
    for row in data_rows:
        name = row[name_col].strip()
        if not name:
            continue
        activities_by_name[name] = Activity(
            name=name,
            duration=_parse_duration(row[duration_col]),
            min_occupancy=int(row[min_col]),
            max_occupancy=int(row[max_col]),
            min_age=None,
        )
    return activities_by_name


def _parse_sessions(rows: list[list[str]], activities_by_name: dict[str, Activity]) -> list[Session]:
    header, data_rows = _extract_table(rows, _SESSIONS_HEADER_MARKER)
    activity_col = _column_index(header, "Activity")
    label_col = _column_index(header, "Label")
    start_col = _column_index(header, "Start time")

    sessions: list[Session] = []
    for row in data_rows:
        activity_name = row[activity_col].strip()
        label = row[label_col].strip()
        if activity_name not in activities_by_name:
            raise GoogleSheetsFetchError(f"Session {label!r} references unknown activity {activity_name!r}")
        sessions.append(
            Session(
                activity=activities_by_name[activity_name],
                label=label,
                start=datetime.strptime(row[start_col].strip(), "%d/%m/%Y %H:%M:%S"),
            )
        )
    return sessions


def _parse_age(age_text: str, age_group_text: str) -> int:
    """Best-effort: the real sheet's Age column is sometimes blank (seen
    for adults who didn't fill in an exact age) or a "18+" style value
    rather than a plain integer. Falls back on the age-group label when no
    usable number is present. Not exact, but errs in the safe direction
    for the rules that depend on it (OQ-7 adult supervision treats 18 as
    adult; OQ-8 minimum ages only ever gate children upward, not adults
    downward)."""
    text = age_text.strip().rstrip("+")
    if text.isdigit():
        return int(text)

    lowered = age_group_text.lower()
    if "adult" in lowered:
        return 18
    if "infant" in lowered:
        return 2
    return 10  # child/unknown, no usable number given


def _resolve_activity_list(
    text: str, activities_by_name: dict[str, Activity], unknown_activities: set[str]
) -> list[Activity]:
    """Parses a comma-separated activity list, silently dropping (but
    recording) any name not present in activities_by_name.

    Unlike json_loader/legacy_cache_loader (where an unknown activity
    reference is a real error - FR-1 - because those inputs are meant to
    already be internally consistent), a live camper registration sheet
    legitimately expresses interest across a broader universe of camp
    attractions than the "Activities for schedule" subset that actually
    needs session-based time-slot scheduling (verified against a real
    sheet: campers can tick things like "Silent Disco" or "Tuck Shop" that
    have no corresponding scheduled sessions at all, alongside the ones
    that do). There is no session such an activity could ever be assigned
    to, so keeping the reference would only produce an unsatisfiable
    priority or a guaranteed-unmet optional request - dropping it is the
    correct behaviour, not data loss of anything the scheduler could act
    on. Every dropped name is still collected so fetch_schedule_data can
    report what was ignored.
    """
    resolved = []
    for raw_name in text.split(","):
        name = raw_name.strip()
        if not name:
            continue
        if name not in activities_by_name:
            unknown_activities.add(name)
            continue
        resolved.append(activities_by_name[name])
    return resolved


def _parse_campers(
    rows: list[list[str]], activities_by_name: dict[str, Activity]
) -> tuple[list[Camper], set[str]]:
    header, data_rows = _extract_table(rows, _CAMPERS_HEADER_MARKER)
    group_col = _column_index(header, "Group Ref")
    first_name_col = _column_index(header, "First Name")
    surname_col = _column_index(header, "Surname")
    age_group_col = _column_index(header, "18?")
    age_col = _column_index(header, "Age")
    priority_col = _column_index(header, "Priority")
    # Confirmed against real data: "Extra" always holds schedulable
    # nice-to-have activity names (the true FR-20 optional list); "Other"
    # always holds non-schedulable camp attractions (Tuck Shop, Silent
    # Disco, ...) that never appear in "Activities for schedule" at all -
    # despite what the column names might suggest at a glance.
    optional_col = _column_index(header, "Extra")

    unknown_activities: set[str] = set()
    campers: list[Camper] = []
    for row in data_rows:
        name = f"{row[first_name_col].strip()} {row[surname_col].strip()}".strip()
        age_group = row[age_group_col].strip()

        campers.append(
            Camper(
                name=name,
                family_id=row[group_col].strip(),
                age=_parse_age(row[age_col], age_group),
                age_group=age_group,
                priorities=tuple(_resolve_activity_list(row[priority_col], activities_by_name, unknown_activities)),
                optional=tuple(_resolve_activity_list(row[optional_col], activities_by_name, unknown_activities)),
            )
        )
    return campers, unknown_activities


def _parse_constraints(rows: list[list[str]]) -> list[dict]:
    """Parses the optional constraints tab (REQUIREMENTS.md §3.5) into raw
    records with the same keys ``constraints.parser.build_constraint_instances``
    expects (``family_id``/``camper_name``/``constraint``/``severity``/
    ``note``) - resolution against actual campers happens later, not here,
    matching how ``fetch_schedule_data`` leaves activity/session/camper
    cross-references to their own parse functions too."""
    header, data_rows = _extract_table(rows, _CONSTRAINTS_HEADER_MARKER)
    family_col = _column_index(header, "Group Ref")
    camper_col = _column_index(header, "Camper Name")
    constraint_col = _column_index(header, "Constraint")
    severity_col = _column_index(header, "Severity")
    note_col = _column_index(header, "Note")

    records: list[dict] = []
    for row in data_rows:
        records.append(
            {
                "family_id": row[family_col].strip(),
                "camper_name": row[camper_col].strip() or None,
                "constraint": row[constraint_col].strip(),
                "severity": row[severity_col].strip(),
                "note": row[note_col].strip(),
            }
        )
    return records


def _worksheet_titles(spreadsheet) -> set[str]:
    return {ws.title for ws in spreadsheet.worksheets()}


def fetch_schedule_data(
    client: GoogleSheetsClient,
    sheet_id_or_url: str,
    activities_worksheet: str = DEFAULT_ACTIVITIES_WORKSHEET,
    sessions_worksheet: str = DEFAULT_SESSIONS_WORKSHEET,
    campers_worksheet: str = DEFAULT_CAMPERS_WORKSHEET,
    constraints_worksheet: str | None = DEFAULT_CONSTRAINTS_WORKSHEET,
) -> tuple[str, list[Activity], list[Session], list[Camper], list[dict]]:
    """Fetch the schedule worksheets from an already-open spreadsheet and
    parse them into domain objects.

    Takes an already-authorized client (typically from ``get_client``) so
    the OAuth dance and the fetch-and-parse logic can be tested
    independently - this function itself needs no real network access if
    ``client`` is a test double exposing the same
    open_by_key/open_by_url/worksheet/worksheets/get_all_values/title
    interface as ``gspread.Client``/``gspread.Spreadsheet``.

    Unlike the other three (required) tabs, the constraints tab (§3.5) is
    an optional addition many spreadsheets won't have, so it's fetched
    only when actually present: ``constraints_worksheet`` (a name to look
    for, defaulting to ``DEFAULT_CONSTRAINTS_WORKSHEET``) is checked
    against ``spreadsheet.worksheets()`` first, and silently skipped
    (empty ``constraint_records``, no error) if no tab with that name
    exists - the organiser doesn't need to say "yes, fetch it" any more
    than they say that for a properly-populated Extra/Priority column;
    the tab either exists or it doesn't. Pass ``constraints_worksheet=None``
    to skip looking for it entirely.

    The returned ``title`` (the spreadsheet's own name, e.g. "Willesley
    2026") is what ``cli.py``'s ``fetch`` subcommand stores as the
    cached JSON's ``camp_name`` field - avoids needing a separate
    ``--camp-name`` flag, on the theory that a camp organiser's
    spreadsheet is already sensibly named.
    """
    spreadsheet = open_spreadsheet(client, sheet_id_or_url)
    title = spreadsheet.title
    acts_rows = spreadsheet.worksheet(activities_worksheet).get_all_values()
    session_rows = spreadsheet.worksheet(sessions_worksheet).get_all_values()
    campers_rows = spreadsheet.worksheet(campers_worksheet).get_all_values()

    activities_by_name = _parse_activities(acts_rows)
    sessions = _parse_sessions(session_rows, activities_by_name)
    campers, unknown_activities = _parse_campers(campers_rows, activities_by_name)

    if unknown_activities:
        warnings.warn(
            "Ignored references to activities not present in "
            f"{activities_worksheet!r} (likely unscheduled camp attractions, "
            f"not session-based activities): {sorted(unknown_activities)}",
            stacklevel=2,
        )

    constraint_records: list[dict] = []
    if constraints_worksheet is not None and constraints_worksheet in _worksheet_titles(spreadsheet):
        constraint_rows = spreadsheet.worksheet(constraints_worksheet).get_all_values()
        constraint_records = _parse_constraints(constraint_rows)

    return title, list(activities_by_name.values()), sessions, campers, constraint_records
