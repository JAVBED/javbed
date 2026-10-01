"""Find existing launcher instances without altering the source installations."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .instances import get_instance, valid_name
from .jobs import Job


@dataclass(frozen=True)
class Candidate:
    launcher: str
    name: str
    path: Path
    version: str
    loader: str = "vanilla"


def _json(path: Path) -> dict:
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def default_roots(home: Path | None = None, platform: str | None = None, appdata: Path | None = None) -> list[tuple[str, Path]]:
    home = home or Path.home()
    platform = platform or sys.platform
    if platform == "win32":
        roaming = appdata or Path(os.getenv("APPDATA") or home / "AppData" / "Roaming")
        return [("Official Minecraft Launcher", roaming / ".minecraft"), ("Prism Launcher", roaming / "PrismLauncher" / "instances"), ("MultiMC", roaming / "MultiMC" / "instances"), ("Modrinth App", roaming / "ModrinthApp" / "profiles"), ("CurseForge", home / "curseforge" / "minecraft" / "Instances")]
    if platform == "darwin":
        support = home / "Library" / "Application Support"
        return [("Official Minecraft Launcher", support / "minecraft"), ("Prism Launcher", support / "PrismLauncher" / "instances"), ("MultiMC", support / "MultiMC" / "instances"), ("Modrinth App", support / "ModrinthApp" / "profiles"), ("CurseForge", home / "Documents" / "curseforge" / "minecraft" / "Instances")]
    share = home / ".local" / "share"
    return [("Official Minecraft Launcher", home / ".minecraft"), ("Prism Launcher", share / "PrismLauncher" / "instances"), ("MultiMC", share / "MultiMC" / "instances"), ("Modrinth App", share / "ModrinthApp" / "profiles"), ("CurseForge", home / "Documents" / "curseforge" / "minecraft" / "Instances")]


def inspect(path: Path, hint: str = "") -> Candidate | None:
    if not path.is_dir():
        return None
    if (path / "instance.cfg").is_file():
        cfg = {}
        try:
            for line in (path / "instance.cfg").read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1); cfg[key.strip()] = value.strip()
        except OSError:
            pass
        pack = _json(path / "mmc-pack.json")
        components = pack.get("components", [])
        version = next((str(row.get("version") or "") for row in components if row.get("uid") == "net.minecraft"), "")
        loader = next((kind for kind in ("fabric", "quilt", "neoforge", "forge") if any(kind in str(row.get("uid", "")).lower() for row in components)), "vanilla")
        return Candidate(hint or "Prism / MultiMC", cfg.get("name") or path.name, path, version, loader)
    if (path / "minecraftinstance.json").is_file():
        meta = _json(path / "minecraftinstance.json")
        name = str((meta.get("baseModLoader") or {}).get("name") or "").lower()
        loader = next((kind for kind in ("neoforge", "fabric", "quilt", "forge") if name.startswith(kind)), "vanilla")
        return Candidate("CurseForge", str(meta.get("name") or path.name), path, str(meta.get("gameVersion") or ""), loader)
    if (path / "profile.json").is_file() and ((path / "mods").is_dir() or (path / "minecraft").is_dir()):
        meta = _json(path / "profile.json")
        return Candidate("Modrinth App", str(meta.get("name") or path.name), path, str(meta.get("game_version") or meta.get("gameVersion") or ""), str(meta.get("loader") or "vanilla"))
    if (path / "versions").is_dir() and (path / "assets").is_dir():
        profiles = _json(path / "launcher_profiles.json")
        selected = str(profiles.get("selectedProfile") or "")
        chosen = (profiles.get("profiles") or {}).get(selected) or {}
        return Candidate("Official Minecraft Launcher", "Official Java", path, str(chosen.get("lastVersionId") or ""))
    if (path / "instance.json").is_file():
        meta = _json(path / "instance.json")
        return Candidate(hint or "Existing instance", str(meta.get("name") or path.name), path, str(meta.get("version") or ""), str(meta.get("loader") or "vanilla"))
    if (path / "mods").is_dir() or (path / "saves").is_dir():
        return Candidate(hint or "Existing game folder", path.name, path, "")
    return None


def discover(extra_roots: list[Path] | None = None, roots: list[tuple[str, Path]] | None = None) -> list[Candidate]:
    search = list(roots if roots is not None else default_roots())
    search.extend(("Other launcher", Path(path)) for path in (extra_roots or []))
    result = []
    seen = set()
    for label, root in search:
        if not root.is_dir():
            continue
        candidates = [root]
        if label != "Official Minecraft Launcher":
            try:
                candidates.extend(path for path in root.iterdir() if path.is_dir() and not path.is_symlink())
            except OSError:
                continue
        for path in candidates[:1001]:
            resolved = path.resolve()
            if resolved in seen:
                continue
            item = inspect(path, label)
            if item:
                seen.add(resolved)
                result.append(item)
    return result


class LauncherImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Found Existing Installations")
        self.resize(850, 560)
        self.pool = QThreadPool.globalInstance()
        self.rows = []
        root = QVBoxLayout(self)
        title = QLabel("FOUND EXISTING INSTALLATIONS")
        title.setObjectName("heroTitle")
        root.addWidget(title)
        self.status = QLabel("Scanning other launchers...")
        root.addWidget(self.status)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget(); self.list_layout = QVBoxLayout(container); self.list_layout.addStretch()
        scroll.setWidget(container); root.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        for title, action in (("SCAN OTHER FOLDER", self.add_folder), ("IMPORT SELECTED", self.accept), ("CANCEL", self.reject)):
            button = QPushButton(title); button.setObjectName("secondary"); button.clicked.connect(action); buttons.addWidget(button)
        root.addLayout(buttons)
        self.scan()

    def scan(self, extra=None):
        job = Job(lambda: discover(extra_roots=[extra] if extra else None))
        self.status.setText("Scanning existing installations...")

        def done(ok, result):
            if not ok:
                self.status.setText("Scan failed: " + str(result))
                return
            existing = {str(item.path.resolve()) for item, _, _, _ in self.rows}
            for item in result:
                if str(item.path.resolve()) in existing:
                    continue
                row = QFrame(); row.setObjectName("hero")
                layout = QHBoxLayout(row)
                choose = QCheckBox(item.launcher + " · " + item.name)
                choose.setChecked(True)
                layout.addWidget(choose, 1)
                name = QLineEdit(re.sub(r"[^A-Za-z0-9._-]+", "-", item.name).strip("-.")[:48] or "imported")
                name.setPlaceholderText("Instance name")
                layout.addWidget(name)
                version = QLineEdit(item.version)
                version.setPlaceholderText("Minecraft version (required)")
                layout.addWidget(version)
                self.list_layout.insertWidget(self.list_layout.count() - 1, row)
                self.rows.append((item, choose, name, version))
            self.status.setText(f"Found {len(self.rows)} installation(s). Imports copy game data and leave originals untouched.")

        job.signals.done.connect(done)
        self.pool.start(job)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Scan launcher folder")
        if path:
            self.scan(Path(path))

    def selected(self) -> list[tuple[Candidate, str, str]]:
        return [(item, name.text().strip(), version.text().strip()) for item, check, name, version in self.rows if check.isChecked()]

    def accept(self):
        rows = self.selected()
        if not rows:
            self.status.setText("Select an installation to import.")
            return
        names = [name for _, name, _ in rows]
        if len(set(names)) != len(names) or any(not valid_name(name) or get_instance(name) for name in names):
            self.status.setText("Choose unique instance names using letters, numbers, dots, underscores, or dashes.")
            return
        if any(not re.fullmatch(r"[A-Za-z0-9._+\-]{1,100}", version) for _, _, version in rows):
            self.status.setText("Enter a valid Minecraft version for every selected installation.")
            return
        super().accept()
