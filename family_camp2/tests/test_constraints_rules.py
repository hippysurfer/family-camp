from datetime import datetime, timedelta

import pytest

from family_camp2.constraints.registry import CONSTRAINT_RULES, get_constraint_class, register
from family_camp2.constraints.rules import (
    NoActivitiesBetween,
    NoActivitiesOnDay,
    NoActivityAfter,
    NoActivityBefore,
    NotOnActivity,
)
from family_camp2.domain import Activity, Camper, Session

DAY1 = datetime(2026, 8, 1)
DAY2 = datetime(2026, 8, 2)


def activity(name="Archery", minutes=60):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=1, max_occupancy=10)


def session(act, label, dt):
    return Session(activity=act, label=label, start=dt)


def camper(name="Kid", family="F1", age=10, age_group="Cub"):
    return Camper(name=name, family_id=family, age=age, age_group=age_group)


# --- registry ---


def test_get_constraint_class_finds_registered_rules():
    assert get_constraint_class("no_activities_on_day") is NoActivitiesOnDay
    assert get_constraint_class("no_activity_before") is NoActivityBefore


def test_get_constraint_class_raises_a_clear_error_for_an_unknown_name():
    with pytest.raises(KeyError, match="bogus_rule"):
        get_constraint_class("bogus_rule")


def test_register_adds_a_new_entry_to_the_registry():
    @register("_test_only_rule")
    class _TestRule:
        def forbids(self, camper, session, all_sessions):
            return False

    assert CONSTRAINT_RULES["_test_only_rule"] is _TestRule
    del CONSTRAINT_RULES["_test_only_rule"]  # don't leak into other tests


# --- NoActivitiesOnDay ---


def test_no_activities_on_day_forbids_matching_day():
    archery = activity()
    all_sessions = [session(archery, "A", DAY1 + timedelta(hours=9)), session(archery, "B", DAY2 + timedelta(hours=9))]
    rule = NoActivitiesOnDay(day=2)
    c = camper()

    assert rule.forbids(c, all_sessions[1], all_sessions) is True  # day 2
    assert rule.forbids(c, all_sessions[0], all_sessions) is False  # day 1


def test_no_activities_on_day_derives_days_from_distinct_dates_present():
    """FR-3: no fixed camp length is assumed - "day N" is the Nth
    distinct date actually present in the session data."""
    archery = activity()
    day3 = datetime(2026, 8, 3)
    all_sessions = [
        session(archery, "A", DAY1 + timedelta(hours=9)),
        session(archery, "B", DAY2 + timedelta(hours=9)),
        session(archery, "C", day3 + timedelta(hours=9)),
    ]
    rule = NoActivitiesOnDay(day=3)
    c = camper()

    assert rule.forbids(c, all_sessions[2], all_sessions) is True
    assert rule.forbids(c, all_sessions[0], all_sessions) is False


# --- NoActivityBefore / NoActivityAfter / NoActivitiesBetween ---


def test_no_activity_before_forbids_earlier_sessions_only():
    archery = activity()
    early = session(archery, "A", DAY1 + timedelta(hours=9))
    late = session(archery, "B", DAY1 + timedelta(hours=12))
    rule = NoActivityBefore(time="11:00")
    c = camper()

    assert rule.forbids(c, early, [early, late]) is True
    assert rule.forbids(c, late, [early, late]) is False


def test_no_activity_after_forbids_later_sessions_only():
    archery = activity()
    early = session(archery, "A", DAY1 + timedelta(hours=9))
    late = session(archery, "B", DAY1 + timedelta(hours=16))
    rule = NoActivityAfter(time="15:00")
    c = camper()

    assert rule.forbids(c, late, [early, late]) is True
    assert rule.forbids(c, early, [early, late]) is False


def test_no_activities_between_forbids_sessions_inside_the_range():
    archery = activity()
    inside = session(archery, "A", DAY1 + timedelta(hours=13))
    outside = session(archery, "B", DAY1 + timedelta(hours=9))
    rule = NoActivitiesBetween(start="12:00", end="14:00")
    c = camper()

    assert rule.forbids(c, inside, [inside, outside]) is True
    assert rule.forbids(c, outside, [inside, outside]) is False


# --- NotOnActivity ---


def test_not_on_activity_forbids_the_named_activity_only():
    archery = activity("Archery")
    craft = activity("Craft")
    archery_session = session(archery, "A", DAY1 + timedelta(hours=9))
    craft_session = session(craft, "A", DAY1 + timedelta(hours=9))
    rule = NotOnActivity(activity="Archery")
    c = camper()

    assert rule.forbids(c, archery_session, [archery_session, craft_session]) is True
    assert rule.forbids(c, craft_session, [archery_session, craft_session]) is False
