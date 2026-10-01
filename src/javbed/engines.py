from __future__ import annotations
import json
import hashlib
import os
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "JAVBED"
ENGINE_ROOT = ROOT / "engines"
API = "https://api.github.com/repos/JAVBED/{repo}/releases/latest"

def _platform_tokens():
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_tokens = {"windows": ("windows", "win"), "linux": ("linux",), "darwin": ("macos", "osx", "darwin", "mac")}.get(system, (system,))
    arch = ("arm64", "aarch64") if machine in ("arm64", "aarch64") else ("x64", "x86_64", "amd64")
    return os_tokens, arch

def _safe_member(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if not path.parts:
        return
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError(f"Unsafe archive path: {name}")


def _extract_archive(package, destination):
    name = package.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(package) as archive:
            for item in archive.infolist():
                _safe_member(item.filename)
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError(f"Archive link is not allowed: {item.filename}")
            archive.extractall(destination)
    elif name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(package, "r:gz") as archive:
            for item in archive.getmembers():
                _safe_member(item.name)
                if not (item.isfile() or item.isdir()):
                    raise ValueError(f"Archive link or special file is not allowed: {item.name}")
            archive.extractall(destination)
    else:
        raise ValueError(f"Unsupported archive: {package.name}")

@dataclass(frozen=True)
class Engine:
    label: str
    project: str
    binary: str

    @property
    def directory(self):
        return ENGINE_ROOT / self.project

    @property
    def executable(self):
        return self.directory / (self.binary + ".exe" if platform.system() == "Windows" else self.binary)

    def locate(self):
        override = os.getenv("JAVBED_" + self.label.upper().replace(" ", "_"))
        if override and Path(override).is_file():
            return Path(override)
        on_path = shutil.which(self.binary)
        if not on_path and platform.system() == "Windows":
            on_path = shutil.which(self.binary + ".exe")
        if on_path and Path(on_path).is_file():
            return Path(on_path)
        return self.executable if self.executable.is_file() else None

    def command(self, *args):
        exe = self.locate()
        if not exe:
            return None, f"{self.label} engine is not configured. Add it to PATH, install it, or choose its path in Settings."
        if platform.system() == "Windows" and exe.suffix.lower() in (".cmd", ".bat"):
            return ["cmd.exe", "/d", "/c", str(exe), *args], None
        return [str(exe), *args], None

    def install_latest(self, progress=None):
        self.directory.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(API.format(repo=self.project), headers={"Accept": "application/vnd.github+json", "User-Agent": "JAVBED"})
        with urllib.request.urlopen(req, timeout=30) as response:
            release = json.load(response)
        assets = release.get("assets", [])
        os_tokens, arch = _platform_tokens()
        candidates = []
        for asset in assets:
            name = asset["name"].lower()
            if any(x in name for x in os_tokens) and any(x in name for x in arch) and name.endswith((".zip", ".tar.gz", ".tgz", ".exe")):
                candidates.append(asset)
        if not candidates and platform.system() == "Windows":
            candidates = [a for a in assets if a["name"].lower().endswith(".exe")]
        if not candidates:
            raise RuntimeError(f"No compatible {self.project} release asset for {platform.system()} {platform.machine()}.")
        asset = candidates[0]
        url = asset["browser_download_url"]
        name = asset["name"]
        if progress:
            progress(f"Downloading {name}...")
        with tempfile.TemporaryDirectory() as td:
            temporary = Path(td)
            package = temporary / Path(name).name
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=60) as response, package.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            expected_digest = asset.get("digest", "")
            if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", expected_digest):
                raise RuntimeError(f"Release asset {name} has no SHA-256 digest.")
            if digest.hexdigest() != expected_digest[7:].lower():
                raise RuntimeError(f"Checksum mismatch for {name}.")
            staging = temporary / "staging"
            staging.mkdir()
            if name.lower().endswith((".zip", ".tar.gz", ".tgz")):
                _extract_archive(package, staging)
            else:
                shutil.copy2(package, staging / self.executable.name)
            expected = (self.binary.lower(), self.binary.lower() + ".exe")
            found = next((p for p in staging.rglob("*") if p.is_file() and p.name.lower() in expected), None)
            if not found:
                raise RuntimeError(f"Downloaded release but could not find {self.binary} executable.")
            for source in staging.rglob("*"):
                target = self.directory / source.relative_to(staging)
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif source != found:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            replacement = self.executable.with_name(self.executable.name + ".new")
            shutil.copy2(found, replacement)
            if platform.system() != "Windows":
                replacement.chmod(replacement.stat().st_mode | stat.S_IEXEC)
            os.replace(replacement, self.executable)
        (self.directory / "release.json").write_text(json.dumps({"tag": release.get("tag_name"), "asset": name}, indent=2), encoding="utf-8")
        return release.get("tag_name") or "latest"

ENGINES = {
    "Java": Engine("Java", "javli", "javli"),
    "Bedrock": Engine("Bedrock", "bedli", "bedli"),
    "EDU": Engine("EDU", "eduli", "eduli"),
    "LCE": Engine("LCE", "legli", "legli"),
    "Servers": Engine("Servers", "servli", "servli"),
}
