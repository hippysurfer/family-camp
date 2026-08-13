import json

import pytest

from family_camp2 import cli
from family_camp2.io.json_loader import load_json
from family_camp2.io.schedule_export import load_schedule_csv, load_schedule_json
from fixtures import SMALL_CAMP_JSON


def test_cli_runs_end_to_end_with_json_data(capsys):
    exit_code = cli.main(["--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Validation Report" in out


def test_cli_rejects_invalid_solver():
    with pytest.raises(SystemExit):
        cli.main(["--solver", "bogus", "--data", str(SMALL_CAMP_JSON)])


def test_cli_requires_a_data_source():
    with pytest.raises(SystemExit):
        cli.main(["--solver", "cp_sat"])


def test_cli_rejects_both_data_sources_at_once(tmp_path):
    fake_cache = tmp_path / ".cache.pickle"
    fake_cache.write_bytes(b"")
    with pytest.raises(SystemExit):
        cli.main(["--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--legacy-cache", str(fake_cache)])


def test_cli_out_writes_round_trippable_json_report(tmp_path):
    out_path = tmp_path / "report.json"
    exit_code = cli.main(
        ["--solver", "annealing", "--data", str(SMALL_CAMP_JSON), "--out", str(out_path)]
    )

    assert exit_code == 0
    data = json.loads(out_path.read_text())
    assert "tier0_score" in data
    assert "class1" in data
    assert "class2" in data


def test_cli_progress_defaults_to_stdout_interleaved_with_the_final_report(capsys):
    exit_code = cli.main(
        ["--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--progress-interval", "60"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase1" in out  # a progress line
    assert "Validation Report" in out  # the final report, on the same stream


def test_cli_progress_output_can_be_redirected_to_a_file(tmp_path, capsys):
    progress_path = tmp_path / "progress.log"
    exit_code = cli.main([
        "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--progress-output", str(progress_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase1" not in out  # progress went to the file, not stdout
    assert "Validation Report" in out  # the final report still prints to stdout

    progress_content = progress_path.read_text()
    assert "phase1" in progress_content


def test_cli_export_schedule_writes_both_csv_and_json(tmp_path):
    export_path = tmp_path / "schedule"  # deliberately no extension
    exit_code = cli.main([
        "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--export-schedule", str(export_path),
    ])

    assert exit_code == 0
    csv_path = export_path.with_suffix(".csv")
    json_path = export_path.with_suffix(".json")
    assert csv_path.exists()
    assert json_path.exists()

    activities, sessions, campers = load_json(SMALL_CAMP_JSON)
    csv_timetable = load_schedule_csv(csv_path, activities, sessions, campers)
    json_timetable = load_schedule_json(json_path, activities, sessions, campers)
    assert csv_timetable == json_timetable
    assert len(csv_timetable) > 0


def test_cli_report_dir_writes_the_three_operational_reports(tmp_path):
    report_dir = tmp_path / "reports"
    exit_code = cli.main([
        "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--report-dir", str(report_dir),
    ])

    assert exit_code == 0
    for name in ("family_itinerary.txt", "activity_roster.txt", "idle_report.txt"):
        path = report_dir / name
        assert path.exists()
        assert path.read_text().strip() != ""
