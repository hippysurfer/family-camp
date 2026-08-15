"""Design B: domain-aware moves for the simulated-annealing local search.

See DESIGN_OPTIONS.md §4.1. Every move here enforces Class 1 (DESIGN_OPTIONS.md
§2.2) as a *precondition*, not a scored outcome: a move that would create a
double-booking, exceed a session's capacity, add an unrequested/age-ineligible
activity, or duplicate an activity is simply never produced (returns
``None``) rather than being produced and then penalised. This mirrors
build_model's variable-eligibility restriction in the CP-SAT design
(cp_sat.py) and means the annealing search, like CP-SAT, never even
considers a Class-1-violating state - it's structurally excluded from the
neighbourhood, not merely discouraged.
"""

from __future__ import annotations

from family_camp2.constraints.base import ConstraintInstance, hard_rules_by_camper
from family_camp2.domain import Activity, Assignment, Camper, Session, Timetable, sessions_overlap

__all__ = [
    "State",
    "assign_family",
    "move_family",
    "swap_families",
    "remove_family",
    "fix_unsupervised_split",
    "fix_lone_adult_split",
]


class State:
    """A mutable candidate assignment, with incrementally-maintained indexes."""

    def __init__(
        self,
        campers: list[Camper],
        sessions: list[Session],
        constraints: list[ConstraintInstance] = (),
    ):
        self.campers = campers
        self.sessions = sessions
        self.constraints = constraints
        self.hard_rules_by_camper = hard_rules_by_camper(constraints)
        self.assigned: dict[Session, set[Camper]] = {s: set() for s in sessions}
        self.assigned_sessions: dict[Camper, set[Session]] = {c: set() for c in campers}

    def occupancy(self, session: Session) -> int:
        return len(self.assigned[session])

    def is_assigned(self, camper: Camper, session: Session) -> bool:
        return session in self.assigned_sessions[camper]

    def _add(self, camper: Camper, session: Session) -> None:
        self.assigned[session].add(camper)
        self.assigned_sessions[camper].add(session)

    def _remove(self, camper: Camper, session: Session) -> None:
        self.assigned[session].discard(camper)
        self.assigned_sessions[camper].discard(session)

    def copy(self) -> "State":
        new = State(self.campers, self.sessions, self.constraints)
        for session, campers in self.assigned.items():
            new.assigned[session] = set(campers)
        for camper, sessions in self.assigned_sessions.items():
            new.assigned_sessions[camper] = set(sessions)
        return new

    def to_timetable(self) -> Timetable:
        assignments = {
            Assignment(camper, session) for session, campers in self.assigned.items() for camper in campers
        }
        return Timetable(frozenset(assignments))


def _is_eligible(camper: Camper, session: Session, state: State) -> bool:
    activity = session.activity
    requested = activity in camper.priorities or activity in camper.optional
    if not requested:
        return False
    if activity.min_age is not None and camper.age < activity.min_age:
        return False
    for rule in state.hard_rules_by_camper.get(camper, ()):
        if rule.forbids(camper, session, state.sessions):
            return False
    return True


def _has_activity(state: State, camper: Camper, activity: Activity) -> bool:
    return any(s.activity == activity for s in state.assigned_sessions[camper])


def _has_overlap(state: State, camper: Camper, session: Session, exclude: Session | None = None) -> bool:
    for other in state.assigned_sessions[camper]:
        if other == exclude:
            continue
        if sessions_overlap(session, other):
            return True
    return False


def assign_family(
    state: State, family_id: str, session: Session, campers_by_family: dict[str, list[Camper]]
) -> State | None:
    """Add every eligible, not-yet-assigned member of the family to session,
    filtered to those requesting the activity and age-eligible for it.
    Rejected (returns None) if nobody eligible remains to add, or if there
    isn't room for all of them."""

    members = campers_by_family.get(family_id, [])
    eligible = [
        c
        for c in members
        if _is_eligible(c, session, state)
        and not state.is_assigned(c, session)
        and not _has_activity(state, c, session.activity)
        and not _has_overlap(state, c, session)
    ]
    if not eligible:
        return None

    room = session.activity.max_occupancy - state.occupancy(session)
    if room < len(eligible):
        return None

    new_state = state.copy()
    for c in eligible:
        new_state._add(c, session)
    return new_state


def move_family(
    state: State,
    family_id: str,
    from_session: Session,
    to_session: Session,
    campers_by_family: dict[str, list[Camper]],
) -> State | None:
    """Move a family's members from one session instance to a parallel
    instance of the *same* activity. Rejected if the activities differ,
    nobody from the family is in from_session, there isn't room in
    to_session, or moving would double-book any member against their other
    assignments."""

    if from_session.activity != to_session.activity:
        return None

    members = [c for c in campers_by_family.get(family_id, []) if state.is_assigned(c, from_session)]
    if not members:
        return None

    room = to_session.activity.max_occupancy - state.occupancy(to_session)
    if room < len(members):
        return None

    for c in members:
        if _has_overlap(state, c, to_session, exclude=from_session):
            return None

    new_state = state.copy()
    for c in members:
        new_state._remove(c, from_session)
        new_state._add(c, to_session)
    return new_state


def swap_families(
    state: State,
    family_a: str,
    session_a: Session,
    family_b: str,
    session_b: Session,
    campers_by_family: dict[str, list[Camper]],
) -> State | None:
    """Swap two families between two sessions (possibly of different
    activities): family_a's members currently in session_a move to
    session_b and vice versa. Rejected unless every moved member is
    eligible for their new activity, there's room, and no member ends up
    double-booked or with a duplicate activity."""

    members_a = [c for c in campers_by_family.get(family_a, []) if state.is_assigned(c, session_a)]
    members_b = [c for c in campers_by_family.get(family_b, []) if state.is_assigned(c, session_b)]
    if not members_a or not members_b:
        return None

    if not all(_is_eligible(c, session_b, state) for c in members_a):
        return None
    if not all(_is_eligible(c, session_a, state) for c in members_b):
        return None

    # room_x = how much space will be free in session_x once its current
    # occupants (who are leaving) have vacated it - the group replacing them.
    room_b = session_b.activity.max_occupancy - state.occupancy(session_b) + len(members_b)
    if room_b < len(members_a):
        return None
    room_a = session_a.activity.max_occupancy - state.occupancy(session_a) + len(members_a)
    if room_a < len(members_b):
        return None

    for c in members_a:
        others = state.assigned_sessions[c] - {session_a}
        if any(sessions_overlap(session_b, s) for s in others):
            return None
        if any(s.activity == session_b.activity for s in others):
            return None
    for c in members_b:
        others = state.assigned_sessions[c] - {session_b}
        if any(sessions_overlap(session_a, s) for s in others):
            return None
        if any(s.activity == session_a.activity for s in others):
            return None

    new_state = state.copy()
    for c in members_a:
        new_state._remove(c, session_a)
    for c in members_b:
        new_state._remove(c, session_b)
    for c in members_a:
        new_state._add(c, session_b)
    for c in members_b:
        new_state._add(c, session_a)
    return new_state


def remove_family(state: State, family_id: str, session: Session, campers_by_family: dict[str, list[Camper]]) -> State:
    """Remove every member of the family from session. Always succeeds -
    removing an assignment can never create a Class 1 violation."""

    members = [c for c in campers_by_family.get(family_id, []) if state.is_assigned(c, session)]
    new_state = state.copy()
    for c in members:
        new_state._remove(c, session)
    return new_state


def fix_unsupervised_split(
    state: State, family_id: str, session: Session, campers_by_family: dict[str, list[Camper]]
) -> State | None:
    """If session (part of a family split, FR-17) has a child but no adult
    from the family, try to move an adult in from elsewhere. Rejected if no
    eligible, available adult exists, or there's no room."""

    members = campers_by_family.get(family_id, [])
    candidates = [
        c
        for c in members
        if c.is_adult
        and _is_eligible(c, session, state)
        and not state.is_assigned(c, session)
        and not _has_activity(state, c, session.activity)
        and not _has_overlap(state, c, session)
    ]
    if not candidates:
        return None
    if state.occupancy(session) >= session.activity.max_occupancy:
        return None

    new_state = state.copy()
    new_state._add(candidates[0], session)
    return new_state


def fix_lone_adult_split(
    state: State, family_id: str, session: Session, campers_by_family: dict[str, list[Camper]]
) -> State | None:
    """If session (part of a family split, FR-17) has only adults from the
    family and no child, try to move a child in from elsewhere - the
    symmetric repair to fix_unsupervised_split. Rejected if no eligible,
    available child exists, or there's no room."""

    members = campers_by_family.get(family_id, [])
    candidates = [
        c
        for c in members
        if not c.is_adult
        and _is_eligible(c, session, state)
        and not state.is_assigned(c, session)
        and not _has_activity(state, c, session.activity)
        and not _has_overlap(state, c, session)
    ]
    if not candidates:
        return None
    if state.occupancy(session) >= session.activity.max_occupancy:
        return None

    new_state = state.copy()
    new_state._add(candidates[0], session)
    return new_state
