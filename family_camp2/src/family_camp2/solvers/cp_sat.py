"""Design A: constraint programming via Google OR-Tools CP-SAT.

See DESIGN_OPTIONS.md §3. This module is built up over several
implementation-plan steps: Step 12 (this one) builds the decision
variables and Class 1 structural constraints only; Step 13 adds Class 2
violation indicators and the Tier 0 objective; Step 14 completes the
three-phase lexicographic solve and the ``CpSatSolver`` itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ortools.sat.python import cp_model

from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable

__all__ = ["VarIndex", "build_model", "extract_timetable"]

# An arbitrary fixed reference point used to convert datetimes to the small
# integer offsets CP-SAT's interval variables require. Any fixed epoch
# works; this one just keeps the resulting integers small and readable.
_EPOCH = datetime(2000, 1, 1)


def _to_minutes(dt: datetime) -> int:
    return int((dt - _EPOCH).total_seconds() // 60)


@dataclass
class VarIndex:
    """Maps (camper, session) -> BoolVar, for eligible pairs only.

    A pair is only eligible - and only gets a variable - if the camper
    requested the session's activity (priority or optional) and is
    age-eligible for it (OQ-8). This is what makes Class 1's
    unrequested-activity and age-eligibility rules structural rather than
    something the objective has to discourage (DESIGN_OPTIONS.md §3.1):
    the model has no way to represent an invalid assignment at all.
    """

    by_pair: dict[tuple[Camper, Session], cp_model.IntVar] = field(default_factory=dict)
    by_camper: dict[Camper, list[Session]] = field(default_factory=dict)
    by_session: dict[Session, list[Camper]] = field(default_factory=dict)

    def get(self, camper: Camper, session: Session) -> cp_model.IntVar | None:
        return self.by_pair.get((camper, session))

    def __contains__(self, pair: tuple[Camper, Session]) -> bool:
        return pair in self.by_pair


def _is_eligible(camper: Camper, session: Session) -> bool:
    activity = session.activity
    requested = activity in camper.priorities or activity in camper.optional
    if not requested:
        return False
    if activity.min_age is not None and camper.age < activity.min_age:
        return False
    return True


def build_model(
    activities: list[Activity], sessions: list[Session], campers: list[Camper]
) -> tuple[cp_model.CpModel, VarIndex]:
    model = cp_model.CpModel()

    by_pair: dict[tuple[Camper, Session], cp_model.IntVar] = {}
    by_camper: dict[Camper, list[Session]] = {c: [] for c in campers}
    by_session: dict[Session, list[Camper]] = {s: [] for s in sessions}

    for camper in campers:
        for session in sessions:
            if _is_eligible(camper, session):
                var = model.NewBoolVar(f"x[{camper.name}|{session.activity.name}|{session.label}]")
                by_pair[(camper, session)] = var
                by_camper[camper].append(session)
                by_session[session].append(camper)

    var_index = VarIndex(by_pair=by_pair, by_camper=by_camper, by_session=by_session)

    # FR-10: no double-booking. A no-overlap constraint over each camper's
    # candidate sessions, using optional intervals gated by the assignment
    # variable itself - only sessions actually chosen participate.
    for camper in campers:
        candidate_sessions = by_camper[camper]
        if len(candidate_sessions) < 2:
            continue
        intervals = []
        for session in candidate_sessions:
            var = by_pair[(camper, session)]
            start = _to_minutes(session.start)
            end = _to_minutes(session.end)
            intervals.append(
                model.NewOptionalIntervalVar(
                    start, end - start, end, var, f"iv[{camper.name}|{session.activity.name}|{session.label}]"
                )
            )
        model.AddNoOverlap(intervals)

    # FR-12 (max side): session capacity.
    for session in sessions:
        candidate_campers = by_session[session]
        if not candidate_campers:
            continue
        model.Add(sum(by_pair[(c, session)] for c in candidate_campers) <= session.activity.max_occupancy)

    # FR-15: no duplicate activity. Eligibility alone doesn't rule this out
    # (a camper can be eligible for two different session instances of the
    # same activity, e.g. a morning and an afternoon slot) - unlike
    # unrequested-activity and age-eligibility, this needs an explicit
    # constraint, not just a restricted variable domain.
    for camper in campers:
        sessions_by_activity: dict[Activity, list[cp_model.IntVar]] = {}
        for session in by_camper[camper]:
            sessions_by_activity.setdefault(session.activity, []).append(by_pair[(camper, session)])
        for activity_vars in sessions_by_activity.values():
            if len(activity_vars) > 1:
                model.Add(sum(activity_vars) <= 1)

    return model, var_index


def extract_timetable(solver: cp_model.CpSolver, var_index: VarIndex) -> Timetable:
    assignments = {
        Assignment(camper, session)
        for (camper, session), var in var_index.by_pair.items()
        if solver.Value(var)
    }
    return Timetable(frozenset(assignments))
