import json

import pytest

from family_camp2.io.json_loader import JsonLoadError, load_json
from fixtures import load_small_camp


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
