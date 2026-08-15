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
      ],
      "constraints": [
        {"family_id": "F1", "camper_name": null, "constraint": "no_activities_on_day(2)",
         "severity": "hard", "note": "optional free text"}
      ]
    }

``min_age`` on an activity, and ``priorities``/``optional`` on a camper, may
be omitted (default to ``null``/``[]`` respectively). Per FR-1, a session or
camper referencing an activity name that isn't in ``activities`` raises
``JsonLoadError`` naming the offending camper/session and the bad
reference, rather than being silently dropped.

``constraints`` (REQUIREMENTS.md §3.5) is optional, defaulting to `[]`;
``camper_name`` blank/``null`` applies the constraint to every member of
the family. Each record is resolved by
``constraints.parser.build_constraint_instances`` - see that module for
the constraint expression syntax and how invalid records are reported
(``constraints.parser.ConstraintParseError``, not wrapped as a
``JsonLoadError``, propagates as-is so constraint-specific problems stay
distinguishable from JSON-shape problems).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.constraints.parser import build_constraint_instances
from family_camp2.domain import Activity, Camper, Session

__all__ = ["JsonLoadError", "load_json", "dump_json"]


class JsonLoadError(ValueError):
    """Raised when a JSON camp file is malformed or references unknown data."""


def load_json(
    path: Path | str,
) -> tuple[list[Activity], list[Session], list[Camper], list[ConstraintInstance]]:
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

    constraints = build_constraint_instances(data.get("constraints", []), campers)

    return list(activities_by_name.values()), sessions, campers, constraints


def dump_json(
    activities: list[Activity],
    sessions: list[Session],
    campers: list[Camper],
    path: Path | str,
    constraint_records: list[dict] = (),
) -> None:
    """The counterpart to load_json: serialise domain objects back to this
    module's documented schema. Used by fetch_cli.py to save data fetched
    live from Google Sheets (io/google_sheets.py) ready for --data.

    ``constraint_records`` are the *raw* per-row dicts (family_id/
    camper_name/constraint/severity/note), not resolved
    ``ConstraintInstance`` objects - written straight through unchanged.
    There's no serialiser back from a resolved instance to a row: once
    targets are resolved to actual ``Camper`` objects, a family-level vs.
    single-camper-in-a-single-member-family record is no longer
    distinguishable, so round-tripping only ever goes through the raw
    row shape, exactly like the input a human would have written."""

    data = {
        "activities": [
            {
                "name": a.name,
                "duration_minutes": round(a.duration.total_seconds() / 60),
                "min_occupancy": a.min_occupancy,
                "max_occupancy": a.max_occupancy,
                "min_age": a.min_age,
            }
            for a in activities
        ],
        "sessions": [
            {"activity": s.activity.name, "label": s.label, "start": s.start.isoformat()} for s in sessions
        ],
        "campers": [
            {
                "name": c.name,
                "family_id": c.family_id,
                "age": c.age,
                "age_group": c.age_group,
                "priorities": [a.name for a in c.priorities],
                "optional": [a.name for a in c.optional],
            }
            for c in campers
        ],
        "constraints": list(constraint_records),
    }
    Path(path).write_text(json.dumps(data, indent=2))


def _resolve_activities(
    camper_name: str, kind: str, names: list[str], activities_by_name: dict[str, Activity]
) -> list[Activity]:
    resolved = []
    for name in names:
        if name not in activities_by_name:
            raise JsonLoadError(f"Camper {camper_name!r} has unknown {kind} activity {name!r}")
        resolved.append(activities_by_name[name])
    return resolved
