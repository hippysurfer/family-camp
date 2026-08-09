import json

import pytest

from family_camp2 import cli
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
