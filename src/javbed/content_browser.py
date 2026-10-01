"""Graphical browsing and installed-content management for Java instances."""

from __future__ import annotations

import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import content, content_registry, settings
from .instances import list_instances
from .jobs import Job

TITLES = {"mod": "MODS", "resourcepack": "RESOURCE PACKS", "shader": "SHADERS"}
FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
COMMANDS = {"mod": "mods", "resourcepack": "resourcepack", "shader": "shader"}


def _make_backup(path: Path) -> Path:
    with tempfile.NamedTemporaryFile(prefix=".javbed-update-", suffix=".backup", dir=path.parent, delete=False) as handle:
        backup = Path(handle.name)
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError:
        backup.unlink(missing_ok=True)
        raise


def _finish_update(path: Path, backup: Path, new_file: Path, success: bool, instance: str, kind: str, record: dict, version: dict) -> bool:
    try:
        if success and new_file.is_file():
            if path != new_file and path.exists():
                path.unlink()
            if path.name.endswith(".disabled"):
                target = new_file.with_name(new_file.name + ".disabled")
                new_file.replace(target)
            content_registry.remove(instance, kind, path.name.removesuffix(".disabled"))
            content_registry.upsert({**record, "file_name": version["file_name"], "version_id": version["id"], "version": version["version"]})
            return True
        shutil.copy2(backup, path)
        return False
    finally:
        backup.unlink(missing_ok=True)


def _has_shader_loader(item: dict) -> bool:
    folder = Path(str(item["path"])) / "minecraft" / "mods"
    return folder.is_dir() and any(any(name in path.name.lower() for name in ("iris", "optifine", "oculus")) for path in folder.iterdir() if path.is_file() and not path.name.endswith(".disabled"))


class ContentBrowser(QWidget):
    def __init__(self, kind: str, run_command, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.run_command = run_command
        self.pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)
        self.job = None
        self.latest = {}
        self.version_job = None
        self.latest_labels = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        title = QLabel(TITLES[kind])
        title.setObjectName("heroTitle")
        root.addWidget(title)
        filters = QHBoxLayout()
        self.instance = QComboBox()
        self.instance.currentIndexChanged.connect(self.refresh_installed)
        filters.addWidget(QLabel("Instance"))
        filters.addWidget(self.instance)
        self.provider = QComboBox()
        self.provider.addItems(["Modrinth", "CurseForge"] if kind == "mod" else ["Modrinth"])
        filters.addWidget(self.provider)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search " + TITLES[kind].lower())
        self.query.returnPressed.connect(self.search)
        filters.addWidget(self.query, 1)
        search_button = QPushButton("SEARCH")
        search_button.setObjectName("secondary")
        search_button.clicked.connect(self.search)
        filters.addWidget(search_button)
        root.addLayout(filters)
        actions = QHBoxLayout()
        self.browse_button = QPushButton("BROWSE")
        self.installed_button = QPushButton("INSTALLED")
        for button in (self.browse_button, self.installed_button):
            button.setObjectName("tab")
            button.setCheckable(True)
            actions.addWidget(button)
        self.browse_button.setChecked(True)
        self.browse_button.clicked.connect(lambda: self.switch_view(False))
        self.installed_button.clicked.connect(lambda: self.switch_view(True))
        actions.addStretch()
        if kind == "mod":
            update_all = QPushButton("UPDATE ALL")
            update_all.setObjectName("secondary")
            update_all.clicked.connect(self.update_all)
            actions.addWidget(update_all)
        folder = QPushButton("OPEN FOLDER")
        folder.setObjectName("secondary")
        folder.clicked.connect(self.open_folder)
        actions.addWidget(folder)
        root.addLayout(actions)
        self.status = QLabel("Choose an instance and search.")
        self.status.setObjectName("small")
        root.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_widget)
        root.addWidget(self.scroll, 1)
        self.installed_view = False
        self.updating = False
        self.refresh_instances()

    def refresh_instances(self, refresh_view=True):
        previous = self.instance.currentText()
        self.instance.blockSignals(True)
        self.instance.clear()
        for item in list_instances():
            self.instance.addItem(str(item["name"]), item)
        self.instance.setCurrentText(previous)
        self.instance.blockSignals(False)
        if self.installed_view and refresh_view:
            self.refresh_installed()

    def selected(self):
        item = self.instance.currentData()
        if not item:
            self.status.setText("Create or import a Java instance first.")
            return None
        return item

    def folder(self, item):
        return Path(str(item["path"])) / "minecraft" / FOLDERS[self.kind]

    def switch_view(self, installed: bool):
        self.installed_view = installed
        self.browse_button.setChecked(not installed)
        self.installed_button.setChecked(installed)
        if installed:
            self.refresh_installed()
        else:
            self.clear_cards()
            self.status.setText("Search " + TITLES[self.kind].lower() + " for this instance.")

    def clear_cards(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_card(self, title: str, description: str, actions: list[tuple[str, object]], icon_url: str = ""):
        card = QFrame()
        card.setObjectName("hero")
        layout = QVBoxLayout(card)
        headline = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(48, 48)
        if icon_url.startswith("https://"):
            reply = self.network.get(QNetworkRequest(QUrl(icon_url)))

            def loaded():
                data = bytes(reply.readAll())
                if len(data) <= 512 * 1024:
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        try:
                            icon.setPixmap(pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        except RuntimeError:
                            pass
                reply.deleteLater()

            reply.finished.connect(loaded)
        headline.addWidget(icon)
        copy = QVBoxLayout()
        label = QLabel(title)
        label.setObjectName("game")
        copy.addWidget(label)
        detail = QLabel(description)
        detail.setWordWrap(True)
        copy.addWidget(detail)
        headline.addLayout(copy, 1)
        layout.addLayout(headline)
        row = QHBoxLayout()
        for text, callback in actions:
            button = QPushButton(text)
            button.setObjectName("play" if text == "INSTALL" else "secondary")
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.list_layout.insertWidget(self.list_layout.count() - 1, card)
        return detail

    def search(self):
        item = self.selected()
        if not item or self.job:
            return
        query = self.query.text().strip()
        if not query:
            self.status.setText("Enter a search term.")
            return
        provider = self.provider.currentText().lower()
        loader = str(item.get("loader") or "vanilla")
        key = str(settings.load().get("curseforge_api_key", ""))
        self.status.setText("Searching " + provider + "...")
        job = Job(lambda: content.search(provider, self.kind, query, str(item.get("version", "")), loader, key))
        self.job = job

        def done(ok, result):
            self.job = None
            if not ok:
                self.status.setText(str(result))
                return
            self.installed_view = False
            self.browse_button.setChecked(True)
            self.installed_button.setChecked(False)
            self.clear_cards()
            self.status.setText(f"{len(result)} compatible results" if result else "No compatible results.")
            for hit in result:
                info = f'{hit["author"]} · {hit["downloads"]:,} downloads · {", ".join(hit["versions"][-4:])}\n{hit["description"]}'
                self.add_card(hit["name"], info, [("INSTALL", lambda checked=False, project=hit: self.install(project))], hit["icon"])

        job.signals.done.connect(done)
        self.pool.start(job)

    def install(self, hit):
        item = self.selected()
        if not item or self.job:
            return
        loader = str(item.get("loader") or "vanilla")
        if self.kind == "mod" and loader == "vanilla":
            self.status.setText("This instance has no mod loader. Add Fabric, Quilt, Forge, or NeoForge first.")
            return
        key = str(settings.load().get("curseforge_api_key", ""))
        self.status.setText("Checking the exact compatible version...")
        def check():
            version = content.newest_compatible(hit["provider"], self.kind, hit["id"], str(item["version"]), loader, key)
            return (version, _has_shader_loader(item)) if self.kind == "shader" else version

        job = Job(check)
        self.job = job

        def checked(ok, result):
            self.job = None
            version, shader_ready = result if ok and self.kind == "shader" else (result, True)
            if not ok or not version:
                self.status.setText(str(version) if not ok else "No compatible version exists for this instance.")
                return
            command = [COMMANDS[self.kind], "install", hit["id"], "--instance", item["name"]]
            command += (["--file-id", version["id"]] if hit["provider"] == "curseforge" else ["--version-id", version["id"]])
            if self.kind == "mod":
                command += ["--minecraft", str(item["version"]), "--loader", loader]
                if hit["provider"] == "curseforge":
                    command += ["--provider", "curseforge"]
            self.status.setText("Installing " + hit["name"] + "...")

            def installed(success, output):
                if not success:
                    self.status.setText("Install failed: " + output.strip()[-180:])
                    return
                filename = version["file_name"]
                if filename and (self.folder(item) / filename).is_file():
                    content_registry.upsert({"instance": item["name"], "kind": self.kind, "file_name": filename, "provider": hit["provider"], "project": hit["id"], "project_name": hit["name"], "version_id": version["id"], "version": version["version"], "icon": hit.get("icon", "")})
                self.status.setText("Installed " + hit["name"] + (". A shader loader is still required." if self.kind == "shader" and not shader_ready and not install_iris else ""))
                if self.installed_view:
                    self.refresh_installed()

            install_iris = False
            if self.kind == "shader" and not shader_ready:
                if loader in ("fabric", "quilt", "neoforge"):
                    response = QMessageBox.question(self, "Shader Loader Required", "This shader pack needs a shader loader such as Iris. Install compatible Iris and its required mods before installing the shader?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                    if response == QMessageBox.StandardButton.Cancel:
                        return
                    install_iris = response == QMessageBox.StandardButton.Yes
                else:
                    response = QMessageBox.question(self, "Shader Loader Required", "A compatible shader loader is required for this instance. JAVBED cannot safely install one for this loader automatically. Install the shader pack anyway?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if response != QMessageBox.StandardButton.Yes:
                        return
            if install_iris:
                iris_command = ["mods", "install", "iris", "--instance", item["name"], "--minecraft", str(item["version"]), "--loader", loader]

                def iris_done(success, output):
                    if success:
                        self.run_command(command, installed)
                    else:
                        self.status.setText("Iris installation failed: " + output.strip()[-180:])

                self.run_command(iris_command, iris_done)
            else:
                self.run_command(command, installed)

        job.signals.done.connect(checked)
        self.pool.start(job)

    def refresh_installed(self):
        if not self.installed_view or self.job:
            return
        item = self.selected()
        if not item:
            return
        folder = self.folder(item)
        job = Job(lambda: sorted(path for path in folder.iterdir() if path.is_file() and (path.suffix.lower() in (".jar", ".zip") or path.name.endswith(".disabled"))) if folder.is_dir() else [])
        self.job = job
        self.status.setText("Scanning installed files...")

        def done(ok, result):
            self.job = None
            if not ok:
                self.status.setText(str(result))
                return
            self.clear_cards()
            self.latest_labels = {}
            self.status.setText(f"{len(result)} installed {TITLES[self.kind].lower()}" if result else "Nothing installed here yet.")
            for path in result:
                base = path.name.removesuffix(".disabled")
                record = content_registry.lookup(item["name"], self.kind, base)
                name = record.get("project_name", base) if record else base
                version = record.get("version", "Unknown version") if record else "Local file"
                actions = []
                if self.kind == "mod":
                    actions.append(("ENABLE" if path.name.endswith(".disabled") else "DISABLE", lambda checked=False, file=path: self.toggle(file)))
                if record:
                    actions.append(("UPDATE", lambda checked=False, file=path, metadata=record: self.update(file, metadata)))
                actions.append(("REMOVE", lambda checked=False, file=path: self.remove(file)))
                detail = self.add_card(name, version + " · " + path.name, actions, record.get("icon", "") if record else "")
                if record:
                    self.latest_labels[base] = (detail, record)
            self.check_latest(item)

        job.signals.done.connect(done)
        self.pool.start(job)

    def check_latest(self, item):
        if self.version_job or not self.latest_labels:
            return
        entries = {name: record for name, (_, record) in self.latest_labels.items()}
        key = str(settings.load().get("curseforge_api_key", ""))
        loader = str(item.get("loader") or "vanilla")

        def query_one(entry):
            name, record = entry
            cache_key = (record["provider"], self.kind, record["project"], str(item["version"]), loader)
            cached = self.latest.get(cache_key)
            if cached and time.time() - cached[0] < 300:
                return name, cached[1], cache_key
            try:
                newest = content.newest_compatible(record["provider"], self.kind, record["project"], str(item["version"]), loader, key)
            except Exception:
                newest = None
            return name, newest, cache_key

        def query_all():
            with ThreadPoolExecutor(max_workers=4) as executor:
                return list(executor.map(query_one, entries.items()))

        job = Job(query_all)
        self.version_job = job

        def done(ok, result):
            self.version_job = None
            if not ok or not self.installed_view or self.instance.currentText() != item["name"]:
                return
            for name, newest, cache_key in result:
                self.latest[cache_key] = (time.time(), newest)
                pair = self.latest_labels.get(name)
                if pair:
                    label, record = pair
                    if newest:
                        suffix = "Update available" if newest["id"] != record.get("version_id") else "Up to date"
                        try:
                            label.setText(f'Installed: {record.get("version", "?")} · Newest compatible: {newest["version"]} · {suffix}')
                        except RuntimeError:
                            pass

        job.signals.done.connect(done)
        self.pool.start(job)

    def toggle(self, path: Path):
        target = path.with_name(path.name.removesuffix(".disabled") if path.name.endswith(".disabled") else path.name + ".disabled")
        if target.exists():
            self.status.setText("Cannot change state: destination already exists.")
            return
        job = Job(lambda: path.rename(target))
        job.signals.done.connect(lambda ok, result: self.refresh_installed() if ok else self.status.setText(str(result)))
        self.pool.start(job)

    def remove(self, path: Path):
        if QMessageBox.question(self, "Remove File", "Remove " + path.name + " from this instance?") != QMessageBox.StandardButton.Yes:
            return
        item = self.selected()
        job = Job(path.unlink)

        def done(ok, result):
            if ok:
                content_registry.remove(item["name"], self.kind, path.name.removesuffix(".disabled"))
                self.refresh_installed()
            else:
                self.status.setText(str(result))

        job.signals.done.connect(done)
        self.pool.start(job)

    def update(self, path: Path, record: dict, on_done=None):
        item = self.selected()
        if not item or self.job or self.updating:
            if on_done:
                on_done()
            return
        self.updating = True
        loader = str(item.get("loader") or "vanilla")
        key = str(settings.load().get("curseforge_api_key", ""))
        job = Job(lambda: content.newest_compatible(record["provider"], self.kind, record["project"], str(item["version"]), loader, key))
        self.job = job
        self.status.setText("Checking newest compatible version...")

        def checked(ok, version):
            self.job = None
            if not ok or not version:
                self.status.setText(str(version) if not ok else "No compatible update found.")
                self.updating = False
                if on_done: on_done()
                return
            if version["id"] == record.get("version_id"):
                self.status.setText(record["project_name"] + " is up to date.")
                self.updating = False
                if on_done: on_done()
                return
            hit = {"provider": record["provider"], "id": record["project"], "name": record["project_name"]}
            backup_job = Job(lambda: _make_backup(path))
            self.job = backup_job
            self.status.setText("Saving current file before update...")

            def backed_up(saved, backup):
                self.job = None
                if not saved:
                    self.status.setText("Could not make safety copy: " + str(backup))
                    self.updating = False
                    if on_done: on_done()
                    return

                def finished(success, output):
                    new_file = self.folder(item) / version["file_name"]
                    final_job = Job(lambda: _finish_update(path, backup, new_file, success, item["name"], self.kind, record, version))
                    self.job = final_job

                    def finalized(ok, updated):
                        self.job = None
                        self.updating = False
                        self.status.setText(("Updated " + record["project_name"]) if ok and updated else ("Update failed: " + (str(updated) if not ok else output.strip()[-180:])))
                        if self.installed_view and not on_done:
                            self.refresh_installed()
                        if on_done:
                            on_done()

                    final_job.signals.done.connect(finalized)
                    self.pool.start(final_job)

                command = [COMMANDS[self.kind], "install", hit["id"], "--instance", item["name"]]
                command += (["--file-id", version["id"]] if hit["provider"] == "curseforge" else ["--version-id", version["id"]])
                if self.kind == "mod":
                    command += ["--minecraft", str(item["version"]), "--loader", loader]
                    if hit["provider"] == "curseforge":
                        command += ["--provider", "curseforge"]
                self.run_command(command, finished)

            backup_job.signals.done.connect(backed_up)
            self.pool.start(backup_job)

        job.signals.done.connect(checked)
        self.pool.start(job)

    def update_all(self, on_done=None):
        item = self.selected()
        if not item or self.job or self.updating:
            if callable(on_done): on_done()
            return
        folder = self.folder(item)
        rows = content_registry.load()
        queue = [(folder / row["file_name"], row) for row in rows if row.get("instance") == item["name"] and row.get("kind") == "mod"]
        queue = [(path if path.exists() else path.with_name(path.name + ".disabled"), row) for path, row in queue]
        queue = [(path, row) for path, row in queue if path.is_file()]
        if not queue:
            self.status.setText("No tracked mods to update.")
            if callable(on_done): on_done()
            return

        def next_item():
            if queue:
                path, record = queue.pop(0)
                self.update(path, record, next_item)
            else:
                self.status.setText("Update pass complete.")
                if self.installed_view:
                    self.refresh_installed()
                if callable(on_done): on_done()

        next_item()

    def open_folder(self):
        item = self.selected()
        if not item:
            return
        folder = self.folder(item)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
