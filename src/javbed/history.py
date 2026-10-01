"""Persistent launch history shared by the dashboard and game pages."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import settings

_lock = threading.RLock()


def _file() -> Path:
    return settings.ROOT / "history.json"


def _read() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == 1:
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "sessions": []}


def sessions(limit: int | None = None) -> list[dict]:
    with _lock:
        rows = list(_read()["sessions"])
    rows.sort(key=lambda row: row.get("started", ""), reverse=True)
    return rows[:limit] if limit is not None else rows


def summary() -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for row in sessions():
        key = (row.get("game", ""), row.get("instance", ""))
        item = grouped.setdefault(key, {"game": key[0], "instance": key[1], "version": row.get("version", ""), "channel": row.get("channel", ""), "loader": row.get("loader", ""), "last_played": row.get("started", ""), "play_count": 0, "total_seconds": 0})
        item["play_count"] += 1
        item["total_seconds"] += int(row.get("duration_seconds", 0))
    return list(grouped.values())


def record(game: str, started: datetime, ended: datetime, *, instance: str = "", version: str = "", channel: str = "", loader: str = "") -> bool:
    """Record a confirmed session; startup failures under ten seconds are ignored."""
    duration = max(0, int((ended - started).total_seconds()))
    if duration < 10:
        return False
    row = {"game": game, "instance": instance, "version": version, "channel": channel, "loader": loader, "started": started.astimezone(timezone.utc).isoformat(), "ended": ended.astimezone(timezone.utc).isoformat(), "duration_seconds": duration}
    with _lock:
        data = _read()
        data["sessions"].append(row)
        path = _file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    return True


def now() -> datetime:
    return datetime.now(timezone.utc)


def watch_process(process, game: str, *, instance: str = "", version: str = "", channel: str = "", loader: str = "") -> None:
    started = now()

    def wait():
        process.wait()
        record(game, started, now(), instance=instance, version=version, channel=channel, loader=loader)

    threading.Thread(target=wait, daemon=True, name="javbed-playtime").start()


def watch_pid(pid: int, game: str, *, instance: str = "", version: str = "", channel: str = "", loader: str = "") -> bool:
    """Monitor a game detached by a CLI without blocking Qt."""
    if pid <= 0:
        return False
    started = now()
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = (ctypes.c_uint, ctypes.c_int, ctypes.c_uint)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, 0, pid)  # SYNCHRONIZE
        if not handle:
            return False

        def wait():
            try:
                kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0xFFFFFFFF)
                record(game, started, now(), instance=instance, version=version, channel=channel, loader=loader)
            finally:
                kernel.CloseHandle(ctypes.c_void_p(handle))
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False

        def wait():
            while True:
                time.sleep(2)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
            record(game, started, now(), instance=instance, version=version, channel=channel, loader=loader)

    threading.Thread(target=wait, daemon=True, name="javbed-playtime").start()
    return True
