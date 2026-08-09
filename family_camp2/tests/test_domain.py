from datetime import datetime, timedelta

from family_camp2.domain import (
    Activity,
    Camper,
    Session,
    Timetable,
    sessions_overlap,
)


def make_activity(name="Archery", minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(
        name=name,
        duration=timedelta(minutes=minutes),
        min_occupancy=min_occ,
        max_occupancy=max_occ,
        min_age=min_age,
    )


def test_session_end_derives_from_start_and_duration():
    activity = make_activity(minutes=90)
    start = datetime(2026, 8, 1, 10, 0)
    session = Session(activity=activity, label="A", start=start)
    assert session.end == start + timedelta(minutes=90)


def test_camper_is_adult_boundary():
    activity = make_activity()
    young = Camper(name="Kid", family_id="F1", age=17, age_group="Cub", priorities=(activity,))
    adult = Camper(name="Parent", family_id="F1", age=18, age_group="Adult")
    assert young.is_adult is False
    assert adult.is_adult is True


def test_sessions_with_same_identity_are_equal_even_if_constructed_separately():
    start = datetime(2026, 8, 1, 10, 0)
    activity_a = make_activity()
    activity_b = make_activity()  # a separate but field-equal Activity instance
    session_a = Session(activity=activity_a, label="Morning", start=start)
    session_b = Session(activity=activity_b, label="Morning", start=start)

    assert session_a == session_b
    assert hash(session_a) == hash(session_b)
    assert {session_a: "x"}[session_b] == "x"


def test_sessions_overlap_helper():
    activity = make_activity(minutes=60)
    s1 = Session(activity=activity, label="A", start=datetime(2026, 8, 1, 10, 0))
    s2 = Session(activity=activity, label="B", start=datetime(2026, 8, 1, 10, 30))
    s3 = Session(activity=activity, label="C", start=datetime(2026, 8, 1, 11, 0))

    assert sessions_overlap(s1, s2) is True
    assert sessions_overlap(s1, s3) is False


def test_timetable_with_and_without_assignment_are_immutable():
    activity = make_activity()
    camper = Camper(name="Kid", family_id="F1", age=10, age_group="Cub")
    session = Session(activity=activity, label="A", start=datetime(2026, 8, 1, 10, 0))

    empty = Timetable()
    with_it = empty.with_assignment(camper, session)

    assert len(empty) == 0
    assert len(with_it) == 1
    assert with_it.sessions_of(camper) == {session}
    assert with_it.campers_in(session) == {camper}

    back_to_empty = with_it.without_assignment(camper, session)
    assert len(back_to_empty) == 0
    assert len(with_it) == 1  # original left untouched
