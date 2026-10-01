"""Track add-ons installed through JAVBED without modifying JAVLI's instance index."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import settings


def _file() -> Path:
    return settings.ROOT / "content_installations.json"


def load() -> list[dict]:
    try:
        rows = json.loads(_file().read_text(encoding="utf-8"))
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def save(rows: list[dict]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def upsert(row: dict) -> None:
    rows = [item for item in load() if not (item.get("instance") == row.get("instance") and item.get("kind") == row.get("kind") and item.get("file_name") == row.get("file_name"))]
    rows.append(row)
    save(rows)


def remove(instance: str, kind: str, file_name: str) -> None:
    save([row for row in load() if not (row.get("instance") == instance and row.get("kind") == kind and row.get("file_name") == file_name)])


def lookup(instance: str, kind: str, file_name: str) -> dict | None:
    return next((row for row in load() if row.get("instance") == instance and row.get("kind") == kind and row.get("file_name") == file_name), None)
