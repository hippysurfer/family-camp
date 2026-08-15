from datetime import datetime, timedelta

import pytest

from family_camp2.domain import Activity, Camper, Session, Timetable
from family_camp2.io.schedule_export import (
    ScheduleExportError,
    dump_schedule_csv,
    dump_schedule_json,
    load_schedule_csv,
    load_schedule_json,
)

DAY = datetime(2026, 8, 1, 9, 0)


def _small_timetable():
    archery = Activity("Archery", timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    craft = Activity("Craft", timedelta(minutes=45), min_occupancy=1, max_occupancy=2)
    activities = [archery, craft]

    morning = Session(activity=archery, label="Morning", start=DAY)
    afternoon = Session(activity=craft, label="Afternoon", start=DAY + timedelta(hours=5))
    sessions = [morning, afternoon]

    parent = Camper(name="Parent", family_id="F1", age=40, age_group="Adult", priorities=(archery,))
    kid = Camper(name="Kid", family_id="F1", age=10, age_group="Cub", optional=(craft,))
    campers = [parent, kid]

    timetable = Timetable().with_assignment(parent, morning).with_assignment(kid, afternoon)
    return activities, sessions, campers, timetable


def test_dump_and_load_csv_round_trips(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.csv"

    dump_schedule_csv(timetable, path)
    reloaded = load_schedule_csv(path, activities, sessions, campers)

    assert reloaded == timetable


def test_dump_and_load_json_round_trips(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.json"

    dump_schedule_json(timetable, path)
    reloaded = load_schedule_json(path, activities, sessions, campers)

    assert reloaded == timetable


def test_csv_output_has_expected_header_and_row_count(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.csv"
    dump_schedule_csv(timetable, path)

    lines = path.read_text().strip().splitlines()
    assert lines[0] == "family_id,camper_name,activity_name,session_label,session_start"
    assert len(lines) == 1 + len(timetable)  # header + one row per assignment


def test_load_csv_raises_on_unknown_camper(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.csv"
    path.write_text(
        "family_id,camper_name,activity_name,session_label,session_start\n"
        "F1,Stranger,Archery,Morning,2026-08-01T09:00:00\n"
    )

    with pytest.raises(ScheduleExportError, match="Stranger"):
        load_schedule_csv(path, activities, sessions, campers)


def test_load_json_raises_on_unknown_session(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.json"
    path.write_text(
        '[{"family_id": "F1", "camper_name": "Parent", "activity_name": "Archery", '
        '"session_label": "Evening", "session_start": "2026-08-01T20:00:00"}]'
    )

    with pytest.raises(ScheduleExportError, match="Evening"):
        load_schedule_json(path, activities, sessions, campers)


def test_load_csv_reports_every_bad_row_not_just_the_first(tmp_path):
    """A hand-editing session is likely to have more than one mistake -
    all of them should surface in one error, not just the first, so they
    can all be fixed in one pass."""
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.csv"
    path.write_text(
        "family_id,camper_name,activity_name,session_label,session_start\n"
        "F1,Stranger One,Archery,Morning,2026-08-01T09:00:00\n"
        "F1,Parent,Archery,Nonexistent Label,2026-08-01T09:00:00\n"
        "F1,Stranger Two,Craft,Afternoon,2026-08-01T14:00:00\n"
    )

    with pytest.raises(ScheduleExportError) as excinfo:
        load_schedule_csv(path, activities, sessions, campers)

    message = str(excinfo.value)
    assert "Stranger One" in message
    assert "Nonexistent Label" in message
    assert "Stranger Two" in message
    assert "Row 1" in message
    assert "Row 2" in message
    assert "Row 3" in message


def test_load_csv_with_one_bad_row_among_good_ones_still_reports_it(tmp_path):
    activities, sessions, campers, timetable = _small_timetable()
    path = tmp_path / "schedule.csv"
    dump_schedule_csv(timetable, path)
    # Append one bad row after the good, dumped ones.
    with open(path, "a") as f:
        f.write("F1,Stranger,Archery,Morning,2026-08-01T09:00:00\n")

    with pytest.raises(ScheduleExportError, match="Stranger"):
        load_schedule_csv(path, activities, sessions, campers)
