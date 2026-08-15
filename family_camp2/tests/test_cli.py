import json
from pathlib import Path

import pytest

from family_camp2 import cli
from family_camp2.io.json_loader import load_json
from family_camp2.io.schedule_export import dump_schedule_csv, load_schedule_csv, load_schedule_json
from fixtures import SMALL_CAMP_JSON

_PDF_NAMES = tuple(
    f"{report}_{variant}.pdf"
    for report in ("activities", "campers", "available_adults", "available_families")
    for variant in ("a4_portrait", "a3_landscape")
)


def _out_dir_from_output(out: str) -> Path:
    for line in out.splitlines():
        if line.startswith("Reports written to "):
            return Path(line.removeprefix("Reports written to "))
    raise AssertionError(f"no 'Reports written to <path>' line in output: {out!r}")


def test_cli_runs_end_to_end_with_json_data(tmp_path, capsys):
    exit_code = cli.main(["solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path)])

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


def test_cli_out_dir_defaults_to_fetched_data(tmp_path, monkeypatch, capsys):
    """No --out-dir given at all - defaults to './fetched_data', isolated
    here via chdir so the default doesn't touch the real repo."""
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON)])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out).resolve()
    assert out_dir.parent == tmp_path / "fetched_data"
    assert (out_dir / "status_report.pdf").exists()


def test_cli_output_folder_is_named_from_camp_and_run_timestamp(tmp_path, capsys):
    exit_code = cli.main(["solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path)])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    assert out_dir.parent == tmp_path
    assert out_dir.name.startswith("small_camp_")  # SMALL_CAMP_JSON's own stem
    assert out_dir.name[len("small_camp_") :].replace("_", "").isdigit()  # a run timestamp


def test_cli_two_runs_in_the_same_out_dir_never_collide(tmp_path, capsys):
    for _ in range(2):
        exit_code = cli.main([
            "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
        ])
        assert exit_code == 0
    out_dirs = {p for p in tmp_path.iterdir() if p.is_dir()}
    assert len(out_dirs) == 2  # never overwrote each other, even if run in the same second


def test_cli_writes_a_round_trippable_json_report(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "annealing", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    data = json.loads((out_dir / "report.json").read_text())
    assert "tier0_score" in data
    assert "class1" in data
    assert "class2" in data


def test_cli_solve_loads_custom_constraints_from_data_without_error(tmp_path):
    """Step 43 only proves the data reaches config.constraints - hard/soft
    enforcement is Steps 44/45, not yet wired here, so this just confirms
    a --data file with a "constraints" array solves without error."""
    data = json.loads(SMALL_CAMP_JSON.read_text())
    data["constraints"] = [
        {"family_id": "F1", "camper_name": None, "constraint": "no_activities_on_day(2)", "severity": "hard"},
    ]
    data_path = tmp_path / "with_constraints.json"
    data_path.write_text(json.dumps(data))

    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(data_path), "--out-dir", str(tmp_path / "out"),
    ])

    assert exit_code == 0


def test_cli_progress_defaults_to_stdout_interleaved_with_the_final_report(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--progress-interval", "60",
        "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase1" in out  # a progress line
    assert "Validation Report" in out  # the final report, on the same stream


def test_cli_progress_output_can_be_redirected_to_a_file(tmp_path, capsys):
    progress_path = tmp_path / "progress.log"
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON),
        "--progress-output", str(progress_path),
        "--out-dir", str(tmp_path / "out"),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "phase1" not in out  # progress went to the file, not stdout
    assert "Validation Report" in out  # the final report still prints to stdout

    progress_content = progress_path.read_text()
    assert "phase1" in progress_content


def test_cli_writes_schedule_csv_and_json(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    csv_path = out_dir / "schedule.csv"
    json_path = out_dir / "schedule.json"
    assert csv_path.exists()
    assert json_path.exists()

    activities, sessions, campers, constraints = load_json(SMALL_CAMP_JSON)
    csv_timetable = load_schedule_csv(csv_path, activities, sessions, campers)
    json_timetable = load_schedule_json(json_path, activities, sessions, campers)
    assert csv_timetable == json_timetable
    assert len(csv_timetable) > 0


def test_cli_writes_the_operational_text_reports(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    for name in (
        "family_itinerary.txt",
        "activity_roster.txt",
        "idle_report.txt",
        "unmet_optional_report.txt",
        "unfeasible_families_report.txt",
    ):
        path = out_dir / name
        assert path.exists()
        assert path.read_text().strip() != ""


def test_cli_writes_both_paper_variants_of_all_four_audience_pdfs(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    for name in _PDF_NAMES:
        path = out_dir / name
        assert path.exists()
        assert path.read_bytes().startswith(b"%PDF-")


def test_cli_writes_the_status_report(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    status_report_path = out_dir / "status_report.pdf"
    assert status_report_path.exists()
    assert status_report_path.read_bytes().startswith(b"%PDF-")


def test_cli_writes_nothing_outside_the_run_folder(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path),
    ])

    assert exit_code == 0
    out_dir = _out_dir_from_output(capsys.readouterr().out)
    assert list(tmp_path.iterdir()) == [out_dir]  # nothing else was created directly in --out-dir


# --- revalidate ---


def test_revalidate_requires_a_schedule_argument():
    with pytest.raises(SystemExit):
        cli.main(["revalidate", "--data", str(SMALL_CAMP_JSON)])


def test_revalidate_matches_solve_on_the_schedule_it_exported(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path / "solve_out"),
    ])
    assert exit_code == 0
    solve_report = capsys.readouterr().out
    solve_tier0 = [line for line in solve_report.splitlines() if "Tier 0" in line][0]
    schedule_path = _out_dir_from_output(solve_report) / "schedule.csv"

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(schedule_path),
        "--out-dir", str(tmp_path / "revalidate_out"),
    ])
    assert exit_code == 0
    revalidate_report = capsys.readouterr().out

    assert "Validation Report" in revalidate_report
    assert solve_tier0 in revalidate_report  # same timetable in, same score out - no solver involved


def test_revalidate_accepts_json_schedule_by_extension(tmp_path, capsys):
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path / "solve_out"),
    ])
    schedule_path = _out_dir_from_output(capsys.readouterr().out) / "schedule.json"

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(schedule_path),
        "--out-dir", str(tmp_path / "revalidate_out"),
    ])

    assert exit_code == 0
    assert "Validation Report" in capsys.readouterr().out


def test_revalidate_surfaces_a_hand_introduced_class1_violation(tmp_path, capsys):
    """A hand edit can create a violation a solver's own output never
    could (FR-88) - here, assigning a camper to two sessions of the same
    activity (Archery has both a Morning and an Afternoon session in the
    fixture) - and revalidate must report it, not silently accept it."""
    from family_camp2.domain import Timetable

    activities, sessions, campers, constraints = load_json(SMALL_CAMP_JSON)
    camper = next(c for c in campers if "Archery" in [a.name for a in c.priorities])
    archery_sessions = [s for s in sessions if s.activity.name == "Archery"]
    assert len(archery_sessions) == 2, "fixture must have two Archery sessions for this to be a duplicate"

    bad_timetable = Timetable()
    for s in archery_sessions:
        bad_timetable = bad_timetable.with_assignment(camper, s)
    schedule_path = tmp_path / "bad_schedule.csv"
    dump_schedule_csv(bad_timetable, schedule_path)

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(schedule_path),
        "--out-dir", str(tmp_path / "out"),
    ])

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


def test_revalidate_produces_the_same_report_files_as_solve(tmp_path, capsys):
    """FR-89: revalidate is a second entry point into the same
    _write_outputs, so it must produce the identical set of files solve
    does, not a reduced subset."""
    exit_code = cli.main([
        "solve", "--solver", "cp_sat", "--data", str(SMALL_CAMP_JSON), "--out-dir", str(tmp_path / "solve_out"),
    ])
    solve_out_dir = _out_dir_from_output(capsys.readouterr().out)
    schedule_path = solve_out_dir / "schedule.csv"

    exit_code = cli.main([
        "revalidate", "--data", str(SMALL_CAMP_JSON), "--schedule", str(schedule_path),
        "--out-dir", str(tmp_path / "revalidate_out"),
    ])
    assert exit_code == 0
    revalidate_out_dir = _out_dir_from_output(capsys.readouterr().out)

    solve_names = {p.name for p in solve_out_dir.iterdir()}
    revalidate_names = {p.name for p in revalidate_out_dir.iterdir()}
    assert solve_names == revalidate_names
