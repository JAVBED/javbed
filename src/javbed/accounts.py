"""Read only the public profile metadata from JAVLI's account store."""

from __future__ import annotations

import json
import re
import time
from urllib.request import Request, urlopen
from pathlib import Path

from . import settings

JAVLI_ROOT = Path.home() / ".mcli"


def accounts() -> tuple[str | None, list[dict]]:
    path = JAVLI_ROOT / "accounts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        try:
            legacy = json.loads((JAVLI_ROOT / "account.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            legacy = {}
        profile = legacy.get("profile", {}) if isinstance(legacy, dict) else {}
        if not isinstance(profile, dict) or not profile.get("name"):
            return None, []
        alias = str(profile["name"])
        return alias, [{"alias": alias, "username": alias, "uuid": str(profile.get("id", ""))}]
    active = data.get("active")
    rows = []
    for alias, value in data["accounts"].items():
        profile = value.get("profile", {}) if isinstance(value, dict) else {}
        if isinstance(profile, dict):
            rows.append({"alias": str(alias), "username": str(profile.get("name") or alias), "uuid": str(profile.get("id") or "")})
    return str(active) if active else None, rows


def active_account() -> dict | None:
    alias, rows = accounts()
    return next((row for row in rows if row["alias"] == alias), None)


def avatar_path(account: dict | None) -> Path | None:
    if not account:
        return None
    uuid = account.get("uuid", "").replace("-", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", uuid):
        return None
    path = settings.ROOT / "cache" / "avatars" / (uuid.lower() + ".png")
    if path.is_file() and time.time() - path.stat().st_mtime < 86400:
        return path
    try:
        request = Request(f"https://crafatar.imc.moe/avatars/{uuid}?size=64&overlay", headers={"User-Agent": "JAVBED"})
        with urlopen(request, timeout=5) as response:
            data = response.read(256 * 1024 + 1)
        if len(data) > 256 * 1024 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return path if path.is_file() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path
    except (OSError, ValueError):
        return path if path.is_file() else None
