"""Reversible, journaled temporary mod disabling for Java instances."""

from __future__ import annotations

import json
from pathlib import Path

from . import settings
from .instances import get_instance, valid_name


def _journal(name: str) -> Path:
    if not valid_name(name):
        raise ValueError("Invalid instance name")
    return settings.ROOT / "safe_mode" / (name + ".json")


def prepare(name: str) -> int:
    item = get_instance(name)
    if not item:
        raise ValueError("Instance not found")
    mods = Path(str(item["path"])) / "minecraft" / "mods"
    journal = _journal(name)
    if journal.exists():
        raise ValueError("Safe Mode is already active. Restore its mods first.")
    mods.mkdir(parents=True, exist_ok=True)
    files = [path.name for path in mods.iterdir() if path.is_file() and path.suffix.lower() == ".jar"]
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("x", encoding="utf-8") as output:
        json.dump({"mods": str(mods.resolve()), "files": files}, output)
    moved = []
    try:
        for filename in files:
            source = mods / filename
            target = mods / (filename + ".javbed-disabled")
            if target.exists():
                raise FileExistsError(target)
            source.rename(target)
            moved.append(filename)
    except Exception:
        for filename in moved:
            (mods / (filename + ".javbed-disabled")).rename(mods / filename)
        journal.unlink(missing_ok=True)
        raise
    return len(files)


def set_pid(name: str, pid: int) -> None:
    journal = _journal(name)
    data = json.loads(journal.read_text(encoding="utf-8"))
    data["pid"] = int(pid)
    temporary = journal.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(journal)


def pending() -> list[tuple[str, int]]:
    folder = settings.ROOT / "safe_mode"
    result = []
    if folder.is_dir():
        for journal in folder.glob("*.json"):
            if valid_name(journal.stem):
                try:
                    data = json.loads(journal.read_text(encoding="utf-8"))
                    result.append((journal.stem, int(data.get("pid") or 0)))
                except (OSError, ValueError, TypeError):
                    pass
    return result


def restore(name: str) -> int:
    journal = _journal(name)
    if not journal.is_file():
        return 0
    data = json.loads(journal.read_text(encoding="utf-8"))
    item = get_instance(name)
    if not item:
        raise ValueError("Instance no longer exists")
    mods = Path(str(item["path"])) / "minecraft" / "mods"
    if mods.resolve() != Path(data["mods"]).resolve():
        raise ValueError("Instance mods path changed; manual recovery is needed")
    restored = 0
    for filename in data["files"]:
        if Path(filename).name != filename or not filename.lower().endswith(".jar"):
            raise ValueError("Invalid Safe Mode journal")
        disabled = mods / (filename + ".javbed-disabled")
        original = mods / filename
        if disabled.exists():
            if original.exists():
                raise FileExistsError("Original mod filename now exists: " + filename)
            disabled.rename(original)
            restored += 1
    journal.unlink()
    return restored
