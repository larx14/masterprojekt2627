"""
Lädt die Governance-Konfiguration aus config.yaml.
"""

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = Path(__file__).with_name("config.yaml")

AUTONOMY_LEVELS = ("L1", "L2", "L3")
RISK_LEVELS = ("read", "draft", "submit", "payment")


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def get_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    Return a copy of the configuration so callers can
    modify it (e.g. in tests) without side effects.
    """

    cfg = deepcopy(_load(str(path or CONFIG_PATH)))

    level = cfg.get("default_autonomy_level")
    if level not in AUTONOMY_LEVELS:
        raise ValueError(f"Unknown default_autonomy_level '{level}'.")

    missing = [r for r in RISK_LEVELS if r not in cfg.get("thresholds", {})]
    if missing:
        raise ValueError(f"Missing thresholds for: {missing}")

    return cfg
