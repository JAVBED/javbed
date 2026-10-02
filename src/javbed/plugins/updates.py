"""Explicit, user-driven GitHub release checks for plugin packages."""

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .manifest import PluginManifest, compare
from .packages import MAX_ARCHIVE


@dataclass(frozen=True)
class PluginUpdate:
    version: str
    url: str
    asset_name: str


def check(manifest: PluginManifest) -> PluginUpdate | None:
    if not manifest.update_repo:
        return None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{manifest.update_repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "JAVBED"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        release = json.load(response)
    version = str(release.get("tag_name") or "").removeprefix("v")
    if compare(version, manifest.version) <= 0:
        return None
    assets = [asset for asset in release.get("assets", []) if str(asset.get("name", "")).lower().endswith(".javbedplugin")]
    asset = next((item for item in assets if manifest.id in item["name"]), assets[0] if assets else None)
    if not asset or not str(asset.get("browser_download_url", "")).startswith("https://"):
        raise ValueError("Release has no .javbedplugin package")
    return PluginUpdate(version, asset["browser_download_url"], asset["name"])


def download(update: PluginUpdate, destination: Path):
    request = urllib.request.Request(update.url, headers={"User-Agent": "JAVBED"})
    with urllib.request.urlopen(request, timeout=30) as response, Path(destination).open("wb") as output:
        total = 0
        while chunk := response.read(256 * 1024):
            total += len(chunk)
            if total > MAX_ARCHIVE:
                raise ValueError("Plugin update package is too large")
            output.write(chunk)
