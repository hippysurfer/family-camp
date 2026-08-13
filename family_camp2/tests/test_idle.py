from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.idle import find_idle_slots

DAY = datetime(2026, 8, 1, 9, 0)  # 09:00


def activity(name, minutes=60, min_occ=1, max_occ=10):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ)


def camper(name, family_id="F1", age=10, age_group="Cub"):
    return Camper(name=name, family_id=family_id, age=age, age_group=age_group)


def test_bucket_with_no_running_session_is_skipped():
    # Sessions run 09:00-10:00 and 12:00-13:00, leaving a gap at 10:00-12:00
    # (e.g. lunch) that should not appear as a reported bucket at all.
    archery = activity("Archery")
    s1 = Session(activity=archery, label="Morning", start=DAY)
    s2 = Session(activity=archery, label="After lunch", start=DAY + timedelta(hours=3))

    kid = camper("Kid")
    tt = Timetable().with_assignment(kid, s1).with_assignment(kid, s2)

    report = find_idle_slots(tt, [kid], [s1, s2], granularity=timedelta(hours=1))
    bucket_starts = [b.start for b in report.buckets]

    assert DAY in bucket_starts
    assert (DAY + timedelta(hours=1)) not in bucket_starts  # 10:00-11:00 gap
    assert (DAY + timedelta(hours=3)) in bucket_starts


def test_idle_camper_reported_in_bucket_they_have_nothing_scheduled():
    archery = activity("Archery")
    s1 = Session(activity=archery, label="Morning", start=DAY)

    busy = camper("Busy")
    idle = camper("Idle")
    tt = Timetable().with_assignment(busy, s1)

    report = find_idle_slots(tt, [busy, idle], [s1], granularity=timedelta(hours=1))

    assert len(report.buckets) == 1
    assert report.buckets[0].idle_campers == (idle,)


def test_no_sessions_produces_empty_report():
    assert find_idle_slots(Timetable(), [], [], granularity=timedelta(hours=1)).buckets == []


def test_family_with_every_member_idle_is_reported_as_an_idle_family():
    archery = activity("Archery")
    s1 = Session(activity=archery, label="Morning", start=DAY)

    busy_family_parent = camper("BusyParent", family_id="F1", age=40, age_group="Adult")
    idle_family_parent = camper("IdleParent", family_id="F2", age=40, age_group="Adult")
    idle_family_kid = camper("IdleKid", family_id="F2", age=8, age_group="Cub")
    tt = Timetable().with_assignment(busy_family_parent, s1)

    report = find_idle_slots(
        tt, [busy_family_parent, idle_family_parent, idle_family_kid], [s1], granularity=timedelta(hours=1)
    )

    assert len(report.buckets) == 1
    assert report.buckets[0].idle_families == ("F2",)  # F1 has an active member, F2 doesn't


def test_family_with_at_least_one_active_member_is_not_reported_as_idle():
    archery = activity("Archery")
    craft = activity("Craft")
    s1 = Session(activity=archery, label="Morning", start=DAY)
    s2 = Session(activity=craft, label="Morning", start=DAY)

    active_parent = camper("Parent", family_id="F1", age=40, age_group="Adult")
    idle_kid = camper("Kid", family_id="F1", age=8, age_group="Cub")
    tt = Timetable().with_assignment(active_parent, s1)  # kid has nothing, but parent is active

    report = find_idle_slots(tt, [active_parent, idle_kid], [s1, s2], granularity=timedelta(hours=1))

    assert report.buckets[0].idle_campers == (idle_kid,)  # the kid personally is idle...
    assert report.buckets[0].idle_families == ()  # ...but the family as a whole is not


def test_idle_adults_is_the_adult_subset_of_idle_campers():
    archery = activity("Archery")
    s1 = Session(activity=archery, label="Morning", start=DAY)

    busy = camper("Busy", age=40, age_group="Adult")
    idle_adult = camper("IdleAdult", family_id="F2", age=40, age_group="Adult")
    idle_kid = camper("IdleKid", family_id="F3", age=8, age_group="Cub")
    tt = Timetable().with_assignment(busy, s1)

    report = find_idle_slots(tt, [busy, idle_adult, idle_kid], [s1], granularity=timedelta(hours=1))

    assert report.buckets[0].idle_campers == (idle_adult, idle_kid)
    assert report.buckets[0].idle_adults == (idle_adult,)
