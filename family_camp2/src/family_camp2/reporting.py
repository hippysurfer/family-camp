"""Human-readable operational reports from a timetable (REQUIREMENTS.md
§4.7, FR-72/FR-73/FR-74/FR-76/FR-77) - matching the *content* of the old
system's ``campers_out``/``activites_out``/``inactive_*_out`` reports
(`deep.py:print_individual`), not their exact formatting.

Per NFR-10, these read only ``Timetable``/domain objects and the
already-computed ``IdleReport``/``UnmetOptionalRequest``/
``CamperOverdemand`` lists that ``validation/`` produces - no new
scoring/validation logic lives here, only presentation.
"""

from __future__ import annotations

from collections import defaultdict

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.feasibility import CamperOverdemand
from family_camp2.validation.idle import IdleReport
from family_camp2.validation.tiers import UnmetOptionalRequest

__all__ = [
    "render_family_itinerary",
    "render_activity_roster",
    "render_idle_report",
    "render_unmet_optional_report",
    "render_unfeasible_families_report",
]

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


def render_unmet_optional_report(
    unmet: list[UnmetOptionalRequest], overdemand: list[CamperOverdemand] = ()
) -> str:
    """FR-76: unmet optional-activity requests, grouped by activity (most
    campers missed first), so an organiser can see at a glance where
    demand for optional activities went unsatisfied.

    Campers who also appear in ``overdemand`` (FR-77 - structurally asked
    for more distinct activities than they could ever fit into
    non-overlapping slots) are marked ``[over demand]``, so a reader can
    tell "there wasn't enough time for this camper regardless of
    capacity" apart from a plain capacity/allocation shortfall."""

    overdemanding_campers = {entry.camper for entry in overdemand}

    by_activity: dict[str, list[UnmetOptionalRequest]] = defaultdict(list)
    for request in unmet:
        by_activity[request.activity.name].append(request)

    lines: list[str] = [f"Total unmet optional requests: {len(unmet)}", ""]
    for name in sorted(by_activity, key=lambda n: (-len(by_activity[n]), n)):
        requests = by_activity[name]
        lines.append(f"{name}: {len(requests)} camper(s) missed it")
        for request in sorted(requests, key=lambda r: (r.camper.family_id, r.camper.name)):
            marker = " [over demand]" if request.camper in overdemanding_campers else ""
            lines.append(f"  - {request.camper.name} ({request.camper.family_id}){marker}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def render_unfeasible_families_report(overdemand: list[CamperOverdemand]) -> str:
    """FR-77: families with a member whose combined priority+optional
    request count structurally cannot fit into the non-overlapping session
    slots available to them, regardless of capacity - see
    validation/feasibility.py for what this ceiling does and doesn't
    prove."""

    by_family: dict[str, list[CamperOverdemand]] = defaultdict(list)
    for entry in overdemand:
        by_family[entry.camper.family_id].append(entry)

    lines: list[str] = [f"Families with a structurally overdemanding member: {len(by_family)}", ""]
    for family_id in sorted(by_family):
        lines.append(f"{family_id}:")
        for entry in sorted(by_family[family_id], key=lambda e: e.camper.name):
            shortfall = entry.requested_count - entry.available_timeslots
            lines.append(
                f"  - {entry.camper.name}: requested {entry.requested_count} activities, "
                f"only {entry.available_timeslots} non-overlapping slot(s) available "
                f"(short by {shortfall})"
            )
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
