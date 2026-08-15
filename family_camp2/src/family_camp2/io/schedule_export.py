"""Export/import for the actual generated timetable (REQUIREMENTS.md §4.7,
FR-70/FR-71) - distinct from validation/report.py's scoring/violation
report (FR-40/41), which describes how *good* a schedule is, not what it
*is*. Closes a real gap found running a 3-hour CP-SAT job against real
data: the CLI's ``--out`` only ever wrote the validation report, never
the schedule itself.

Both CSV and JSON are supported (FR-70) from one shared row-building
helper, so "what does an exported assignment look like" exists exactly
once regardless of format.

Also the re-import path a hand-edited schedule goes through
(REQUIREMENTS.md §4.9, FR-86/87): ``load_schedule_csv``/``load_schedule_json``
collect *every* row that can't be resolved to a known camper/session
before raising, rather than stopping at the first - friendlier for a
hand-editing session likely to contain more than one mistake.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable

__all__ = [
    "ScheduleExportError",
    "dump_schedule_csv",
    "dump_schedule_json",
    "load_schedule_csv",
    "load_schedule_json",
]

_FIELDS = ["family_id", "camper_name", "activity_name", "session_label", "session_start"]


class ScheduleExportError(ValueError):
    """Raised when an exported schedule row/record can't be resolved back
    to a known camper or session."""


def _rows(timetable: Timetable) -> list[dict]:
    return [
        {
            "family_id": a.camper.family_id,
            "camper_name": a.camper.name,
            "activity_name": a.session.activity.name,
            "session_label": a.session.label,
            "session_start": a.session.start.isoformat(),
        }
        for a in sorted(timetable.assignments, key=lambda a: (a.camper.family_id, a.camper.name, a.session.start))
    ]


def dump_schedule_csv(timetable: Timetable, path: Path | str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerows(_rows(timetable))


def dump_schedule_json(timetable: Timetable, path: Path | str) -> None:
    Path(path).write_text(json.dumps(_rows(timetable), indent=2))


def _resolve_row(
    row: dict,
    campers_by_key: dict[tuple[str, str], Camper],
    sessions_by_key: dict[tuple[str, str, datetime], Session],
) -> Assignment:
    camper_key = (row["family_id"], row["camper_name"])
    camper = campers_by_key.get(camper_key)
    if camper is None:
        raise ScheduleExportError(
            f"Row references unknown camper {row['camper_name']!r} in family {row['family_id']!r}"
        )

    session_key = (row["activity_name"], row["session_label"], datetime.fromisoformat(row["session_start"]))
    session = sessions_by_key.get(session_key)
    if session is None:
        raise ScheduleExportError(
            f"Row references unknown session {row['activity_name']!r}/{row['session_label']!r} "
            f"at {row['session_start']!r}"
        )

    return Assignment(camper, session)


def _index_reference_data(
    sessions: list[Session], campers: list[Camper]
) -> tuple[dict[tuple[str, str], Camper], dict[tuple[str, str, datetime], Session]]:
    campers_by_key = {(c.family_id, c.name): c for c in campers}
    sessions_by_key = {(s.activity.name, s.label, s.start): s for s in sessions}
    return campers_by_key, sessions_by_key


def _resolve_rows(
    rows: list[dict],
    campers_by_key: dict[tuple[str, str], Camper],
    sessions_by_key: dict[tuple[str, str, datetime], Session],
) -> frozenset[Assignment]:
    """Resolves every row, collecting *all* unresolvable ones rather than
    stopping at the first - a hand-editing session is likely
    to contain more than one typo, and finding them one fix-and-rerun at
    a time is tedious. Row numbers are 1-based over the data rows only
    (matching what a spreadsheet's row selector would show once its
    header row is accounted for)."""

    assignments: set[Assignment] = set()
    errors: list[str] = []
    for i, row in enumerate(rows, start=1):
        try:
            assignments.add(_resolve_row(row, campers_by_key, sessions_by_key))
        except ScheduleExportError as exc:
            errors.append(f"Row {i}: {exc}")

    if errors:
        raise ScheduleExportError(
            f"{len(errors)} row(s) could not be resolved:\n" + "\n".join(errors)
        )
    return frozenset(assignments)


def load_schedule_csv(
    path: Path | str, activities: list[Activity], sessions: list[Session], campers: list[Camper]
) -> Timetable:
    campers_by_key, sessions_by_key = _index_reference_data(sessions, campers)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return Timetable(_resolve_rows(rows, campers_by_key, sessions_by_key))


def load_schedule_json(
    path: Path | str, activities: list[Activity], sessions: list[Session], campers: list[Camper]
) -> Timetable:
    campers_by_key, sessions_by_key = _index_reference_data(sessions, campers)
    rows = json.loads(Path(path).read_text())
    return Timetable(_resolve_rows(rows, campers_by_key, sessions_by_key))
