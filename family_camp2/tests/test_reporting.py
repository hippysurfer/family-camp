from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.reporting import render_activity_roster, render_family_itinerary

DAY = datetime(2026, 8, 1, 9, 0)


def _fixture():
    archery = Activity("Archery", timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    craft = Activity("Craft", timedelta(minutes=45), min_occupancy=1, max_occupancy=2)

    morning = Session(activity=archery, label="Morning", start=DAY)
    afternoon = Session(activity=archery, label="Afternoon", start=DAY + timedelta(hours=5))
    craft_session = Session(activity=craft, label="A", start=DAY + timedelta(hours=1))
    sessions = [morning, afternoon, craft_session]

    parent = Camper(name="Parent One", family_id="001/One", age=40, age_group="Adult", priorities=(archery,))
    kid = Camper(name="Kid One", family_id="001/One", age=10, age_group="Cub", optional=(craft,))
    lonely = Camper(name="Lonely Two", family_id="002/Two", age=30, age_group="Adult")
    campers = [parent, kid, lonely]

    timetable = Timetable().with_assignment(parent, morning).with_assignment(kid, craft_session)
    return sessions, campers, timetable


def test_family_itinerary_groups_by_family_in_time_order():
    sessions, campers, timetable = _fixture()

    text = render_family_itinerary(timetable, campers)

    assert "001/One:" in text
    idx_family = text.index("001/One:")
    idx_archery = text.index("Archery", idx_family)
    idx_craft = text.index("Craft", idx_family)
    assert idx_archery < idx_craft  # morning session listed before the later craft session
    assert "Parent One" in text
    assert "Kid One" in text


def test_family_itinerary_notes_families_with_no_assignments():
    sessions, campers, timetable = _fixture()

    text = render_family_itinerary(timetable, campers)

    idx_family = text.index("002/Two:")
    assert "(no assigned sessions)" in text[idx_family : idx_family + 60]


def test_activity_roster_shows_occupancy_against_limit():
    sessions, campers, timetable = _fixture()

    text = render_activity_roster(timetable, sessions)

    assert "Archery (capacity 1-4 per session):" in text
    assert "1/4" in text  # morning session has exactly 1 occupant, limit 4
    assert "Parent One" in text

    # The empty afternoon Archery session should still be listed, at 0/4.
    assert "0/4" in text

    assert "Craft (capacity 1-2 per session):" in text
    assert "1/2" in text
    assert "Kid One" in text
