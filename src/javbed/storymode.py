from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

STORY_MODE_SEASON_1_DOWNLOAD_URL = "https://archive.org/download/minecraft-full-season-1/MINECRAFT_FULL_SEASON_1.iso"
STORY_MODE_SEASON_2_DOWNLOAD_URL = "https://archive.org/download/minecraft-story-mode-season-2-pc/Minecraft%20Story%20Mode%20Season%202.iso"

DOWNLOAD_URLS = {
    "Story Mode": STORY_MODE_SEASON_1_DOWNLOAD_URL,
    "Story Mode 2": STORY_MODE_SEASON_2_DOWNLOAD_URL,
}


def detect_game(settings: dict, season_index: int) -> Path | None:
    key = "story_mode_s1_path" if season_index == 0 else "story_mode_s2_path"
    saved = Path(str(settings.get(key, "")).strip())
    if saved.is_file():
        return saved
    if sys.platform != "win32":
        return None
    roots = [
        Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam" / "steamapps" / "common",
        Path(os.getenv("ProgramFiles", "C:/Program Files")),
    ]
    names = (("Minecraft Story Mode", "Minecraft - Story Mode") if season_index == 0
             else ("Minecraft Story Mode - Season Two", "Minecraft Story Mode Season Two"))
    for root in roots:
        for name in names:
            base = root / name
            if base.exists():
                for path in base.glob("**/*.exe"):
                    if "unins" not in path.name.lower() and "setup" not in path.name.lower():
                        return path
    return None


class DownloadCancelled(Exception):
    pass


def download_iso(url: str, destination: Path, progress, cancel=None) -> None:
    """Download to a resumable partial file, then replace the selected destination."""
    partial = destination.with_name(destination.name + ".part")
    received = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "JAVBED"}
    if received:
        headers["Range"] = f"bytes={received}-"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        resumed = received > 0 and getattr(response, "status", None) == 206
        if not resumed:
            received = 0
        remaining = int(response.headers.get("Content-Length") or 0)
        total = received + remaining if remaining else 0
        with partial.open("ab" if resumed else "wb") as output:
            progress(received, total)
            while chunk := response.read(256 * 1024):
                if cancel and cancel.is_set():
                    raise DownloadCancelled("Download paused. Press DOWNLOAD ISO to resume.")
                output.write(chunk)
                received += len(chunk)
                progress(received, total)
        if total and received != total:
            raise OSError(f"Incomplete download: received {received} of {total} bytes; retry to resume")
    partial.replace(destination)
