import json

import pytest

from family_camp2.config import ConfigError, EngineConfig, load_config


def test_default_config_with_no_path():
    config = load_config(None)
    assert config == EngineConfig()
    assert config.objective_order == ("tier0", "tier1", "tier2")
    assert config.compulsory_activities == ()
    assert config.constraints == ()


def test_constraints_is_not_a_config_file_field(tmp_path):
    """Constraints are camp data: they flow in via --data, not the
    --config JSON file - a config file that tries to set them is rejected
    like any other unknown key."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"constraints": []}))

    with pytest.raises(ConfigError, match="constraints"):
        load_config(path)


def test_valid_json_overrides_specific_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "objective_order": ["tier1", "tier0", "tier2"],
        "compulsory_activities": ["Saturday BBQ"],
        "tier0_weights": {"missing_priority": 5},
    }))

    config = load_config(path)

    assert config.objective_order == ("tier1", "tier0", "tier2")
    assert config.compulsory_activities == ("Saturday BBQ",)
    assert config.tier0_weights.missing_priority == 5
    # unspecified weight fields keep their defaults
    assert config.tier0_weights.family_safety == EngineConfig().tier0_weights.family_safety


def test_family_split_weight_is_a_valid_override(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tier0_weights": {"family_split": 7}}))

    config = load_config(path)

    assert config.tier0_weights.family_split == 7
    assert config.tier0_weights.family_safety == EngineConfig().tier0_weights.family_safety


def test_custom_constraint_weight_is_a_valid_override(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tier0_weights": {"custom_constraint": 42}}))

    config = load_config(path)

    assert config.tier0_weights.custom_constraint == 42
    assert config.tier0_weights.family_safety == EngineConfig().tier0_weights.family_safety


def test_unknown_top_level_key_raises_naming_the_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tierzero_weights": {}}))

    with pytest.raises(ConfigError, match="tierzero_weights"):
        load_config(path)


def test_unknown_tier0_weight_key_raises_naming_the_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tier0_weights": {"missing_priorty": 1}}))

    with pytest.raises(ConfigError, match="missing_priorty"):
        load_config(path)


def test_duplicate_objective_order_entry_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"objective_order": ["tier0", "tier0", "tier2"]}))

    with pytest.raises(ConfigError, match="duplicate"):
        load_config(path)


def test_unknown_objective_order_entry_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"objective_order": ["tier0", "tier1", "tier99"]}))

    with pytest.raises(ConfigError, match="tier99"):
        load_config(path)


def test_incomplete_objective_order_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"objective_order": ["tier0", "tier1"]}))

    with pytest.raises(ConfigError, match="missing"):
        load_config(path)
