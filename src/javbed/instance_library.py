"""Graphical JAVLI instance library and creation wizard."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from .instances import remove_preferences, save_icon, save_preferences, snapshot, valid_name
from .packages import export_package
from .jobs import Job


class InstanceWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Java Instance")

        identity = QWizardPage()
        identity.setTitle("Name")
        form = QFormLayout(identity)
        self.name = QLineEdit()
        self.name.setPlaceholderText("survival")
        identity.registerField("name*", self.name)
        form.addRow("Instance name", self.name)
        self.addPage(identity)

        version = QWizardPage()
        version.setTitle("Minecraft version and type")
        form = QFormLayout(version)
        self.era = QComboBox()
        self.era.addItems(["release", "snapshot", "beta", "alpha", "infdev", "indev", "classic", "preclassic"])
        self.version = QLineEdit()
        self.version.setPlaceholderText("1.21.1")
        version.registerField("version*", self.version)
        form.addRow("Type", self.era)
        form.addRow("Version", self.version)
        self.addPage(version)

        loader = QWizardPage()
        loader.setTitle("Mod loader")
        form = QFormLayout(loader)
        self.loader = QComboBox()
        self.loader.addItems(["Vanilla", "Fabric", "Quilt", "Forge", "NeoForge"])
        self.loader_version = QLineEdit()
        self.loader_version.setPlaceholderText("Latest compatible")
        form.addRow("Loader", self.loader)
        form.addRow("Loader version", self.loader_version)
        self.addPage(loader)

        options = QWizardPage()
        options.setTitle("Memory, window, and icon")
        form = QFormLayout(options)
        self.memory = QSpinBox()
        self.memory.setRange(512, 65536)
        self.memory.setValue(4096)
        self.memory.setSuffix(" MB")
        self.width = QSpinBox()
        self.width.setRange(640, 7680)
        self.width.setValue(1280)
        self.height = QSpinBox()
        self.height.setRange(480, 4320)
        self.height.setValue(720)
        self.runtime = QComboBox()
        self.runtime.addItems(["Automatic (JAVLI)", "Java 8", "Java 17", "Java 21", "Java 25"])
        self.icon = QLineEdit()
        icon_button = QPushButton("BROWSE")
        icon_button.setObjectName("secondary")
        icon_button.clicked.connect(self.choose_icon)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon)
        icon_row.addWidget(icon_button)
        form.addRow("RAM", self.memory)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("Java runtime", self.runtime)
        form.addRow("Icon", icon_row)
        self.addPage(options)

    def choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose instance icon", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.icon.setText(path)

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "era": self.era.currentText(),
            "version": self.version.text().strip(),
            "loader": self.loader.currentText().lower(),
            "loader_version": self.loader_version.text().strip(),
            "memory_mb": self.memory.value(),
            "width": self.width.value(),
            "height": self.height.value(),
            "java_major": int(self.runtime.currentText().split()[-1]) if self.runtime.currentIndex() else None,
            "icon": self.icon.text().strip(),
        }


class InstanceLibrary(QWidget):
    def __init__(self, run_command, parent=None):
        super().__init__(parent)
        self.run_command = run_command
        self.pool = QThreadPool.globalInstance()
        self.refresh_job = None
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        header = QHBoxLayout()
        title = QLabel("JAVA INSTANCES")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch()
        create = QPushButton("+ CREATE INSTANCE")
        create.setObjectName("play")
        create.clicked.connect(self.create_instance)
        header.addWidget(create)
        refresh = QPushButton("REFRESH")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        root.addLayout(header)
        self.status = QLabel("Loading instances...")
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
        self.refresh()

    def refresh(self):
        if self.refresh_job:
            return
        job = Job(snapshot)
        self.refresh_job = job
        self.status.setText("Scanning JAVLI instances...")

        def done(ok, result):
            self.refresh_job = None
            if not ok:
                self.status.setText("Could not read instances: " + str(result))
                return
            self.show_instances(result)

        job.signals.done.connect(done)
        self.pool.start(job)

    def show_instances(self, rows):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.status.setText(f"{len(rows)} JAVLI instance{'s' if len(rows) != 1 else ''}" if rows else "No instances yet. Create one to get started.")
        for item in rows:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self.card(item))

    def card(self, item):
        frame = QFrame()
        frame.setObjectName("hero")
        row = QHBoxLayout(frame)
        icon = QLabel()
        icon.setFixedSize(56, 56)
        image = Path(str(item.get("preferences", {}).get("icon", "")))
        if image.is_file():
            icon.setPixmap(QPixmap(str(image)).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon.setText("⛏")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(icon)
        meta = QVBoxLayout()
        name = QLabel(str(item["name"]))
        name.setObjectName("game")
        meta.addWidget(name)
        loader = str(item.get("loader") or "Vanilla")
        meta.addWidget(QLabel(f'{item.get("era", "release")} · {item.get("version", "?")} · {loader} · {item["mod_count"]} mods'))
        played = item.get("history", {})
        runtime = item.get("preferences", {}).get("java_major")
        meta.addWidget(QLabel(f'Java: {runtime or "Automatic"} · Last played: {played.get("last_played", "Never")[:16].replace("T", " ")} · Playtime: {played.get("total_seconds", 0) // 60} min'))
        row.addLayout(meta, 1)
        play = QPushButton("PLAY")
        play.setObjectName("play")
        play.clicked.connect(lambda: self.run(["instance", "launch", item["name"]]))
        row.addWidget(play)
        more = QPushButton("⋮")
        more.setObjectName("secondary")
        more.clicked.connect(lambda: self.show_menu(more, item))
        row.addWidget(more)
        return frame

    def run(self, args, after=None):
        self.status.setText("Working...")

        def finished(ok, output):
            self.status.setText(output.strip().splitlines()[-1][:180] if output.strip() else ("Done" if ok else "Command failed"))
            if ok:
                if after:
                    after()
                self.refresh()

        self.run_command(args, finished)

    def create_instance(self):
        wizard = InstanceWizard(self)
        if not wizard.exec():
            return
        values = wizard.values()
        if not valid_name(values["name"]):
            self.status.setText("Name may use letters, numbers, dots, underscores, and dashes.")
            return
        args = ["instance", "create", values["name"], values["era"], values["version"]]
        if values["loader"] != "vanilla":
            args += ["--loader", values["loader"]]
            if values["loader_version"]:
                args += ["--loader-version", values["loader_version"]]

        def save_options():
            save_preferences(values["name"], {"memory_mb": values["memory_mb"], "width": values["width"], "height": values["height"], "java_major": values["java_major"]})
            if values["icon"]:
                save_icon(values["name"], Path(values["icon"]))

        self.run(args, save_options)

    def show_menu(self, button, item):
        menu = QMenu(self)
        menu.addAction("Play in Safe Mode", lambda: self.parent().play_safe_mode(item["name"]))
        menu.addAction("Edit", lambda: self.edit_instance(item))
        menu.addAction("Clone", lambda: self.clone_instance(item))
        menu.addAction("Export .javbed", lambda: self.export_portable(item))
        menu.addAction("Open Folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item["path"]))))
        menu.addAction("Change Icon", lambda: self.change_icon(item))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.delete_instance(item))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def edit_instance(self, item):
        wizard = InstanceWizard(self)
        wizard.name.setText(item["name"])
        wizard.name.setEnabled(False)
        wizard.era.setCurrentText(str(item.get("era", "release")))
        wizard.version.setText(str(item.get("version", "")))
        loader = str(item.get("loader") or "vanilla").lower()
        wizard.loader.setCurrentIndex(["vanilla", "fabric", "quilt", "forge", "neoforge"].index(loader) if loader in ("vanilla", "fabric", "quilt", "forge", "neoforge") else 0)
        wizard.loader_version.setText(str(item.get("loader_version", "")))
        pref = item.get("preferences", {})
        wizard.memory.setValue(int(pref.get("memory_mb", 4096)))
        wizard.width.setValue(int(pref.get("width", 1280)))
        wizard.height.setValue(int(pref.get("height", 720)))
        if pref.get("java_major"):
            wizard.runtime.setCurrentText(f'Java {pref["java_major"]}')
        if not wizard.exec():
            return
        values = wizard.values()
        changes = []
        for field in ("era", "version", "loader", "loader_version"):
            old = str(item.get(field) or ("vanilla" if field == "loader" else ""))
            new = values[field]
            if old != new:
                changes.append(["instance", "set", item["name"], field, "" if field == "loader" and new == "vanilla" else new])

        def save_options():
            save_preferences(item["name"], {"memory_mb": values["memory_mb"], "width": values["width"], "height": values["height"], "java_major": values["java_major"]})
            if values["icon"]:
                save_icon(item["name"], Path(values["icon"]))

        def next_change():
            if changes:
                self.run(changes.pop(0), next_change)
            else:
                save_options()
                self.refresh()

        next_change()

    def clone_instance(self, item):
        name, ok = QInputDialog.getText(self, "Clone Instance", "New instance name")
        if ok and valid_name(name.strip()):
            source_pref = dict(item.get("preferences", {}))
            self.run(["instance", "clone", item["name"], name.strip()], lambda: save_preferences(name.strip(), source_pref))
        elif ok:
            self.status.setText("Invalid instance name.")

    def change_icon(self, item):
        path, _ = QFileDialog.getOpenFileName(self, "Choose instance icon", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            try:
                save_icon(item["name"], Path(path))
                self.refresh()
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))

    def delete_instance(self, item):
        answer = QMessageBox.question(self, "Delete Instance", f'Delete {item["name"]} and its files? This cannot be undone.')
        if answer == QMessageBox.StandardButton.Yes:
            self.run(["instance", "delete", item["name"]], lambda: remove_preferences(item["name"]))

    def export_portable(self, item):
        path, _ = QFileDialog.getSaveFileName(self, "Export JAVBED Instance", item["name"] + ".javbed", "JAVBED packages (*.javbed)")
        if not path:
            return
        destination = Path(path if path.lower().endswith(".javbed") else path + ".javbed")
        job = Job(lambda: export_package(item, destination))
        self.status.setText("Exporting instance manifest...")

        def done(ok, result):
            self.status.setText(("Exported " + str(result)) if ok else ("Export failed: " + str(result)))

        job.signals.done.connect(done)
        self.pool.start(job)
