"""Browse packs and install each one into a new JAVLI instance."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import content, settings
from .instances import get_instance, save_preferences, valid_name
from .jobs import Job


def pack_requirements(index: dict) -> tuple[str, str, str]:
    dependencies = index.get("dependencies") or {}
    minecraft = str(dependencies.get("minecraft") or "")
    for key in ("fabric-loader", "quilt-loader", "neoforge", "forge"):
        if key in dependencies:
            return minecraft, key.split("-")[0], str(dependencies[key])
    return minecraft, "vanilla", ""


def inspect_mrpack(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        index = json.loads(archive.read("modrinth.index.json"))
    if not isinstance(index, dict) or index.get("formatVersion") != 1:
        raise ValueError("Unsupported .mrpack format.")
    minecraft, loader, loader_version = pack_requirements(index)
    if not minecraft:
        raise ValueError("The modpack has no Minecraft version.")
    return {"name": str(index.get("name") or path.stem), "minecraft": minecraft, "loader": loader, "loader_version": loader_version}


class ModpackBrowser(QWidget):
    def __init__(self, run_command, parent=None):
        super().__init__(parent)
        self.run_command = run_command
        self.pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)
        self.job = None
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        title = QLabel("MODPACKS")
        title.setObjectName("heroTitle")
        root.addWidget(title)
        controls = QHBoxLayout()
        self.provider = QComboBox()
        self.provider.addItems(["Modrinth", "CurseForge"])
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search modpacks")
        self.query.returnPressed.connect(self.search)
        controls.addWidget(self.provider)
        controls.addWidget(self.query, 1)
        search = QPushButton("SEARCH")
        search.setObjectName("secondary")
        search.clicked.connect(self.search)
        controls.addWidget(search)
        local = QPushButton("OPEN .MRPACK")
        local.setObjectName("secondary")
        local.clicked.connect(self.open_mrpack)
        controls.addWidget(local)
        root.addLayout(controls)
        self.status = QLabel("Search a provider or open a local .mrpack file.")
        self.status.setObjectName("small")
        root.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_widget)
        root.addWidget(scroll, 1)

    def clear(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def search(self):
        if self.job:
            return
        query = self.query.text().strip()
        if not query:
            self.status.setText("Enter a search term.")
            return
        provider = self.provider.currentText().lower()
        key = str(settings.load().get("curseforge_api_key", ""))
        job = Job(lambda: content.search(provider, "modpack", query, api_key=key))
        self.job = job
        self.status.setText("Searching " + provider + "...")

        def done(ok, result):
            self.job = None
            if not ok:
                self.status.setText(str(result))
                return
            self.clear()
            self.status.setText(f"{len(result)} packs found" if result else "No packs found.")
            for hit in result:
                self.card(hit)

        job.signals.done.connect(done)
        self.pool.start(job)

    def card(self, hit):
        frame = QFrame()
        frame.setObjectName("hero")
        row = QHBoxLayout(frame)
        icon = QLabel()
        icon.setFixedSize(56, 56)
        url = str(hit.get("icon") or "")
        if url.startswith("https://"):
            reply = self.network.get(QNetworkRequest(QUrl(url)))

            def loaded():
                data = bytes(reply.readAll())
                pixmap = QPixmap()
                if len(data) < 512 * 1024 and pixmap.loadFromData(data):
                    try:
                        icon.setPixmap(pixmap.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    except RuntimeError:
                        pass
                reply.deleteLater()

            reply.finished.connect(loaded)
        row.addWidget(icon)
        copy = QVBoxLayout()
        name = QLabel(hit["name"])
        name.setObjectName("game")
        copy.addWidget(name)
        detail = QLabel(f'{hit["author"]} · {hit["downloads"]:,} downloads\n{hit["description"]}')
        detail.setWordWrap(True)
        copy.addWidget(detail)
        row.addLayout(copy, 1)
        install = QPushButton("INSTALL")
        install.setObjectName("play")
        install.clicked.connect(lambda: self.install(hit))
        row.addWidget(install)
        self.list_layout.insertWidget(self.list_layout.count() - 1, frame)

    def _new_name(self, suggestion):
        default = re.sub(r"[^A-Za-z0-9._-]+", "-", suggestion).strip("-.")[:48] or "modpack"
        name, ok = QInputDialog.getText(self, "New Isolated Instance", "Instance name", text=default)
        if not ok:
            return None
        name = name.strip()
        if not valid_name(name) or get_instance(name):
            self.status.setText("Choose a unique instance name using letters, numbers, dots, underscores, or dashes.")
            return None
        return name

    def install(self, hit):
        if self.job:
            return
        versions = [value for value in hit.get("versions", []) if value]
        if versions:
            minecraft, ok = QInputDialog.getItem(self, "Minecraft Version", "Install pack for", versions, len(versions) - 1, False)
        else:
            minecraft, ok = QInputDialog.getText(self, "Minecraft Version", "Minecraft version")
        if not ok or not minecraft.strip():
            return
        name = self._new_name(hit["slug"] or hit["name"])
        if not name:
            return
        key = str(settings.load().get("curseforge_api_key", ""))
        job = Job(lambda: content.newest_compatible(hit["provider"], "modpack", hit["id"], minecraft.strip(), api_key=key))
        self.job = job
        self.status.setText("Checking compatible pack version...")

        def checked(ok, version):
            self.job = None
            if not ok or not version:
                self.status.setText(str(version) if not ok else "No compatible pack version found.")
                return
            if hit["provider"] == "modrinth":
                dependencies = version["raw"].get("dependencies") or {}
                mc, loader, loader_version = pack_requirements({"dependencies": dependencies})
                if mc and mc != minecraft.strip():
                    self.status.setText("Pack version metadata conflicts with the selected Minecraft version.")
                    return
                self._create_and_install(name, minecraft.strip(), loader, loader_version, hit, version)
            else:
                inspect_job = Job(lambda: content.curseforge_pack_requirements(hit["id"], version, key))
                self.job = inspect_job
                self.status.setText("Inspecting CurseForge pack requirements...")

                def inspected(valid, details):
                    self.job = None
                    if not valid:
                        self.status.setText("Cannot install pack: " + str(details))
                        return
                    mc, loader, loader_version = details
                    if mc != minecraft.strip():
                        self.status.setText("Pack manifest Minecraft version does not match the selected version.")
                        return
                    self._create_and_install(name, mc, loader, loader_version, hit, version)

                inspect_job.signals.done.connect(inspected)
                self.pool.start(inspect_job)

        job.signals.done.connect(checked)
        self.pool.start(job)

    def _create_and_install(self, name, minecraft, loader, loader_version, hit, version, local_file=None):
        command = ["instance", "create", name, "release", minecraft]
        if loader != "vanilla":
            command += ["--loader", loader]
            if loader_version:
                command += ["--loader-version", loader_version]
        self.status.setText("Creating isolated instance " + name + "...")

        def created(ok, output):
            if not ok:
                self.status.setText("Instance creation failed: " + output.strip()[-180:])
                return
            project = str(local_file) if local_file else hit["id"]
            install_command = ["modpack", "install", project, "--instance", name]
            if hit["provider"] == "curseforge":
                install_command += ["--provider", "curseforge", "--file-id", version["id"]]
            elif not local_file:
                install_command += ["--version-id", version["id"]]
            self.status.setText("Installing pack into " + name + "...")

            def installed(success, details):
                if success:
                    save_preferences(name, {"modpack": {"provider": hit["provider"], "project": hit.get("id", ""), "version_id": version.get("id", ""), "name": hit["name"]}})
                    self.status.setText("Installed " + hit["name"] + " as " + name)
                else:
                    self.status.setText("Pack install failed for " + name + ": " + details.strip()[-180:])

            self.run_command(install_command, installed)

        self.run_command(command, created)

    def open_mrpack(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Modrinth Pack", "", "Modrinth packs (*.mrpack)")
        if not path or self.job:
            return
        source = Path(path)
        job = Job(lambda: inspect_mrpack(source))
        self.job = job
        self.status.setText("Inspecting local modpack...")

        def done(ok, info):
            self.job = None
            if not ok:
                self.status.setText("Cannot read pack: " + str(info))
                return
            name = self._new_name(info["name"])
            if not name:
                return
            hit = {"provider": "modrinth", "id": "", "name": info["name"]}
            self._create_and_install(name, info["minecraft"], info["loader"], info["loader_version"], hit, {"id": ""}, source)

        job.signals.done.connect(done)
        self.pool.start(job)
