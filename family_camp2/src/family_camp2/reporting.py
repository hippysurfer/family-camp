"""Human-readable operational reports from a timetable (REQUIREMENTS.md
§4.7, FR-72/FR-73/FR-74) - matching the *content* of the old system's
``campers_out``/``activites_out``/``inactive_*_out`` reports
(`deep.py:print_individual`), not their exact formatting.

Per NFR-10, these read only ``Timetable``/domain objects and the
already-computed ``IdleReport`` that ``validation/`` produces - no new
scoring/validation logic lives here, only presentation.
"""

from __future__ import annotations

from collections import defaultdict

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.idle import IdleReport

__all__ = ["render_family_itinerary", "render_activity_roster", "render_idle_report"]

_TIME_FORMAT = "%a %H:%M"


def render_family_itinerary(timetable: Timetable, campers: list[Camper]) -> str:
    """For each family (sorted alphabetically by family_id, matching the
    old system's human-friendly ordering), its members' sessions in time
    order."""

    campers_by_family: dict[str, list[Camper]] = defaultdict(list)
    for c in campers:
        campers_by_family[c.family_id].append(c)

    lines: list[str] = []
    for family_id in sorted(campers_by_family):
        members = campers_by_family[family_id]
        assignments = [
            (session, camper) for camper in members for session in timetable.sessions_of(camper)
        ]

        lines.append(f"{family_id}:")
        if not assignments:
            lines.append("  (no assigned sessions)")
        else:
            for session, camper in sorted(
                assignments, key=lambda pair: (pair[0].start, pair[0].label, pair[1].name)
            ):
                lines.append(
                    f"  {session.start.strftime(_TIME_FORMAT)}  {session.activity.name} "
                    f"({session.label})  -  {camper.name}"
                )
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_activity_roster(timetable: Timetable, sessions: list[Session]) -> str:
    """For each activity's sessions (sorted by activity name, then session
    start time), who's assigned plus an occupancy-vs-limit summary."""

    by_activity: dict[Activity, list[Session]] = defaultdict(list)
    for s in sessions:
        by_activity[s.activity].append(s)

    lines: list[str] = []
    for activity in sorted(by_activity, key=lambda a: a.name):
        activity_sessions = sorted(by_activity[activity], key=lambda s: s.start)
        lines.append(f"{activity.name} (capacity {activity.min_occupancy}-{activity.max_occupancy} per session):")
        for session in activity_sessions:
            occupants = sorted(timetable.campers_in(session), key=lambda c: c.name)
            lines.append(
                f"  {session.start.strftime(_TIME_FORMAT)} ({session.label}): "
                f"{len(occupants)}/{activity.max_occupancy}"
            )
            for camper in occupants:
                lines.append(f"    - {camper.name} ({camper.family_id})")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_idle_report(idle_report: IdleReport) -> str:
    """For each active time bucket (buckets with nothing scheduled at all,
    e.g. a lunch break, are already excluded by find_idle_slots): the
    families with nobody active, and the individually-named idle adults
    (FR-74) - two distinct staffing-relevant views, not one
    undifferentiated camper list."""

    lines: list[str] = []
    for bucket in idle_report.buckets:
        lines.append(f"{bucket.start.strftime(_TIME_FORMAT)}:")
        families = ", ".join(bucket.idle_families) if bucket.idle_families else "none"
        lines.append(f"  Idle families: {families}")
        adults = ", ".join(c.name for c in bucket.idle_adults) if bucket.idle_adults else "none"
        lines.append(f"  Idle adults: {adults}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
