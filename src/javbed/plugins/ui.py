"""Native plugin management UI and reusable API 1 widgets."""

import tempfile
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Qt, QSize
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from javbed.jobs import Job

from .packages import inspect
from .permissions import HIGH_RISK
from .updates import check, download

WARNING = "Plugins are third-party code and may execute code on your computer. Only install plugins you trust. Permissions limit JAVBED APIs; they are not an OS sandbox."


class SectionTitle(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("heroTitle")


class JavbedButton(QPushButton):
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.setObjectName("play" if primary else "secondary")


class StatusBadge(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setObjectName("small")


class PluginCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("hero")


class ProgressCard(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("hero")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.status = QLabel("")
        layout.addWidget(self.status)


class PluginExtensionsPage(QWidget):
    """Launcher-owned surface for plugin integrations and tools."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        root.addWidget(SectionTitle("EXTENSIONS"))
        self.status = QLabel("Plugin integrations and tools")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.rows = QVBoxLayout(container)
        self.rows.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)
        self.refresh()

    def refresh(self):
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        kinds = (("game", "Games and launchers"), ("server_provider", "Server providers"), ("java_tool", "Java tools"), ("update_provider", "Update providers"))
        found = False
        for kind, label in kinds:
            entries = self.manager.contributions.all(kind)
            if not entries:
                continue
            found = True
            self.rows.insertWidget(self.rows.count() - 1, SectionTitle(label.upper()))
            for contribution in entries:
                card = PluginCard()
                layout = QHBoxLayout(card)
                title = QLabel(contribution.title + "  ·  " + contribution.owner)
                title.setTextFormat(Qt.TextFormat.PlainText)
                layout.addWidget(title, 1)
                button = JavbedButton("CREATE" if kind == "server_provider" else "RUN" if kind == "java_tool" else "CHECK" if kind == "update_provider" else "LAUNCH")
                button.clicked.connect(lambda checked=False, item=contribution: self.activate(item))
                layout.addWidget(button)
                self.rows.insertWidget(self.rows.count() - 1, card)
        if not found:
            self.rows.insertWidget(0, QLabel("No plugin integrations are enabled."))

    def activate(self, item):
        if item.kind == "server_provider":
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "Create server", "Server name")
            if not ok:
                return
            from javbed.instances import valid_name
            if not valid_name(name):
                QMessageBox.warning(self, "Invalid name", "Use letters, numbers, dots, underscores or dashes.")
                return
            version, ok = QInputDialog.getText(self, "Create server", "Minecraft version")
            if not ok or not version.strip() or len(version) > 80:
                return
            args = (name, version.strip())
        else:
            args = ()
        self.status.setText("Running " + item.title + "...")
        def run():
            result = self.manager.contributions.invoke(item, *args)
            return str(result)[:250] if result is not None else "Completed"
        job = Job(run)

        def done(ok, result):
            if ok and self.manager.records.get(item.owner) and self.manager.records[item.owner].status == "enabled":
                self.status.setText(item.title + ": " + result)
            else:
                self.status.setText(item.title + " failed. See Plugin Manager logs.")

        job.signals.done.connect(done)
        self.pool.start(job)


class PluginManagerPage(QWidget):
    def __init__(self, manager, *, developer_mode=False, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.developer_mode = developer_mode
        self.pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        header = QHBoxLayout()
        header.addWidget(SectionTitle("PLUGINS"))
        header.addStretch()
        install = JavbedButton("INSTALL PLUGIN", True)
        install.clicked.connect(self.choose_install)
        header.addWidget(install)
        root.addLayout(header)
        warning = QLabel(WARNING)
        warning.setWordWrap(True)
        root.addWidget(warning)
        if manager.safe_mode:
            badge = StatusBadge("SAFE MODE — third-party plugins are disabled for this session.")
            root.addWidget(badge)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search installed plugins...")
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.cards = QVBoxLayout(container)
        self.cards.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)
        self.refresh()

    def refresh(self):
        while self.cards.count() > 1:
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self.search.text().lower() if hasattr(self, "search") else ""
        records = [record for record in self.manager.records.values() if query in record.id.lower() or (record.manifest and query in record.manifest.name.lower())]
        if not records:
            self.cards.insertWidget(0, QLabel("No plugins installed."))
        for record in records:
            self.cards.insertWidget(self.cards.count() - 1, self._card(record))

    def _card(self, record):
        card = PluginCard()
        layout = QVBoxLayout(card)
        manifest = record.manifest
        heading = QHBoxLayout()
        icon = QLabel("◆")
        icon.setFixedSize(48, 48)
        icon.setObjectName("game")
        if manifest and manifest.icon:
            path = record.path / manifest.icon
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024 * 1024:
                reader = QImageReader(str(path))
                size = reader.size()
                if size.isValid() and size.width() <= 2048 and size.height() <= 2048:
                    reader.setScaledSize(size.scaled(QSize(48, 48), Qt.AspectRatioMode.KeepAspectRatio))
                    image = reader.read()
                    if not image.isNull():
                        icon.setPixmap(QPixmap.fromImage(image))
        heading.addWidget(icon)
        details = QVBoxLayout()
        title = QLabel((manifest.name if manifest else record.id) + (f"  v{manifest.version}" if manifest else ""))
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("game")
        details.addWidget(title)
        if manifest:
            author=QLabel("by " + manifest.author);author.setTextFormat(Qt.TextFormat.PlainText);details.addWidget(author)
        heading.addLayout(details,1)
        layout.addLayout(heading)
        if manifest:
            description = QLabel(manifest.description)
            description.setTextFormat(Qt.TextFormat.PlainText)
            description.setWordWrap(True)
            layout.addWidget(description)
            permissions = ", ".join(sorted(manifest.permissions.names)) or "None"
            layout.addWidget(QLabel("Permissions: " + permissions))
        layout.addWidget(StatusBadge(record.status.upper() + (" — " + record.error if record.error else "")))
        if self.developer_mode and manifest:
            layout.addWidget(QLabel(f"Path: {record.path} | Plugin API {manifest.api_version} | Load: {record.startup_seconds:.2f}s"))
        actions = QHBoxLayout()
        if manifest and not self.manager.safe_mode:
            toggle = JavbedButton("DISABLE" if record.plugin else "ENABLE")
            toggle.clicked.connect(lambda checked=False, item=record: self.disable(item) if item.plugin else self.enable(item))
            actions.addWidget(toggle)
            if record.plugin and any(item.owner == record.id for item in self.manager.ui.all("settings_page")):
                settings = JavbedButton("SETTINGS")
                settings.clicked.connect(lambda checked=False, item=record: self.open_settings(item))
                actions.addWidget(settings)
            if self.developer_mode and record.plugin:
                reload_button = JavbedButton("RELOAD")
                reload_button.clicked.connect(lambda checked=False, item=record: self.reload(item))
                actions.addWidget(reload_button)
        more = JavbedButton("•••")
        menu = QMenu(more)
        if manifest:
            menu.addAction("View permissions", lambda item=record: self.view_permissions(item))
        menu.addAction("Open plugin folder", lambda item=record: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path))))
        menu.addAction("View logs", lambda item=record: self.open_logs(item))
        if manifest and manifest.update_repo and not self.manager.safe_mode:
            menu.addAction("Check update", lambda item=record: self.check_update(item))
        menu.addAction("Uninstall", lambda item=record: self.uninstall(item))
        more.setMenu(menu)
        actions.addWidget(more)
        actions.addStretch()
        layout.addLayout(actions)
        return card

    def _approve(self, manifest, verb):
        permissions = "\n".join(("HIGH RISK: " if name in HIGH_RISK else "") + name for name in sorted(manifest.permissions.names)) or "None"
        message = f"{verb} {manifest.name} v{manifest.version} by {manifest.author}?\n\nRequested permissions:\n{permissions}\n\n{WARNING}"
        return QMessageBox.question(self, "Review plugin permissions", message) == QMessageBox.StandardButton.Yes

    def view_permissions(self, record):
        permissions = "\n".join(("HIGH RISK: " if name in HIGH_RISK else "") + name for name in sorted(record.manifest.permissions.names)) or "None"
        QMessageBox.information(self, "Plugin permissions", record.manifest.name + " requests:\n" + permissions + "\n\n" + WARNING)

    def enable(self, record):
        if not self._approve(record.manifest, "Enable"):
            return
        try:
            self.manager.enable(record.id, approve=True)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin failed", str(exc))
        self.refresh()

    def disable(self, record):
        try:
            self.manager.disable(record.id)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot disable plugin", str(exc))
        self.refresh()

    def reload(self, record):
        try:
            self.manager.reload(record.id)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin failed", str(exc))
        self.refresh()

    def choose_install(self):
        choice = QMessageBox.question(self, "Install plugin", "Install from a directory? Choose No for a ZIP or .javbedplugin package.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Cancel:
            return
        if choice == QMessageBox.StandardButton.Yes:
            source = QFileDialog.getExistingDirectory(self, "Choose plugin directory")
        else:
            source, _ = QFileDialog.getOpenFileName(self, "Choose plugin package", "", "Plugin packages (*.javbedplugin *.zip)")
        if not source:
            return
        try:
            manifest = inspect(Path(source))
            if not self._approve(manifest, "Install and enable"):
                return
            record = self.manager.install(Path(source))
            self.manager.enable(record.id, approve=True)
        except Exception as exc:
            QMessageBox.warning(self, "Plugin installation failed", str(exc))
        self.refresh()

    def uninstall(self, record):
        if QMessageBox.question(self, "Uninstall plugin", f"Remove {record.id}? Plugin data is retained.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.uninstall(record.id)
        except Exception as exc:
            QMessageBox.warning(self, "Uninstall failed", str(exc))
        self.refresh()

    def open_settings(self, record):
        for item in self.manager.ui.all("settings_page"):
            if item.owner != record.id:
                continue
            widget = self.manager.ui.invoke(item)
            if widget is None:
                continue
            if not isinstance(widget, QWidget):
                self.manager._fail(record.id, "settings widget", TypeError("Factory must return QWidget"))
                self.refresh()
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(item.title)
            dialog.resize(600, 440)
            layout = QVBoxLayout(dialog)
            layout.addWidget(widget)
            dialog.exec()
            return

    def open_logs(self, record):
        path = self.manager.log_root / (record.id + ".log")
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(self, "Plugin logs", "No log has been written for this plugin yet.")

    def check_update(self, record):
        job = Job(lambda: check(record.manifest))
        def checked(ok, update):
            if not ok:
                QMessageBox.warning(self, "Update check failed", str(update))
                return
            if not update:
                QMessageBox.information(self, "Plugin update", "This plugin is up to date.")
                return
            if QMessageBox.question(self, "Plugin update", f"{record.manifest.name}: installed {record.manifest.version}, available {update.version}. Download and review package?") != QMessageBox.StandardButton.Yes:
                return
            temporary = tempfile.TemporaryDirectory()
            path = Path(temporary.name) / "update.javbedplugin"
            download_job = Job(lambda: download(update, path))
            def downloaded(success, result):
                try:
                    if not success:
                        raise RuntimeError(str(result))
                    manifest = inspect(path)
                    from .manifest import compare
                    if manifest.id != record.id or compare(manifest.version, record.manifest.version) <= 0:
                        raise ValueError("Update package has the wrong ID or version")
                    if not self._approve(manifest, "Update"):
                        return
                    new = self.manager.install(path, replace=True)
                    self.manager.enable(new.id, approve=True)
                except Exception as exc:
                    QMessageBox.warning(self, "Plugin update failed", str(exc))
                finally:
                    temporary.cleanup()
                    self.refresh()
            download_job.signals.done.connect(downloaded)
            self.pool.start(download_job)
        job.signals.done.connect(checked)
        self.pool.start(job)
