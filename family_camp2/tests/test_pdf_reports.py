from datetime import datetime, timedelta

import pytest

pytest.importorskip("reportlab")  # pdf_reports.py is only usable with the optional 'pdf' extra installed

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.pdf_reports import PageSpec, _activity_label, _short_name, render_activities_pdf, render_campers_pdf

DAY = datetime(2026, 8, 1, 9, 0)


def activity(name, minutes=60, min_occ=1, max_occ=10):
    return Activity(name=name, duration=timedelta(minutes=minutes), min_occupancy=min_occ, max_occupancy=max_occ)


def session(act, label, hour):
    return Session(activity=act, label=label, start=DAY + timedelta(hours=hour))


def camper(name, family="F1", age=10, age_group="Cub", priorities=(), optional=()):
    return Camper(name=name, family_id=family, age=age, age_group=age_group, priorities=priorities, optional=optional)


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


def _assert_valid_pdf(path):
    assert path.exists()
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 500  # trivially small output would indicate an empty/broken document


# --- PageSpec ---


def test_page_spec_default_is_a4_portrait():
    from reportlab.lib.pagesizes import A4

    assert PageSpec().pagesize == A4


def test_page_spec_a3_landscape_is_wider_than_tall():
    spec = PageSpec("a3", "landscape")
    width, height = spec.pagesize
    assert width > height


def test_page_spec_rejects_unknown_paper_size():
    with pytest.raises(ValueError, match="paper_size"):
        PageSpec("a5", "portrait")


def test_page_spec_rejects_unknown_orientation():
    with pytest.raises(ValueError, match="orientation"):
        PageSpec("a4", "sideways")


# --- _activity_label / _short_name (pure helpers, no PDF needed) ---


def test_activity_label_suppressed_when_identical_to_activity_name():
    craft = activity("Craft")
    s = session(craft, "Craft", 9)  # label happens to repeat the activity name
    assert _activity_label(s) == ""


def test_activity_label_kept_when_it_differs():
    craft = activity("Craft")
    s = session(craft, "Group A", 9)
    assert _activity_label(s) == " (Group A)"


def test_short_name_drops_matching_family_surname():
    c = camper("Christopher Winwood", family="012/Winwood")
    assert _short_name(c, "Winwood") == "Christopher"


def test_short_name_keeps_full_name_when_surname_differs():
    c = camper("Shevonne Hodson-Walker", family="012/Winwood")
    assert _short_name(c, "Winwood") == "Shevonne Hodson-Walker"


def test_short_name_keeps_full_name_when_no_family_surname_given():
    c = camper("Kid One")
    assert _short_name(c, None) == "Kid One"


# --- render_activities_pdf / render_campers_pdf ---


@pytest.mark.parametrize("paper_size", ["a4", "a3"])
@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_render_activities_pdf_produces_a_valid_pdf(tmp_path, paper_size, orientation):
    sessions, campers, timetable = _fixture()
    out = tmp_path / "activities.pdf"

    render_activities_pdf(timetable, sessions, out, PageSpec(paper_size, orientation))

    _assert_valid_pdf(out)


@pytest.mark.parametrize("paper_size", ["a4", "a3"])
@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_render_campers_pdf_produces_a_valid_pdf(tmp_path, paper_size, orientation):
    sessions, campers, timetable = _fixture()
    out = tmp_path / "campers.pdf"

    render_campers_pdf(timetable, campers, out, PageSpec(paper_size, orientation))

    _assert_valid_pdf(out)


def test_render_campers_pdf_handles_a_family_with_no_assignments(tmp_path):
    sessions, campers, timetable = _fixture()  # includes "002/Two" (Lonely Two), never assigned
    out = tmp_path / "campers.pdf"

    render_campers_pdf(timetable, campers, out)

    _assert_valid_pdf(out)


def test_render_campers_pdf_falls_back_to_list_for_a_large_family(tmp_path):
    """A family with many long-named members should still produce a valid,
    non-crashing PDF via the [session, attendees] list fallback (matrix
    columns would otherwise be too narrow to be legible)."""
    craft = activity("Craft", max_occ=20)
    s = session(craft, "A", 9)
    members = [
        camper(f"Alexandria Christopherson{i}", family="F1", optional=(craft,)) for i in range(8)
    ]
    timetable = Timetable()
    for m in members:
        timetable = timetable.with_assignment(m, s)
    out = tmp_path / "campers.pdf"

    render_campers_pdf(timetable, members, out, PageSpec("a4", "portrait"))

    _assert_valid_pdf(out)
