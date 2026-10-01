"""Stage the Windows MSI payload from verified JAVBED engine releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


ENGINES = ("javli", "bedli", "eduli", "legli", "servli")
API = "https://api.github.com/repos/JAVBED/{name}/releases/latest"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "JAVBED-installer-build"}


def release_for(name: str) -> dict:
    request = urllib.request.Request(API.format(name=name), headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def choose_asset(name: str, release: dict) -> dict:
    assets = release.get("assets") or []
    archives = [asset for asset in assets if asset["name"].lower().endswith(".zip")
                and ("windows-x64" in asset["name"].lower() or "win-x64" in asset["name"].lower())]
    executables = [asset for asset in assets if asset["name"].lower() == name + ".exe"]
    candidates = archives or executables
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one Windows x64 asset for {name}; found {len(candidates)}")
    asset = candidates[0]
    digest = str(asset.get("digest") or "")
    if len(digest) != 71 or not digest.startswith("sha256:") or any(c not in "0123456789abcdefABCDEF" for c in digest[7:]):
        raise RuntimeError(f"{name} release asset has no valid SHA-256 digest")
    return asset


def download_verified(asset: dict, destination: Path) -> None:
    request = urllib.request.Request(asset["browser_download_url"], headers=HEADERS)
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != asset["digest"][7:].lower():
        raise RuntimeError(f"Checksum mismatch for {asset['name']}")
    if asset.get("size") and destination.stat().st_size != asset["size"]:
        raise RuntimeError(f"Size mismatch for {asset['name']}")


def extract_engine(package: Path, name: str, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        extracted = Path(temporary) / "extracted"
        extracted.mkdir()
        if package.suffix.lower() == ".exe":
            shutil.copy2(package, extracted / (name + ".exe"))
        else:
            with zipfile.ZipFile(package) as archive:
                for entry in archive.infolist():
                    part = PurePosixPath(entry.filename.replace("\\", "/"))
                    if not part.parts or part.is_absolute() or ".." in part.parts or ":" in part.parts[0]:
                        raise RuntimeError(f"Unsafe archive path: {entry.filename}")
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        raise RuntimeError(f"Archive link is not allowed: {entry.filename}")
                archive.extractall(extracted)
        matches = [item for item in extracted.rglob("*") if item.is_file() and item.name.lower() == name + ".exe"]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {name}.exe in {package.name}; found {len(matches)}")
        # Preserve files beside the executable, including PyInstaller runtime folders.
        shutil.copytree(matches[0].parent, destination)
        if not (destination / (name + ".exe")).is_file():
            raise RuntimeError(f"Failed to stage {name}.exe")


def stage_payload(app_dir: Path, destination: Path) -> dict:
    if not (app_dir / "JAVBED.exe").is_file():
        raise RuntimeError("PyInstaller JAVBED.exe is missing")
    if not any((app_dir / relative).is_file() for relative in ("Javbed.StoreHelper.exe", "_internal/Javbed.StoreHelper.exe")):
        raise RuntimeError("Windows Store helper is missing from the JAVBED build")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(app_dir, destination / "JAVBED")
    versions = {}
    with tempfile.TemporaryDirectory() as temporary:
        download_dir = Path(temporary)
        for name in ENGINES:
            release = release_for(name)
            asset = choose_asset(name, release)
            print(f"Staging {name} {release.get('tag_name', 'latest')} from {asset['name']}", flush=True)
            package = download_dir / asset["name"]
            download_verified(asset, package)
            extract_engine(package, name, destination / "engines" / name)
            versions[name] = {"tag": release.get("tag_name"), "asset": asset["name"], "sha256": asset["digest"][7:]}
            package.unlink()
    (destination / "engine-versions.json").write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    stage_payload(args.app_dir, args.output)


if __name__ == "__main__":
    main()
