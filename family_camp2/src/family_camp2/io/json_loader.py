"""A minimal, documented JSON format for describing a camp instance.

Implements the input data contract in REQUIREMENTS.md §3 (plus ``min_age``
per OQ-8). Usable standalone for manual runs and as the format every test
fixture in this repo is built from.

Schema::

    {
      "activities": [
        {"name": "Archery", "duration_minutes": 60,
         "min_occupancy": 1, "max_occupancy": 10, "min_age": null}
      ],
      "sessions": [
        {"activity": "Archery", "label": "Morning", "start": "2026-08-01T09:00:00"}
      ],
      "campers": [
        {"name": "Kid", "family_id": "F1", "age": 10, "age_group": "Cub",
         "priorities": ["Archery"], "optional": ["Craft"]}
      ]
    }

``min_age`` on an activity, and ``priorities``/``optional`` on a camper, may
be omitted (default to ``null``/``[]`` respectively). Per FR-1, a session or
camper referencing an activity name that isn't in ``activities`` raises
``JsonLoadError`` naming the offending camper/session and the bad
reference, rather than being silently dropped.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from family_camp2.domain import Activity, Camper, Session

__all__ = ["JsonLoadError", "load_json"]


class JsonLoadError(ValueError):
    """Raised when a JSON camp file is malformed or references unknown data."""


def load_json(path: Path | str) -> tuple[list[Activity], list[Session], list[Camper]]:
    data = json.loads(Path(path).read_text())

    activities_by_name: dict[str, Activity] = {}
    for a in data.get("activities", []):
        activities_by_name[a["name"]] = Activity(
            name=a["name"],
            duration=timedelta(minutes=a["duration_minutes"]),
            min_occupancy=a["min_occupancy"],
            max_occupancy=a["max_occupancy"],
            min_age=a.get("min_age"),
        )

    sessions: list[Session] = []
    for s in data.get("sessions", []):
        activity_name = s["activity"]
        if activity_name not in activities_by_name:
            raise JsonLoadError(
                f"Session {s.get('label', '?')!r} references unknown activity {activity_name!r}"
            )
        sessions.append(
            Session(
                activity=activities_by_name[activity_name],
                label=s["label"],
                start=datetime.fromisoformat(s["start"]),
            )
        )

    campers: list[Camper] = []
    for c in data.get("campers", []):
        priorities = _resolve_activities(c["name"], "priority", c.get("priorities", []), activities_by_name)
        optional = _resolve_activities(c["name"], "optional", c.get("optional", []), activities_by_name)

        campers.append(
            Camper(
                name=c["name"],
                family_id=c["family_id"],
                age=c["age"],
                age_group=c["age_group"],
                priorities=tuple(priorities),
                optional=tuple(optional),
            )
        )

    return list(activities_by_name.values()), sessions, campers


def _resolve_activities(
    camper_name: str, kind: str, names: list[str], activities_by_name: dict[str, Activity]
) -> list[Activity]:
    resolved = []
    for name in names:
        if name not in activities_by_name:
            raise JsonLoadError(f"Camper {camper_name!r} has unknown {kind} activity {name!r}")
        resolved.append(activities_by_name[name])
    return resolved
