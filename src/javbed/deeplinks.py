"""Validated JAVBED URI navigation and per-user Windows protocol registration."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class Link:
    section: str
    value: str = ""


def parse(uri: str) -> Link:
    if not isinstance(uri, str) or len(uri) > 2048:
        raise ValueError("Invalid JAVBED link")
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "javbed" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ValueError("Invalid JAVBED link")
    section = parsed.netloc.lower()
    value = unquote(parsed.path.lstrip("/"))
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError("Invalid JAVBED link path")
    if section == "settings" and not value:
        return Link(section)
    patterns = {
        "java": r"[A-Za-z0-9._+\-]{1,100}",
        "instance": r"[A-Za-z0-9._-]{1,100}",
        "server": r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}",
        "modrinth": r"[A-Za-z0-9_-]{1,128}",
    }
    if section not in patterns or not re.fullmatch(patterns[section], value) or value in (".", ".."):
        raise ValueError("Unsupported JAVBED link")
    return Link(section, value)


def register_windows(executable: str) -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import winreg
    root = r"Software\Classes\javbed"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:JAVBED Launcher")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, '"' + executable.replace('"', '') + '" "%1"')
