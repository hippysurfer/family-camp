import pickle

import pytest

from family_camp2.io.legacy_cache_loader import LegacyCacheLoadError, load_legacy_cache

HEADER_ROW = ["Group", "First", "Last", "?", "Age", "AgeGroup", "?", "?", "Priorities", "Others"]


def write_cache(tmp_path, acts_wks, session_wks, campers_wks):
    path = tmp_path / ".cache.pickle"
    with open(path, "wb") as f:
        pickle.dump((acts_wks, session_wks, campers_wks), f)
    return path


def test_legacy_cache_parses_into_expected_domain_objects(tmp_path):
    acts_wks = [
        ["Archery", "1:00:00", "1", "4"],
        ["Craft", "0:45:00", "1", "2"],
        ["", "", "", ""],  # trailing blank row, must be skipped
    ]
    session_wks = [
        ["Archery", "Morning", "01/08/2026 09:00:00"],
    ]
    campers_wks = [
        HEADER_ROW,
        ["F1", "Kid", "One", "?", "10", "Cub", "?", "?", "Archery", "Craft"],
    ]
    path = write_cache(tmp_path, acts_wks, session_wks, campers_wks)

    activities, sessions, campers = load_legacy_cache(path)

    assert {a.name for a in activities} == {"Archery", "Craft"}
    assert len(sessions) == 1
    assert sessions[0].label == "Morning"
    assert sessions[0].start.strftime("%d/%m/%Y %H:%M:%S") == "01/08/2026 09:00:00"

    assert len(campers) == 1
    kid = campers[0]
    assert kid.name == "Kid One"
    assert kid.family_id == "F1"
    assert kid.age == 10
    assert [a.name for a in kid.priorities] == ["Archery"]
    assert [a.name for a in kid.optional] == ["Craft"]

    archery = next(a for a in activities if a.name == "Archery")
    assert archery.min_age is None  # legacy schema predates OQ-8


def test_session_with_unknown_activity_raises(tmp_path):
    acts_wks = []
    session_wks = [["Archery", "Morning", "01/08/2026 09:00:00"]]
    campers_wks = [HEADER_ROW]
    path = write_cache(tmp_path, acts_wks, session_wks, campers_wks)

    with pytest.raises(LegacyCacheLoadError, match="Archery"):
        load_legacy_cache(path)


def test_camper_with_unknown_priority_activity_raises(tmp_path):
    acts_wks = []
    session_wks = []
    campers_wks = [
        HEADER_ROW,
        ["F1", "Kid", "One", "?", "10", "Cub", "?", "?", "Archery", ""],
    ]
    path = write_cache(tmp_path, acts_wks, session_wks, campers_wks)

    with pytest.raises(LegacyCacheLoadError, match="Kid One"):
        load_legacy_cache(path)
