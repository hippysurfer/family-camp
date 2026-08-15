from datetime import datetime, timedelta

import pytest

from family_camp2 import fetch_cli
from family_camp2.domain import Activity, Camper, Session
from family_camp2.io.json_loader import load_json


def test_build_parser_requires_sheet_id_and_out():
    with pytest.raises(SystemExit):
        fetch_cli.build_parser().parse_args([])


def test_build_parser_accepts_minimal_args():
    args = fetch_cli.build_parser().parse_args(["--sheet-id", "abc123", "--out", "data.json"])
    assert args.sheet_id == "abc123"
    assert str(args.out) == "data.json"
    assert args.credentials is None


def _canned_data():
    archery = Activity(name="Archery", duration=timedelta(minutes=60), min_occupancy=1, max_occupancy=4)
    session = Session(activity=archery, label="Morning", start=datetime(2026, 8, 1, 9, 0))
    kid = Camper(name="Kid", family_id="F1", age=10, age_group="Cub", priorities=(archery,))
    return [archery], [session], [kid]


def test_main_fetches_and_writes_json_without_real_network_or_oauth(monkeypatch, tmp_path, capsys):
    calls = {}

    def fake_get_client(credentials_path=None, authorized_user_path=None):
        calls["get_client"] = (credentials_path, authorized_user_path)
        return "sentinel-client"

    def fake_fetch_schedule_data(client, sheet_id_or_url, activities_worksheet, sessions_worksheet, campers_worksheet):
        calls["fetch"] = (client, sheet_id_or_url, activities_worksheet, sessions_worksheet, campers_worksheet)
        return _canned_data()

    monkeypatch.setattr(fetch_cli, "get_client", fake_get_client)
    monkeypatch.setattr(fetch_cli, "fetch_schedule_data", fake_fetch_schedule_data)

    out_path = tmp_path / "data.json"
    exit_code = fetch_cli.main(["--sheet-id", "abc123", "--out", str(out_path)])

    assert exit_code == 0
    assert calls["get_client"] == (None, None)
    assert calls["fetch"][0] == "sentinel-client"
    assert calls["fetch"][1] == "abc123"

    activities, sessions, campers, constraints = load_json(out_path)
    assert [a.name for a in activities] == ["Archery"]
    assert [c.name for c in campers] == ["Kid"]

    out = capsys.readouterr().out
    assert "1 activities" in out
    assert str(out_path) in out


def test_main_passes_through_credentials_and_worksheet_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_cli, "get_client", lambda credentials_path=None, authorized_user_path=None: "client")
    seen = {}

    def fake_fetch(client, sheet_id_or_url, activities_worksheet, sessions_worksheet, campers_worksheet):
        seen["worksheets"] = (activities_worksheet, sessions_worksheet, campers_worksheet)
        return _canned_data()

    monkeypatch.setattr(fetch_cli, "fetch_schedule_data", fake_fetch)

    out_path = tmp_path / "data.json"
    fetch_cli.main([
        "--sheet-id", "abc123", "--out", str(out_path),
        "--activities-worksheet", "MyActs",
        "--sessions-worksheet", "MySessions",
        "--campers-worksheet", "MyCampers",
    ])

    assert seen["worksheets"] == ("MyActs", "MySessions", "MyCampers")
