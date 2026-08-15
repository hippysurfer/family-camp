"""Engine configuration: objective tier order and severity weights (NFR-4).

Loaded from a JSON file so organisers can retune priorities year to year
without code changes. Unknown keys are rejected rather than silently
ignored, so a typo in a config file surfaces immediately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from family_camp2.constraints.base import ConstraintInstance
from family_camp2.validation.class2 import Tier0Weights

__all__ = ["EngineConfig", "ConfigError", "load_config"]

VALID_TIERS = frozenset({"tier0", "tier1", "tier2"})
_TIER0_WEIGHT_FIELDS = frozenset(
    {"custom_constraint", "missing_priority", "family_safety", "family_split", "under_minimum", "compulsory"}
)
_TOP_LEVEL_FIELDS = frozenset({"tier0_weights", "objective_order", "compulsory_activities"})


class ConfigError(ValueError):
    """Raised when a config file contains an unknown or invalid setting."""


@dataclass(frozen=True)
class EngineConfig:
    tier0_weights: Tier0Weights = field(default_factory=Tier0Weights)
    # Content is fixed (one entry per tier); only the *order* is adjustable (FR-20-22).
    objective_order: tuple[str, ...] = ("tier0", "tier1", "tier2")
    compulsory_activities: tuple[str, ...] = ()
    # Per-camper/family custom constraints (REQUIREMENTS.md §3.5/§4.10) -
    # populated from the --data/--legacy-cache source, not from this JSON
    # config file (see load_config below): unlike the other fields here,
    # constraints are camp-specific data tied to real campers in a given
    # year, not a solver-tuning knob.
    constraints: tuple[ConstraintInstance, ...] = ()


def _parse_tier0_weights(data: dict) -> Tier0Weights:
    unknown = set(data) - _TIER0_WEIGHT_FIELDS
    if unknown:
        raise ConfigError(f"Unknown tier0_weights key(s): {sorted(unknown)}")
    return Tier0Weights(**data)


def _parse_objective_order(order: list) -> tuple[str, ...]:
    order_t = tuple(order)
    unknown = set(order_t) - VALID_TIERS
    if unknown:
        raise ConfigError(f"Unknown objective_order entry/entries: {sorted(unknown)}")
    if len(set(order_t)) != len(order_t):
        raise ConfigError(f"objective_order contains duplicate entries: {order_t}")
    missing = VALID_TIERS - set(order_t)
    if missing:
        raise ConfigError(f"objective_order is missing entries: {sorted(missing)}")
    return order_t


def load_config(path: Path | str | None = None) -> EngineConfig:
    if path is None:
        return EngineConfig()

    data = json.loads(Path(path).read_text())
    unknown = set(data) - _TOP_LEVEL_FIELDS
    if unknown:
        raise ConfigError(f"Unknown config key(s): {sorted(unknown)}")

    kwargs = {}
    if "tier0_weights" in data:
        kwargs["tier0_weights"] = _parse_tier0_weights(data["tier0_weights"])
    if "objective_order" in data:
        kwargs["objective_order"] = _parse_objective_order(data["objective_order"])
    if "compulsory_activities" in data:
        kwargs["compulsory_activities"] = tuple(data["compulsory_activities"])

    return EngineConfig(**kwargs)
