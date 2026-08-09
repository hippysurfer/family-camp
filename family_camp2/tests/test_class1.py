from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.class1 import check_class1

DAY = datetime(2026, 8, 1)


def activity(name, minutes=60, min_occ=1, max_occ=2, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_clean_timetable_reports_nothing():
    archery = activity("Archery")
    c = camper("Kid", priorities=(archery,))
    s = session(archery, "A", 10)
    tt = Timetable().with_assignment(c, s)

    report = check_class1(tt)
    assert report.is_clean


def test_double_booking_detected():
    archery = activity("Archery")
    canoeing = activity("Canoeing")
    c = camper("Kid", priorities=(archery, canoeing))
    s1 = session(archery, "A", 10)
    s2 = session(canoeing, "B", 10)  # same start time -> overlaps

    tt = Timetable().with_assignment(c, s1).with_assignment(c, s2)
    report = check_class1(tt)

    assert not report.is_clean
    assert len(report.double_bookings) == 1
    assert report.double_bookings[0].camper == c


def test_capacity_overflow_detected():
    archery = activity("Archery", max_occ=1)
    c1 = camper("Kid1", priorities=(archery,))
    c2 = camper("Kid2", family="F2", priorities=(archery,))
    s = session(archery, "A", 10)

    tt = Timetable().with_assignment(c1, s).with_assignment(c2, s)
    report = check_class1(tt)

    assert not report.is_clean
    assert len(report.capacity_overflows) == 1
    assert report.capacity_overflows[0].count == 2
    assert report.capacity_overflows[0].max_occupancy == 1


def test_unrequested_assignment_detected():
    archery = activity("Archery")
    canoeing = activity("Canoeing")
    c = camper("Kid", priorities=(archery,))  # never asked for canoeing
    s = session(canoeing, "A", 10)

    tt = Timetable().with_assignment(c, s)
    report = check_class1(tt)

    assert not report.is_clean
    assert len(report.unrequested) == 1
    assert report.unrequested[0].camper == c


def test_duplicate_activity_assignment_detected():
    archery = activity("Archery")
    c = camper("Kid", priorities=(archery,))
    s1 = session(archery, "Morning", 9)
    s2 = session(archery, "Afternoon", 14)

    tt = Timetable().with_assignment(c, s1).with_assignment(c, s2)
    report = check_class1(tt)

    assert not report.is_clean
    assert len(report.duplicate_activity) == 1
    assert report.duplicate_activity[0].camper == c
    assert set(report.duplicate_activity[0].sessions) == {s1, s2}


def test_age_ineligible_assignment_detected():
    climbing = activity("Climbing", min_age=12)
    c = camper("Kid", age=10, priorities=(climbing,))
    s = session(climbing, "A", 10)

    tt = Timetable().with_assignment(c, s)
    report = check_class1(tt)

    assert not report.is_clean
    assert len(report.age_ineligible) == 1
    assert report.age_ineligible[0].camper == c
