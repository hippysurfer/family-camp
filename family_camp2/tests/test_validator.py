from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.validation.report import render_text
from family_camp2.validation.validator import validate

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10, min_age=None):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ, min_age=min_age)


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


def test_validate_end_to_end_report():
    archery = activity("Archery")
    craft = activity("Craft")

    # Camper "Kid" has a priority (archery) that never gets scheduled -
    # a Class 2 violation - and one of two optional craft requests met.
    pottery = activity("Pottery")
    kid = camper("Kid", priorities=(archery,), optional=(craft, pottery))
    craft_session = session(craft, "A", 10)

    tt = Timetable().with_assignment(kid, craft_session)

    report = validate(tt, campers=[kid], sessions=[craft_session])

    assert report.is_feasible is False
    assert len(report.class2.missing_priorities) == 1
    assert report.class2.missing_priorities[0].activity == archery
    assert report.tier0_score > 0
    assert report.tier1_score == 0.5  # 1 of 2 optional requests met
    assert report.tier2_score == 0.0  # no multi-session activities

    text = render_text(report)
    assert "Kid" in text
    assert "Archery" in text
    assert "Feasible: False" in text


def test_validate_feasible_clean_report():
    archery = activity("Archery")
    kid = camper("Kid", priorities=(archery,))
    s = session(archery, "A", 10)
    tt = Timetable().with_assignment(kid, s)

    report = validate(tt, campers=[kid], sessions=[s])

    assert report.is_feasible is True
    assert report.tier0_score == 0
    text = render_text(report)
    assert "Feasible: True" in text
    assert "no violations" in text
