"""Read JAVLI's structured instance index without touching its authentication data."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import history, settings

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


def valid_name(name: str) -> bool:
    return name not in (".", "..") and bool(re.fullmatch(r"[A-Za-z0-9._-]+", name))


def _preferences_file() -> Path:
    return settings.ROOT / "instance_preferences.json"


def preferences(name: str) -> dict:
    try:
        data = json.loads(_preferences_file().read_text(encoding="utf-8"))
        value = data.get(name, {}) if isinstance(data, dict) else {}
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(name: str, values: dict) -> None:
    if not valid_name(name):
        raise ValueError("Invalid instance name")
    path = _preferences_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[name] = {**(data.get(name, {}) if isinstance(data.get(name), dict) else {}), **values}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def remove_preferences(name: str) -> None:
    path = _preferences_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or name not in data:
        return
    data.pop(name)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def save_icon(name: str, source: Path) -> Path:
    if not valid_name(name) or source.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("Choose a PNG, JPEG, or WebP image")
    path = settings.ROOT / "instance_icons" / (name + source.suffix.lower())
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, path)
    save_preferences(name, {"icon": str(path)})
    return path


def snapshot() -> list[dict]:
    played = {item["instance"]: item for item in history.summary() if item["game"] == "Java" and item["instance"]}
    rows = []
    for item in list_instances():
        name = str(item["name"])
        path = Path(str(item.get("path") or JAVLI_ROOT / "instances" / name))
        mods = path / "minecraft" / "mods"
        count = sum(1 for file in mods.iterdir() if file.suffix.lower() == ".jar") if mods.is_dir() else 0
        rows.append({**item, "mod_count": count, "history": played.get(name, {}), "preferences": preferences(name)})
    return sorted(rows, key=lambda item: item["name"].lower())


def launch_environment(name: str = "") -> dict[str, str]:
    data = settings.load()
    pref = preferences(name) if name else {}
    result = {
        "MCLI_MEMORY_MB": str(pref.get("memory_mb", data.get("java_memory_mb", 4096))),
        "MCLI_RESOLUTION_WIDTH": str(pref.get("width", data.get("resolution_width", 1280))),
        "MCLI_RESOLUTION_HEIGHT": str(pref.get("height", data.get("resolution_height", 720))),
    }
    major = pref.get("java_major")
    runtime = str(managed_runtime_path(int(major)) if major else pref.get("java_runtime") or data.get("java_runtime") or "")
    if runtime and Path(runtime).is_file():
        result["MCLI_JAVA"] = runtime
    return result


def managed_runtime_path(major: int) -> Path:
    binary = "java.exe" if sys.platform == "win32" else "java"
    return JAVLI_ROOT / "runtimes" / f"java-{major}" / "bin" / binary
