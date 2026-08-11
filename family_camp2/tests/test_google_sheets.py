import sys

import pytest

from family_camp2.io.google_sheets import (
    DEFAULT_ACTIVITIES_WORKSHEET,
    DEFAULT_CAMPERS_WORKSHEET,
    DEFAULT_SESSIONS_WORKSHEET,
    fetch_schedule_data,
    get_client,
    open_spreadsheet,
)

HEADER_ROW = ["Group", "First", "Last", "?", "Age", "AgeGroup", "?", "?", "Priorities", "Others"]


class FakeWorksheet:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


class FakeSpreadsheet:
    def __init__(self, worksheets: dict[str, FakeWorksheet]):
        self._worksheets = worksheets
        self.requested_names = []

    def worksheet(self, name):
        self.requested_names.append(name)
        return self._worksheets[name]


class FakeClient:
    def __init__(self, spreadsheet: FakeSpreadsheet):
        self._spreadsheet = spreadsheet
        self.opened_by_key = None
        self.opened_by_url = None

    def open_by_key(self, key):
        self.opened_by_key = key
        return self._spreadsheet

    def open_by_url(self, url):
        self.opened_by_url = url
        return self._spreadsheet


def _fake_spreadsheet():
    acts_wks = [
        ["Archery", "1:00:00", "1", "4"],
        ["Craft", "0:45:00", "1", "2"],
    ]
    session_wks = [
        ["Archery", "Morning", "01/08/2026 09:00:00"],
    ]
    campers_wks = [
        HEADER_ROW,
        ["F1", "Kid", "One", "?", "10", "Cub", "?", "?", "Archery", "Craft"],
    ]
    return FakeSpreadsheet(
        {
            DEFAULT_ACTIVITIES_WORKSHEET: FakeWorksheet(acts_wks),
            DEFAULT_SESSIONS_WORKSHEET: FakeWorksheet(session_wks),
            DEFAULT_CAMPERS_WORKSHEET: FakeWorksheet(campers_wks),
        }
    )


def test_open_spreadsheet_uses_key_for_a_bare_id():
    spreadsheet = _fake_spreadsheet()
    client = FakeClient(spreadsheet)

    result = open_spreadsheet(client, "abc123")

    assert result is spreadsheet
    assert client.opened_by_key == "abc123"
    assert client.opened_by_url is None


def test_open_spreadsheet_uses_url_for_a_url():
    spreadsheet = _fake_spreadsheet()
    client = FakeClient(spreadsheet)
    url = "https://docs.google.com/spreadsheets/d/abc123/edit"

    result = open_spreadsheet(client, url)

    assert result is spreadsheet
    assert client.opened_by_url == url
    assert client.opened_by_key is None


def test_fetch_schedule_data_parses_the_three_worksheets():
    spreadsheet = _fake_spreadsheet()
    client = FakeClient(spreadsheet)

    activities, sessions, campers = fetch_schedule_data(client, "abc123")

    assert {a.name for a in activities} == {"Archery", "Craft"}
    assert len(sessions) == 1
    assert sessions[0].label == "Morning"
    assert len(campers) == 1
    assert campers[0].name == "Kid One"
    assert spreadsheet.requested_names == [
        DEFAULT_ACTIVITIES_WORKSHEET,
        DEFAULT_SESSIONS_WORKSHEET,
        DEFAULT_CAMPERS_WORKSHEET,
    ]


def test_fetch_schedule_data_accepts_custom_worksheet_names():
    acts_wks = [["Archery", "1:00:00", "1", "4"]]
    spreadsheet = FakeSpreadsheet(
        {
            "MyActivities": FakeWorksheet(acts_wks),
            "MySessions": FakeWorksheet([]),
            "MyCampers": FakeWorksheet([HEADER_ROW]),
        }
    )
    client = FakeClient(spreadsheet)

    activities, sessions, campers = fetch_schedule_data(
        client, "abc123",
        activities_worksheet="MyActivities",
        sessions_worksheet="MySessions",
        campers_worksheet="MyCampers",
    )

    assert {a.name for a in activities} == {"Archery"}
    assert sessions == []
    assert campers == []


def test_get_client_raises_a_clear_error_when_gspread_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "gspread", None)

    with pytest.raises(ImportError, match=r"pip install -e '\.\[google\]'"):
        get_client()
