from datetime import datetime, timedelta

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.reporting import (
    render_activity_roster,
    render_family_itinerary,
    render_idle_report,
    render_unfeasible_families_report,
    render_unmet_optional_report,
)
from family_camp2.validation.feasibility import CamperOverdemand, find_overdemanding_campers
from family_camp2.validation.idle import find_idle_slots
from family_camp2.validation.tiers import UnmetOptionalRequest, find_unmet_optional_requests

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


def test_idle_report_lists_idle_families_and_adults_per_bucket():
    sessions, campers, timetable = _fixture()
    idle_report = find_idle_slots(timetable, campers, sessions, granularity=timedelta(hours=1))

    text = render_idle_report(idle_report)

    # At 09:00, Parent One is in Archery; Kid One and Lonely Two are idle,
    # but only "002/Two" (Lonely Two's family) has *every* member idle -
    # 001/One has Parent One active.
    first_bucket = text.split("\n\n")[0]
    assert "Idle families: 002/Two" in first_bucket
    assert "Idle adults: Lonely Two" in first_bucket


def test_unmet_optional_report_lists_missed_activity_by_camper():
    craft = Activity("Craft", timedelta(minutes=45), min_occupancy=1, max_occupancy=2)
    canoeing = Activity("Canoeing", timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    kid = Camper(name="Kid One", family_id="001/One", age=10, age_group="Cub", optional=(craft, canoeing))
    timetable = Timetable()  # nothing assigned - both optional requests unmet

    unmet = find_unmet_optional_requests(timetable, [kid])
    text = render_unmet_optional_report(unmet)

    assert "Total unmet optional requests: 2" in text
    assert "Craft: 1 camper(s) missed it" in text
    assert "Canoeing: 1 camper(s) missed it" in text
    assert "Kid One (001/One)" in text


def test_unmet_optional_report_empty_when_nothing_missed():
    assert render_unmet_optional_report([]) == "Total unmet optional requests: 0\n"


def test_unfeasible_families_report_groups_by_family():
    craft = Activity("Craft", timedelta(minutes=60), min_occupancy=1, max_occupancy=2)
    canoeing = Activity("Canoeing", timedelta(minutes=60), min_occupancy=1, max_occupancy=2)
    sessions = [Session(craft, "A", DAY), Session(canoeing, "A", DAY)]  # same time - 1 slot max
    kid = Camper(name="Kid One", family_id="001/One", age=10, age_group="Cub", optional=(craft, canoeing))

    overdemand = find_overdemanding_campers(sessions, [kid])
    text = render_unfeasible_families_report(overdemand)

    assert "Families with a structurally overdemanding member: 1" in text
    assert "001/One:" in text
    assert "Kid One: requested 2 activities, only 1 non-overlapping slot(s) available (short by 1)" in text


def test_unfeasible_families_report_empty_when_nothing_flagged():
    assert render_unfeasible_families_report([]) == "Families with a structurally overdemanding member: 0\n"
