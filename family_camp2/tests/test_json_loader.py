import json

import pytest

from family_camp2.constraints.parser import ConstraintParseError
from family_camp2.io.json_loader import JsonLoadError, dump_json, load_json, peek_camp_name
from fixtures import SMALL_CAMP_JSON, load_small_camp


def test_small_camp_loads_expected_counts():
    activities, sessions, campers = load_small_camp()

    assert len(activities) == 3
    assert len(sessions) == 4
    assert len(campers) == 5

    by_name = {a.name: a for a in activities}
    assert by_name["Canoeing"].min_age == 8
    assert by_name["Archery"].max_occupancy == 4

    kid1 = next(c for c in campers if c.name == "Kid1")
    assert kid1.family_id == "F1"
    assert [a.name for a in kid1.priorities] == ["Canoeing"]


def test_session_with_unknown_activity_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "activities": [],
        "sessions": [{"activity": "Archery", "label": "Morning", "start": "2026-08-01T09:00:00"}],
        "campers": [],
    }))

    with pytest.raises(JsonLoadError, match="Archery"):
        load_json(path)


def test_camper_with_unknown_priority_activity_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "activities": [],
        "sessions": [],
        "campers": [{
            "name": "Kid", "family_id": "F1", "age": 10, "age_group": "Cub",
            "priorities": ["Archery"], "optional": [],
        }],
    }))

    with pytest.raises(JsonLoadError, match="Kid"):
        load_json(path)


def test_camper_with_unknown_optional_activity_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "activities": [],
        "sessions": [],
        "campers": [{
            "name": "Kid", "family_id": "F1", "age": 10, "age_group": "Cub",
            "priorities": [], "optional": ["Craft"],
        }],
    }))

    with pytest.raises(JsonLoadError, match="Craft"):
        load_json(path)


def test_small_camp_has_no_constraints_by_default():
    activities, sessions, campers, constraints = load_json(SMALL_CAMP_JSON)
    assert constraints == []


def test_camp_with_a_family_level_constraint(tmp_path):
    path = tmp_path / "with_constraints.json"
    path.write_text(json.dumps({
        "activities": [],
        "sessions": [],
        "campers": [
            {"name": "Kid", "family_id": "F1", "age": 10, "age_group": "Cub", "priorities": [], "optional": []},
        ],
        "constraints": [
            {"family_id": "F1", "camper_name": None, "constraint": "no_activities_on_day(2)", "severity": "hard"},
        ],
    }))

    activities, sessions, campers, constraints = load_json(path)

    assert len(constraints) == 1
    assert constraints[0].severity == "hard"
    assert [c.name for c in constraints[0].targets] == ["Kid"]


def test_camp_with_an_unresolvable_constraint_raises_constraint_parse_error(tmp_path):
    path = tmp_path / "bad_constraints.json"
    path.write_text(json.dumps({
        "activities": [],
        "sessions": [],
        "campers": [],
        "constraints": [
            {"family_id": "F1", "camper_name": None, "constraint": "no_activities_on_day(2)", "severity": "hard"},
        ],
    }))

    with pytest.raises(ConstraintParseError, match="F1"):
        load_json(path)


def test_dump_json_round_trips_through_load_json(tmp_path):
    activities, sessions, campers = load_small_camp()

    out_path = tmp_path / "round_trip.json"
    dump_json(activities, sessions, campers, out_path)
    reloaded_activities, reloaded_sessions, reloaded_campers, reloaded_constraints = load_json(out_path)

    assert {a.name for a in reloaded_activities} == {a.name for a in activities}
    assert set(reloaded_activities) == set(activities)
    assert set(reloaded_sessions) == set(sessions)
    assert set(reloaded_campers) == set(campers)
    assert reloaded_constraints == []


def test_dump_json_round_trips_constraint_records(tmp_path):
    activities, sessions, campers = load_small_camp()
    records = [
        {"family_id": "F1", "camper_name": None, "constraint": "no_activities_on_day(2)", "severity": "hard"},
    ]

    out_path = tmp_path / "round_trip.json"
    dump_json(activities, sessions, campers, out_path, constraint_records=records)
    _, _, _, reloaded_constraints = load_json(out_path)

    assert len(reloaded_constraints) == 1
    assert reloaded_constraints[0].severity == "hard"


def test_dump_json_output_matches_documented_schema(tmp_path):
    activities, sessions, campers = load_small_camp()

    out_path = tmp_path / "round_trip.json"
    dump_json(activities, sessions, campers, out_path)
    data = json.loads(out_path.read_text())

    assert set(data.keys()) == {"activities", "sessions", "campers", "constraints", "camp_name"}
    archery = next(a for a in data["activities"] if a["name"] == "Archery")
    assert archery["duration_minutes"] == 60
    assert archery["max_occupancy"] == 4

    kid1_session = next(s for s in data["sessions"] if s["label"] == "Morning" and s["activity"] == "Archery")
    assert kid1_session["start"] == "2026-08-01T09:00:00"


def test_dump_json_writes_the_given_camp_name(tmp_path):
    activities, sessions, campers = load_small_camp()
    out_path = tmp_path / "with_name.json"

    dump_json(activities, sessions, campers, out_path, camp_name="Willesley 2026")

    assert json.loads(out_path.read_text())["camp_name"] == "Willesley 2026"


def test_dump_json_defaults_camp_name_to_null(tmp_path):
    activities, sessions, campers = load_small_camp()
    out_path = tmp_path / "no_name.json"

    dump_json(activities, sessions, campers, out_path)

    assert json.loads(out_path.read_text())["camp_name"] is None


def test_peek_camp_name_reads_the_field_without_full_load(tmp_path):
    path = tmp_path / "named.json"
    path.write_text(json.dumps({"activities": [], "sessions": [], "campers": [], "camp_name": "Willesley 2026"}))

    assert peek_camp_name(path) == "Willesley 2026"


def test_peek_camp_name_returns_none_when_the_field_is_absent():
    assert peek_camp_name(SMALL_CAMP_JSON) is None
