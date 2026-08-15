import sys

import pytest

from family_camp2.io.google_sheets import (
    DEFAULT_ACTIVITIES_WORKSHEET,
    DEFAULT_CAMPERS_WORKSHEET,
    DEFAULT_CONSTRAINTS_WORKSHEET,
    DEFAULT_SESSIONS_WORKSHEET,
    GoogleSheetsFetchError,
    _extract_table,
    _parse_age,
    fetch_schedule_data,
    get_client,
    open_spreadsheet,
)

# Structure mirrors a real "Willesley 2026" sheet: a preamble row, a header
# row, occasional blank rows (including one right after the campers header
# for no obvious reason), and a non-blank footer note after the real data
# on the activities sheet that must NOT be parsed as an activity.
ACTIVITIES_ROWS = [
    ["", "", "", "", "", ""],
    ["Activity", "Duration (mins)", "Min", "Limit", "Number of Sessions", "Total Spaces"],
    ["Archery", "1:00:00", "1", "4", "2", "8"],
    ["Craft", "0:45:00", "1", "2", "1", "2"],
    ["", "", "", "", "", ""],
    ["Used by scheduling software", "", "", "", "", ""],
]

SESSIONS_ROWS = [
    ["Activity", "Label", "Start time", "End time", "Duration", "Weekday", "Day"],
    ["Archery", "Archery", "01/08/2026 09:00:00", "01/08/2026 09:59:00", "0:59:00", "6", "Saturday"],
    ["Craft", "Craft", "01/08/2026 10:00:00", "01/08/2026 10:44:00", "0:44:00", "6", "Saturday"],
]

# "Extra" (index 9) holds schedulable nice-to-have activities (the true
# FR-20 optional list) and "Other" (index 10) holds non-schedulable camp
# attractions - confirmed against the real sheet, despite what the column
# names alone might suggest.
CAMPERS_ROWS = [
    ["Group Ref", "Group Name", "First Name", "Surname", "Diet", "18?", "Age", "DBS", "Priority", "Extra", "Other"],
    ["", "", "", "", "", "", "", "", "", "", ""],
    ["001/One", "One", "Parent", "One", "", "Adult (over 18 years)", "18+", "Received", "Archery", "", ""],
    ["001/One", "One", "Kid", "One", "None", "Child (between 5 and 18 years)", "10", "", "", "Craft", ""],
    ["002/Two", "Two", "Alex", "Two", "", "Adult (over 18 years)", "", "Received", "", "", ""],
]

# A new, optional tab (REQUIREMENTS.md §3.5) - preamble row, then a header
# reusing "Group Ref" from the Campers tab, matching the realism of the
# other fixtures above.
CONSTRAINTS_ROWS = [
    ["Custom constraints - see README for syntax", "", "", "", ""],
    ["Group Ref", "Camper Name", "Constraint", "Severity", "Note"],
    ["001/One", "Kid One", "no_activity_before(time=\"11:00\")", "hard", "sleeps in"],
    ["001/One", "", "no_activities_on_day(2)", "soft", ""],
]


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


def _real_shaped_spreadsheet(campers_rows=CAMPERS_ROWS):
    return FakeSpreadsheet(
        {
            DEFAULT_ACTIVITIES_WORKSHEET: FakeWorksheet(ACTIVITIES_ROWS),
            DEFAULT_SESSIONS_WORKSHEET: FakeWorksheet(SESSIONS_ROWS),
            DEFAULT_CAMPERS_WORKSHEET: FakeWorksheet(campers_rows),
        }
    )


def test_open_spreadsheet_uses_key_for_a_bare_id():
    spreadsheet = _real_shaped_spreadsheet()
    client = FakeClient(spreadsheet)

    result = open_spreadsheet(client, "abc123")

    assert result is spreadsheet
    assert client.opened_by_key == "abc123"
    assert client.opened_by_url is None


def test_open_spreadsheet_uses_url_for_a_url():
    spreadsheet = _real_shaped_spreadsheet()
    client = FakeClient(spreadsheet)
    url = "https://docs.google.com/spreadsheets/d/abc123/edit"

    result = open_spreadsheet(client, url)

    assert result is spreadsheet
    assert client.opened_by_url == url
    assert client.opened_by_key is None


def test_extract_table_skips_preamble_and_stops_at_first_blank_after_data():
    header, data_rows = _extract_table(ACTIVITIES_ROWS, "Activity")

    assert header == ACTIVITIES_ROWS[1]
    assert [r[0] for r in data_rows] == ["Archery", "Craft"]  # footer note excluded


def test_extract_table_skips_a_leading_blank_row_after_the_header():
    header, data_rows = _extract_table(CAMPERS_ROWS, "Group Ref")

    assert len(data_rows) == 3
    assert data_rows[0][0] == "001/One"  # the blank template row is skipped, not mistaken for data


def test_extract_table_raises_when_header_marker_not_found():
    with pytest.raises(GoogleSheetsFetchError, match="Group Ref"):
        _extract_table(ACTIVITIES_ROWS, "Group Ref")


@pytest.mark.parametrize(
    "age_text,age_group_text,expected",
    [
        ("18+", "Adult (over 18 years)", 18),
        ("10", "Child (between 5 and 18 years)", 10),
        ("", "Adult (over 18 years)", 18),  # blank age, falls back on age-group
        ("", "Infant (under 5 years)", 2),
        ("", "Child (between 5 and 18 years)", 10),
    ],
)
def test_parse_age_handles_real_world_messiness(age_text, age_group_text, expected):
    assert _parse_age(age_text, age_group_text) == expected


def test_fetch_schedule_data_parses_the_three_worksheets():
    spreadsheet = _real_shaped_spreadsheet()
    client = FakeClient(spreadsheet)

    activities, sessions, campers, constraints = fetch_schedule_data(client, "abc123")

    assert {a.name for a in activities} == {"Archery", "Craft"}
    assert len(sessions) == 2
    assert len(campers) == 3

    parent = next(c for c in campers if c.name == "Parent One")
    assert parent.family_id == "001/One"
    assert parent.age == 18  # "18+" parsed
    assert [a.name for a in parent.priorities] == ["Archery"]

    kid = next(c for c in campers if c.name == "Kid One")
    assert kid.age == 10
    assert [a.name for a in kid.optional] == ["Craft"]  # from the "Extra" column

    blank_age_adult = next(c for c in campers if c.name == "Alex Two")
    assert blank_age_adult.age == 18  # blank Age column, falls back via "18?" column

    assert constraints == []  # constraints_worksheet not given - not fetched at all


def test_fetch_schedule_data_uses_extra_column_not_other_column_for_optional():
    """Regression guard, confirmed against the real sheet: "Extra" holds
    schedulable nice-to-have activities (the true optional list); "Other"
    holds non-schedulable camp attractions and must never be read as if it
    were the optional list."""
    campers_rows = [
        CAMPERS_ROWS[0],
        ["001/One", "One", "Parent", "One", "", "Adult (over 18 years)", "40", "", "", "", "Craft"],
    ]
    spreadsheet = _real_shaped_spreadsheet(campers_rows=campers_rows)
    client = FakeClient(spreadsheet)

    _, _, campers, _ = fetch_schedule_data(client, "abc123")

    # "Craft" is a perfectly valid activity, just sitting in the column
    # that's never read for this purpose - not flagged as unknown, simply ignored.
    assert campers[0].optional == ()


def test_fetch_schedule_data_skips_and_warns_about_unschedulable_activity_references():
    """A camper referencing an activity that isn't in "Activities for
    schedule" at all (verified against the real sheet: e.g. non-schedulable
    camp attractions like "Silent Disco" that live in the "Other" column,
    or simply a typo/unknown name) has that reference dropped, with a
    single summary warning - not a hard failure, since unlike
    json_loader/legacy_cache_loader's inputs, a live registration sheet
    legitimately covers a broader set of interests than what needs session
    scheduling."""
    campers_rows = [
        CAMPERS_ROWS[0],
        ["001/One", "One", "Parent", "One", "", "Adult (over 18 years)", "40", "", "Fencing", "", ""],
    ]
    spreadsheet = _real_shaped_spreadsheet(campers_rows=campers_rows)
    client = FakeClient(spreadsheet)

    with pytest.warns(UserWarning, match="Fencing"):
        _, _, campers, _ = fetch_schedule_data(client, "abc123")

    assert campers[0].priorities == ()
    assert campers[0].optional == ()


def test_fetch_schedule_data_accepts_custom_worksheet_names():
    spreadsheet = FakeSpreadsheet(
        {
            "MyActivities": FakeWorksheet(ACTIVITIES_ROWS),
            "MySessions": FakeWorksheet(SESSIONS_ROWS),
            "MyCampers": FakeWorksheet(CAMPERS_ROWS),
            "MyConstraints": FakeWorksheet(CONSTRAINTS_ROWS),
        }
    )
    client = FakeClient(spreadsheet)

    activities, sessions, campers, constraints = fetch_schedule_data(
        client, "abc123",
        activities_worksheet="MyActivities",
        sessions_worksheet="MySessions",
        campers_worksheet="MyCampers",
        constraints_worksheet="MyConstraints",
    )

    assert {a.name for a in activities} == {"Archery", "Craft"}
    assert spreadsheet.requested_names == ["MyActivities", "MySessions", "MyCampers", "MyConstraints"]
    assert len(constraints) == 2


def test_fetch_schedule_data_does_not_touch_the_constraints_tab_by_default():
    """§3.5's constraints tab is optional - unlike the other three, most
    spreadsheets won't have it, so fetch_schedule_data must not even try to
    open it unless a worksheet name is explicitly given."""
    spreadsheet = _real_shaped_spreadsheet()
    client = FakeClient(spreadsheet)

    fetch_schedule_data(client, "abc123")

    assert DEFAULT_CONSTRAINTS_WORKSHEET not in spreadsheet.requested_names


def test_fetch_schedule_data_parses_the_constraints_worksheet_into_raw_records():
    spreadsheet = FakeSpreadsheet(
        {
            DEFAULT_ACTIVITIES_WORKSHEET: FakeWorksheet(ACTIVITIES_ROWS),
            DEFAULT_SESSIONS_WORKSHEET: FakeWorksheet(SESSIONS_ROWS),
            DEFAULT_CAMPERS_WORKSHEET: FakeWorksheet(CAMPERS_ROWS),
            DEFAULT_CONSTRAINTS_WORKSHEET: FakeWorksheet(CONSTRAINTS_ROWS),
        }
    )
    client = FakeClient(spreadsheet)

    _, _, _, constraints = fetch_schedule_data(
        client, "abc123", constraints_worksheet=DEFAULT_CONSTRAINTS_WORKSHEET
    )

    assert constraints == [
        {
            "family_id": "001/One",
            "camper_name": "Kid One",
            "constraint": 'no_activity_before(time="11:00")',
            "severity": "hard",
            "note": "sleeps in",
        },
        {
            "family_id": "001/One",
            "camper_name": None,
            "constraint": "no_activities_on_day(2)",
            "severity": "soft",
            "note": "",
        },
    ]


def test_get_client_raises_a_clear_error_when_gspread_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "gspread", None)

    with pytest.raises(ImportError, match=r"pip install -e '\.\[google\]'"):
        get_client()
