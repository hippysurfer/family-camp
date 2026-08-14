import json

import pytest

from family_camp2 import cli
from family_camp2.io.json_loader import load_json
from family_camp2.io.schedule_export import dump_schedule_csv, load_schedule_csv, load_schedule_json
from fixtures import SMALL_CAMP_JSON


def test_cli_runs_end_to_end_with_json_data(capsys):
    exit_code = cli.main(["solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Validation Report" in out


def test_cli_rejects_invalid_solver():
    with pytest.raises(SystemExit):
        cli.main(["solve", "--solver", "bogus", "--data", str(SMALL_CAMP_JSON)])


def test_cli_requires_a_data_source():
    with pytest.raises(SystemExit):
        cli.main(["solve", "--solver", "cp_sat"])


def test_cli_rejects_both_data_sources_at_once(tmp_path):
    fake_cache = tmp_path / ".cache.pickle"
    fake_cache.write_bytes(b"")
    with pytest.raises(SystemExit):
        cli.main([
            "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--legacy-cache", str(fake_cache),
        ])


def test_cli_out_writes_round_trippable_json_report(tmp_path):
    out_path = tmp_path / "report.json"
    exit_code = cli.main(
        ["solve", "--solver", "annealing", "--data", str(SMALL_CAMP_JSON), "--out", str(out_path)]
    )

    assert exit_code == 0
    data = json.loads(out_path.read_text())
    assert "tier0_score" in data
    assert "class1" in data
    assert "class2" in data


def test_cli_progress_defaults_to_stdout_interleaved_with_the_final_report(capsys):
    exit_code = cli.main(
        ["solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--progress-interval", "60"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase1" in out  # a progress line
    assert "Validation Report" in out  # the final report, on the same stream


def test_cli_progress_output_can_be_redirected_to_a_file(tmp_path, capsys):
    progress_path = tmp_path / "progress.log"
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
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
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
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


def test_cli_report_dir_writes_the_operational_reports(tmp_path):
    report_dir = tmp_path / "reports"
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--report-dir", str(report_dir),
    ])

    assert exit_code == 0
    for name in (
        "family_itinerary.txt",
        "activity_roster.txt",
        "idle_report.txt",
        "unmet_optional_report.txt",
        "unfeasible_families_report.txt",
    ):
        path = report_dir / name
        assert path.exists()
        assert path.read_text().strip() != ""


def test_cli_pdf_dir_writes_all_four_pdfs(tmp_path):
    pytest.importorskip("reportlab")
    pdf_dir = tmp_path / "pdfs"
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--pdf-dir", str(pdf_dir), "--pdf-paper", "a3", "--pdf-orientation", "landscape",
    ])

    assert exit_code == 0
    for name in ("activities.pdf", "campers.pdf", "available_adults.pdf", "available_families.pdf"):
        path = pdf_dir / name
        assert path.exists()
        assert path.read_bytes().startswith(b"%PDF-")


# --- revalidate ---


def test_revalidate_requires_a_schedule_argument():
    with pytest.raises(SystemExit):
        cli.main(["revalidate", "--data", str(SMALL_CAMP_JSON)])


def test_revalidate_matches_solve_on_the_schedule_it_exported(tmp_path, capsys):
    export_path = tmp_path / "schedule"
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--export-schedule", str(export_path),
    ])
    assert exit_code == 0
    solve_report = capsys.readouterr().out
    solve_tier0 = [line for line in solve_report.splitlines() if "Tier 0" in line][0]

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(export_path.with_suffix(".csv")),
    ])
    assert exit_code == 0
    revalidate_report = capsys.readouterr().out

    assert "Validation Report" in revalidate_report
    assert solve_tier0 in revalidate_report  # same timetable in, same score out - no solver involved


def test_revalidate_accepts_json_schedule_by_extension(tmp_path, capsys):
    export_path = tmp_path / "schedule"
    cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--export-schedule", str(export_path),
    ])
    capsys.readouterr()

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(export_path.with_suffix(".json")),
    ])

    assert exit_code == 0
    assert "Validation Report" in capsys.readouterr().out


def test_revalidate_surfaces_a_hand_introduced_class1_violation(tmp_path, capsys):
    """A hand edit can create a violation a solver's own output never
    could (FR-88) - here, assigning a camper to two sessions of the same
    activity (Archery has both a Morning and an Afternoon session in the
    fixture) - and revalidate must report it, not silently accept it."""
    from family_camp2.domain import Timetable

    activities, sessions, campers = load_json(SMALL_CAMP_JSON)
    camper = next(c for c in campers if "Archery" in [a.name for a in c.priorities])
    archery_sessions = [s for s in sessions if s.activity.name == "Archery"]
    assert len(archery_sessions) == 2, "fixture must have two Archery sessions for this to be a duplicate"

    bad_timetable = Timetable()
    for s in archery_sessions:
        bad_timetable = bad_timetable.with_assignment(camper, s)
    schedule_path = tmp_path / "bad_schedule.csv"
    dump_schedule_csv(bad_timetable, schedule_path)

    exit_code = cli.main(["revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(schedule_path)])

    assert exit_code == 0  # revalidate succeeds - it *reports* the violation, doesn't crash on it
    out = capsys.readouterr().out
    assert "Feasible: False" in out
    assert "Duplicate activity" in out


def test_revalidate_reports_every_bad_row_not_just_the_first(tmp_path, capsys):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "family_id,camper_name,activity_name,session_label,session_start\n"
        "F1,Nonexistent Camper One,Archery,A,2026-08-01T09:00:00\n"
        "F1,Nonexistent Camper Two,Craft,A,2026-08-01T09:00:00\n"
    )

    with pytest.raises(Exception) as excinfo:
        cli.main(["revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(bad_csv)])

    assert "Nonexistent Camper One" in str(excinfo.value)
    assert "Nonexistent Camper Two" in str(excinfo.value)


def test_revalidate_supports_the_same_output_flags_as_solve(tmp_path, capsys):
    export_path = tmp_path / "schedule"
    cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--export-schedule", str(export_path),
    ])
    capsys.readouterr()

    report_dir = tmp_path / "reports"
    out_path = tmp_path / "report.json"
    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON),
        "--schedule", str(export_path.with_suffix(".csv")),
        "--out", str(out_path),
        "--report-dir", str(report_dir),
    ])

    assert exit_code == 0
    assert out_path.exists()
    assert (report_dir / "family_itinerary.txt").exists()
