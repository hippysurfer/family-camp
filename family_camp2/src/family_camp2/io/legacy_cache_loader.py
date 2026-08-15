"""Adapter for the raw worksheet-row format already produced by the
existing, unmodified ``family_camp/schedule/fetch_data.py``.

This is a data-contract dependency, not a code dependency: per
REQUIREMENTS.md's "Google Sheets is a prerequisite" framing, ``load_legacy_cache``
reads the pickle file that process already writes, so family_camp2 can be
run against real historical camp data without waiting on any new
data-fetch work. The parsing below is written from scratch against that
known row shape, not imported from ``family_camp.schedule.deep`` - keeping
family_camp2 fully independent of the old package.

``parse_worksheet_rows`` is the shared core: it takes the same
``(acts_wks, session_wks, campers_wks)`` raw-row shape regardless of how
those rows were obtained - unpickled here, or fetched live via
``io/google_sheets.py``'s OAuth-authenticated gspread client - so the
column-index parsing logic below has exactly one implementation, not one
per data source.

Column layout:

  activities row: [name, "H:MM:SS" duration, min_occupancy, max_occupancy]
  sessions row:   [activity_name, label, "%d/%m/%Y %H:%M:%S" start]
  campers row:    [family_id, first_name, last_name, ?, age, age_group,
                    ?, ?, "comma,separated,priority,activities",
                    "comma,separated,optional,activities"]
                   (the first campers row is a header and is skipped)

The legacy schema has no minimum-age column, so every Activity parsed
this way has ``min_age=None``. It also has no compulsory-activities
concept - that lives entirely in ``EngineConfig`` on the family_camp2
side, never mixed into a camper's own priorities list.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path

from family_camp2.domain import Activity, Camper, Session

__all__ = ["LegacyCacheLoadError", "load_legacy_cache", "parse_worksheet_rows"]


class LegacyCacheLoadError(ValueError):
    """Raised when worksheet rows are malformed or reference unknown data."""


def _parse_duration(text: str) -> timedelta:
    hours, minutes, seconds = map(float, text.split(":"))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def load_legacy_cache(path: Path | str) -> tuple[list[Activity], list[Session], list[Camper]]:
    with open(path, "rb") as f:
        acts_wks, session_wks, campers_wks = pickle.load(f)
    return parse_worksheet_rows(acts_wks, session_wks, campers_wks)


def parse_worksheet_rows(
    acts_wks: list[list[str]], session_wks: list[list[str]], campers_wks: list[list[str]]
) -> tuple[list[Activity], list[Session], list[Camper]]:
    activities_by_name: dict[str, Activity] = {}
    for row in acts_wks:
        if row[0] == "":
            continue
        name, duration, min_occ, max_occ = row[0], row[1], row[2], row[3]
        activities_by_name[name] = Activity(
            name=name,
            duration=_parse_duration(duration),
            min_occupancy=int(min_occ),
            max_occupancy=int(max_occ),
            min_age=None,
        )

    sessions: list[Session] = []
    for row in session_wks:
        activity_name, label, start_text = row[0], row[1], row[2]
        if activity_name not in activities_by_name:
            raise LegacyCacheLoadError(f"Session {label!r} references unknown activity {activity_name!r}")
        sessions.append(
            Session(
                activity=activities_by_name[activity_name],
                label=label,
                start=datetime.strptime(start_text, "%d/%m/%Y %H:%M:%S"),
            )
        )

    campers: list[Camper] = []
    for row in campers_wks[1:]:  # first row is a header
        family_id, first_name, last_name = row[0], row[1], row[2]
        age, age_group = row[4], row[5]
        priority_names = [n.strip() for n in row[8].split(",") if n.strip()]
        optional_names = [n.strip() for n in row[9].split(",") if n.strip()]
        camper_name = f"{first_name} {last_name}"

        priorities = _resolve(camper_name, "priority", priority_names, activities_by_name)
        optional = _resolve(camper_name, "optional", optional_names, activities_by_name)

        campers.append(
            Camper(
                name=camper_name,
                family_id=family_id,
                age=int(age),
                age_group=age_group,
                priorities=tuple(priorities),
                optional=tuple(optional),
            )
        )

    return list(activities_by_name.values()), sessions, campers


def _resolve(
    camper_name: str, kind: str, names: list[str], activities_by_name: dict[str, Activity]
) -> list[Activity]:
    resolved = []
    for name in names:
        if name not in activities_by_name:
            raise LegacyCacheLoadError(f"Camper {camper_name!r} has unknown {kind} activity {name!r}")
        resolved.append(activities_by_name[name])
    return resolved
