from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

STORY_MODE_SEASON_1_DOWNLOAD_URL = "https://archive.org/download/minecraft-full-season-1/MINECRAFT_FULL_SEASON_1.iso"
STORY_MODE_SEASON_2_DOWNLOAD_URL = "https://archive.org/download/minecraft-story-mode-season-2-pc/Minecraft%20Story%20Mode%20Season%202.iso"

DOWNLOAD_URLS = {
    "Story Mode": STORY_MODE_SEASON_1_DOWNLOAD_URL,
    "Story Mode 2": STORY_MODE_SEASON_2_DOWNLOAD_URL,
}


def download_iso(url: str, destination: Path, progress) -> None:
    """Download to a temporary file, then replace the selected destination."""
    partial = destination.with_name(destination.name + ".part")
    try:
        request = Request(url, headers={"User-Agent": "JAVBED"})
        with urlopen(request, timeout=30) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            while chunk := response.read(256 * 1024):
                output.write(chunk)
                received += len(chunk)
                progress(received, total)
            if total and received != total:
                raise OSError(f"Incomplete download: received {received} of {total} bytes")
        partial.replace(destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
