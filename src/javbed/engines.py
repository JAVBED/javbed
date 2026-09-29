from __future__ import annotations
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "JAVBED"
ENGINE_ROOT = ROOT / "engines"
API = "https://api.github.com/repos/JAVBED/{repo}/releases/latest"

def _platform_tokens():
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_tokens = {"windows": ("windows", "win"), "linux": ("linux",), "darwin": ("macos", "osx", "darwin", "mac")}.get(system, (system,))
    arch = ("arm64", "aarch64") if machine in ("arm64", "aarch64") else ("x64", "x86_64", "amd64")
    return os_tokens, arch

def _windows_candidates(binary):
    names = (binary, binary + ".exe", binary + ".cmd", binary + ".bat")
    for name in names:
        found = shutil.which(name)
        if found:
            yield Path(found)
    roots = [
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs",
        Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps",
        Path(os.getenv("APPDATA", "")) / "Python",
        Path.home() / ".local" / "bin",
    ]
    for root in roots:
        if not root.exists():
            continue
        patterns = [binary + ".exe", binary + ".cmd", binary + ".bat"]
        for pattern in patterns:
            try:
                for path in root.rglob(pattern):
                    if path.is_file():
                        yield path
            except OSError:
                pass

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
        if override and Path(override).exists():
            return Path(override)
        if platform.system() == "Windows":
            found = next(_windows_candidates(self.binary), None)
            if found:
                return found
        else:
            found = shutil.which(self.binary)
            if found:
                return Path(found)
        return self.executable if self.executable.exists() else None

    def command(self, *args):
        exe = self.locate()
        if not exe:
            return None, f"{self.label} engine is not installed or visible to JAVBED."
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
            package = Path(td) / name
            urllib.request.urlretrieve(url, package)
            if name.lower().endswith(".zip"):
                with zipfile.ZipFile(package) as archive:
                    archive.extractall(self.directory)
            elif name.lower().endswith((".tar.gz", ".tgz")):
                with tarfile.open(package, "r:gz") as archive:
                    archive.extractall(self.directory)
            else:
                shutil.copy2(package, self.executable)
        if not self.executable.exists():
            expected = (self.binary.lower(), self.binary.lower() + ".exe")
            found = next((p for p in self.directory.rglob("*") if p.is_file() and p.name.lower() in expected), None)
            if found and found != self.executable:
                shutil.copy2(found, self.executable)
        if not self.executable.exists():
            raise RuntimeError(f"Downloaded release but could not find {self.binary} executable.")
        if platform.system() != "Windows":
            self.executable.chmod(self.executable.stat().st_mode | stat.S_IEXEC)
        (self.directory / "release.json").write_text(json.dumps({"tag": release.get("tag_name"), "asset": name}, indent=2), encoding="utf-8")
        return release.get("tag_name") or "latest"

ENGINES = {
    "Java": Engine("Java", "javli", "javli"),
    "Bedrock": Engine("Bedrock", "bedli", "bedli"),
    "EDU": Engine("EDU", "eduli", "eduli"),
    "LCE": Engine("LCE", "legli", "legli"),
    "Servers": Engine("Servers", "servli", "servli"),
}
