"""Read JAVLI's structured instance index without touching its authentication data."""

from __future__ import annotations

import json
from pathlib import Path

JAVLI_ROOT = Path.home() / ".mcli"


def list_instances() -> list[dict]:
    try:
        data = json.loads((JAVLI_ROOT / "instances.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return [value for value in data.values() if isinstance(value, dict) and value.get("name")]


def get_instance(name: str) -> dict | None:
    return next((item for item in list_instances() if item["name"] == name), None)
