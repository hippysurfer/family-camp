"""FR-40/FR-41: the structured validation report and its human-readable rendering."""

from __future__ import annotations

from dataclasses import dataclass

from family_camp2.validation.class1 import Class1Report
from family_camp2.validation.class2 import Class2Report
from family_camp2.validation.idle import IdleReport

__all__ = ["ValidationReport", "render_text"]


@dataclass
class ValidationReport:
    class1: Class1Report
    class2: Class2Report
    tier0_score: int
    tier1_score: float
    tier2_score: float
    idle: IdleReport

    @property
    def is_feasible(self) -> bool:
        return self.class1.is_clean and self.class2.is_clean


def render_text(report: ValidationReport) -> str:
    lines: list[str] = []
    lines.append("=== Validation Report ===")
    lines.append(f"Feasible: {report.is_feasible}")
    lines.append(f"Tier 0 (violation) score: {report.tier0_score}")
    lines.append(f"Tier 1 (optional-request satisfaction) score: {report.tier1_score:.2f}")
    lines.append(f"Tier 2 (session spread variance) score: {report.tier2_score:.4f}")
    lines.append("")

    c1 = report.class1
    if c1.is_clean:
        lines.append("Class 1 (structural): no violations.")
    else:
        lines.append("Class 1 (structural) violations:")
        for v in c1.double_bookings:
            lines.append(
                f"  - Double-booking: {v.camper.name} in "
                f"{v.session_a.activity.name}/{v.session_a.label} and "
                f"{v.session_b.activity.name}/{v.session_b.label}"
            )
        for v in c1.capacity_overflows:
            lines.append(
                f"  - Capacity overflow: {v.session.activity.name}/{v.session.label} "
                f"has {v.count} campers (max {v.max_occupancy})"
            )
        for v in c1.unrequested:
            lines.append(
                f"  - Unrequested activity: {v.camper.name} assigned to "
                f"{v.session.activity.name}/{v.session.label}, never requested"
            )
        for v in c1.duplicate_activity:
            lines.append(f"  - Duplicate activity: {v.camper.name} assigned to {v.activity.name} more than once")
        for v in c1.age_ineligible:
            lines.append(
                f"  - Age ineligible: {v.camper.name} (age {v.camper.age}) assigned to "
                f"{v.session.activity.name} (min age {v.session.activity.min_age})"
            )

    lines.append("")
    c2 = report.class2
    if c2.is_clean:
        lines.append("Class 2 (demand-driven): no violations.")
    else:
        lines.append("Class 2 (demand-driven) violations:")
        for v in c2.missing_priorities:
            lines.append(f"  - Missing priority: {v.camper.name} did not get {v.activity.name}")
        for v in c2.family_time_conflicts:
            lines.append(
                f"  - Family time conflict ({v.family_id}): {v.camper_a.name} in "
                f"{v.session_a.activity.name}/{v.session_a.label} clashes with "
                f"{v.camper_b.name} in {v.session_b.activity.name}/{v.session_b.label}"
            )
        for v in c2.unsupervised_splits:
            lines.append(
                f"  - Unsupervised family split ({v.family_id}): no adult in "
                f"{v.activity.name}/{v.session.label}"
            )
        for v in c2.under_minimum_sessions:
            lines.append(
                f"  - Under minimum: {v.session.activity.name}/{v.session.label} "
                f"has {v.count} (min {v.min_occupancy})"
            )
        for v in c2.unmet_compulsory:
            lines.append(f"  - Unmet compulsory activity: {v.camper.name} did not get {v.activity.name}")

    lines.append("")
    idle_occurrences = sum(len(b.idle_campers) for b in report.idle.buckets)
    lines.append(
        f"Idle: {idle_occurrences} camper-timeslot idle occurrence(s) "
        f"across {len(report.idle.buckets)} active time bucket(s)."
    )

    return "\n".join(lines)
