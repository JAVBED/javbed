"""Read-only launcher health checks, designed to run in a worker thread."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .accounts import active_account
from .artwork import FILES, artwork_dir
from .engines import ENGINES
from .instances import JAVLI_ROOT
from .settings import ROOT, load


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str
    repair_engine: str = ""


def _reachable(url: str, headers=None) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "JAVBED", **(headers or {})}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read(1)
            return 200 <= response.status < 400
    except (OSError, urllib.error.HTTPError):
        return False


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def scan() -> list[Check]:
    data = load()
    result = []
    network = _reachable("https://www.minecraft.net/")
    result.append(Check("Network", "healthy" if network else "failed", "Minecraft.net reachable" if network else "Could not reach Minecraft.net"))
    github = _reachable("https://api.github.com/repos/JAVBED/javbed")
    result.append(Check("GitHub", "healthy" if github else "warning", "GitHub API reachable" if github else "GitHub API unavailable"))
    account = active_account()
    result.append(Check("Microsoft account", "healthy" if account else "warning", account["username"] if account else "No active JAVLI account; sign in from Java → Accounts"))
    if sys.platform == "win32":
        try:
            process = subprocess.run(["powershell", "-NoProfile", "-Command", "@(Get-AppxPackage Microsoft.GamingServices).Count"], capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            lines = process.stdout.strip().splitlines()
            installed = process.returncode == 0 and bool(lines) and lines[-1].isdigit() and int(lines[-1]) > 0
        except (OSError, subprocess.TimeoutExpired):
            installed = False
        result.append(Check("Gaming Services", "healthy" if installed else "warning", "Installed" if installed else "Not detected; Bedrock may need Microsoft Gaming Services"))
    for label, engine in ENGINES.items():
        found = engine.locate()
        result.append(Check(label + " engine", "healthy" if found else "warning", str(found) if found else "Engine is not installed or on PATH", "" if found else label))
    for major in (8, 17, 21, 25):
        binary = "java.exe" if sys.platform == "win32" else "java"
        path = JAVLI_ROOT / "runtimes" / f"java-{major}" / "bin" / binary
        result.append(Check("Java " + str(major), "healthy" if path.is_file() else "warning", str(path) if path.is_file() else "JAVLI can install this runtime when needed"))
    for key, label in (("minecraft_directory", "Minecraft folder"), ("java_runtime", "Java runtime path"), ("servli_home", "SERVLI home"), ("bedrock_worlds_path", "Bedrock worlds path"), ("edu_worlds_path", "Education worlds path")):
        value = str(data.get(key) or "").strip()
        if value:
            exists = Path(value).exists()
            result.append(Check(label, "healthy" if exists else "warning", value if exists else "Configured path does not exist: " + value))
    art = artwork_dir()
    missing = [file for file in set(FILES.values()) if not (art / file).is_file()]
    result.append(Check("Artwork", "healthy" if not missing else "warning", str(art) if not missing else "Missing: " + ", ".join(missing)))
    for folder, label in ((ROOT, "JAVBED data"), (ROOT / "cache", "JAVBED cache")):
        writable = _writable(folder)
        result.append(Check(label, "healthy" if writable else "failed", str(folder) if writable else "Directory is not writable: " + str(folder)))
    api_key = str(data.get("curseforge_api_key") or "").strip()
    if api_key:
        available = _reachable("https://api.curseforge.com/v1/games/432", {"x-api-key": api_key})
        result.append(Check("CurseForge API", "healthy" if available else "warning", "API key works" if available else "API unavailable or key rejected"))
    return result
