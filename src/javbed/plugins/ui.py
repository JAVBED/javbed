"""Native plugin management UI and reusable API 1 widgets."""

import tempfile
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Qt, QSize
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
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
        self._jobs = set()
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
        kinds = (("game", "Games and launchers"), ("server_provider", "Server providers"), ("importer", "Importers"), ("java_tool", "Java tools"), ("update_provider", "Update providers"))
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
                button = JavbedButton("MANAGE" if kind == "server_provider" and contribution.handlers else "CREATE" if kind == "server_provider" else "IMPORT" if kind == "importer" else "RUN" if kind == "java_tool" else "CHECK" if kind == "update_provider" else "BROWSE" if contribution.handlers else "LAUNCH")
                button.clicked.connect(lambda checked=False, item=contribution: self.activate(item))
                layout.addWidget(button)
                self.rows.insertWidget(self.rows.count() - 1, card)
        if not found:
            self.rows.insertWidget(0, QLabel("No plugin integrations are enabled."))

    def activate(self, item):
        if item.kind == "importer":
            source, _ = QFileDialog.getOpenFileName(self, "Import file")
            if source:
                self._run(item, lambda: self.manager.contributions.invoke(item, Path(source)))
            return
        if item.kind == "game" and item.handlers:
            self._choose_game(item)
            return
        if item.kind == "server_provider" and item.handlers:
            self._manage_servers(item)
            return
        if item.kind == "update_provider" and item.handlers:
            self._check_updates(item)
            return
        if item.kind == "server_provider":
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
        self._run(item, lambda: self.manager.contributions.invoke(item, *args))

    def _run(self, item, callback):
        self.status.setText("Running " + item.title + "...")
        def run():
            result = callback()
            return str(result)[:250] if result is not None else "Completed"
        job = Job(run)

        def done(ok, result):
            if ok and self.manager.records.get(item.owner) and self.manager.records[item.owner].status == "enabled":
                self.status.setText(item.title + ": " + result)
            else:
                self.status.setText(item.title + " failed. See Plugin Manager logs.")

        self._start(job, done)

    def _start(self, job, callback):
        self._jobs.add(job)
        def completed(ok, result):
            self._jobs.discard(job)
            callback(ok, result)
        job.signals.done.connect(completed)
        self.pool.start(job)

    def _choose_game(self, item):
        from .api import GameInfo
        self.status.setText("Finding games for " + item.title + "...")
        job = Job(lambda: self.manager.contributions.invoke_handler(item, "discover"))
        def done(ok, rows):
            if not ok or not isinstance(rows, (list, tuple)) or any(not isinstance(row, GameInfo) for row in rows):
                self.status.setText("Could not discover games. See Plugin Manager logs.")
                return
            if not rows:
                self.status.setText("No games found for " + item.title)
                return
            labels = [f"{row.title} ({row.version})" if row.version else row.title for row in rows]
            choice, accepted = QInputDialog.getItem(self, "Launch game", "Choose a game", labels, 0, False)
            if accepted:
                game = rows[labels.index(choice)]
                self._run(item, lambda: self.manager.contributions.invoke_handler(item, "launch", game.id))
        self._start(job, done)

    def _manage_servers(self, item):
        from .api import ServerInfo
        self.status.setText("Finding servers for " + item.title + "...")
        job = Job(lambda: self.manager.contributions.invoke_handler(item, "list"))
        def done(ok, rows):
            if not ok or not isinstance(rows, (list, tuple)) or any(not isinstance(row, ServerInfo) or row.provider != item.id for row in rows):
                self.status.setText("Could not list servers. See Plugin Manager logs.")
                return
            choices = ["Create new server"] + [f"{row.name} ({'running' if row.running else 'stopped'})" for row in rows]
            choice, accepted = QInputDialog.getItem(self, "Server provider", "Choose a server", choices, 0, False)
            if not accepted:
                return
            if choice == choices[0]:
                name, accepted = QInputDialog.getText(self, "Create server", "Server name")
                if not accepted:
                    return
                from javbed.instances import valid_name
                if not valid_name(name):
                    QMessageBox.warning(self, "Invalid name", "Use letters, numbers, dots, underscores or dashes.")
                    return
                version, accepted = QInputDialog.getText(self, "Create server", "Minecraft version")
                if accepted and version.strip() and len(version) <= 80:
                    self._run(item, lambda: self.manager.contributions.invoke_handler(item, "create", name, version.strip()))
                return
            server = rows[choices.index(choice) - 1]
            actions = ["Start", "Stop", "Restart", "Backup", "Send command"]
            action, accepted = QInputDialog.getItem(self, server.name, "Action", actions, 0, False)
            if not accepted:
                return
            method = action.lower().replace(" ", "_")
            if method == "send_command":
                command, accepted = QInputDialog.getText(self, server.name, "Console command")
                if not accepted or not command.strip() or "\n" in command or "\r" in command:
                    return
                self._run(item, lambda: self.manager.contributions.invoke_handler(item, method, server.name, command))
            else:
                self._run(item, lambda: self.manager.contributions.invoke_handler(item, method, server.name))
        self._start(job, done)

    def _check_updates(self, item):
        from .api import UpdateInfo
        self.status.setText("Checking updates from " + item.title + "...")
        job = Job(lambda: self.manager.contributions.invoke_handler(item, "check"))
        def done(ok, rows):
            if not ok or not isinstance(rows, (list, tuple)) or any(not isinstance(row, UpdateInfo) for row in rows):
                self.status.setText("Update check failed. See Plugin Manager logs.")
                return
            if not rows:
                self.status.setText("No updates available from " + item.title)
                return
            labels = [f"{row.title}: {row.installed_version} → {row.available_version}" for row in rows]
            choice, accepted = QInputDialog.getItem(self, "Available updates", "Choose an update", labels, 0, False)
            if not accepted:
                return
            selected = rows[labels.index(choice)]
            if QMessageBox.question(self, "Apply update", f"Apply {selected.title} {selected.available_version}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self._run(item, lambda: self.manager.contributions.invoke_handler(item, "apply", selected.id))
        self._start(job, done)


class PluginManagerPage(QWidget):
    def __init__(self, manager, *, developer_mode=False, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.developer_mode = developer_mode
        self.pool = QThreadPool.globalInstance()
        self._jobs = set()
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
                    self.manager.update(path, approve=True)
                except Exception as exc:
                    QMessageBox.warning(self, "Plugin update failed", str(exc))
                finally:
                    temporary.cleanup()
                    self.refresh()
            self._start(download_job, downloaded)
        self._start(job, checked)

    def _start(self, job, callback):
        self._jobs.add(job)
        def completed(ok, result):
            self._jobs.discard(job)
            callback(ok, result)
        job.signals.done.connect(completed)
        self.pool.start(job)
