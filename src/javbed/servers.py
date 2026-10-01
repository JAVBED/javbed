"""SERVLI-backed graphical server dashboard and live console."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from .engines import ENGINES
from .jobs import Job
from .settings import load as load_settings


def servli_home() -> Path:
    configured = str(load_settings().get("servli_home") or os.environ.get("SERVLI_HOME") or "").strip()
    return Path(configured) if configured else Path.home() / ".servli"


def _json_command(*args):
    command, error = ENGINES["Servers"].command(*args)
    if error:
        raise RuntimeError(error)
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "SERVLI command failed")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("SERVLI must support structured --json output. Update the SERVLI engine.") from exc


def server_snapshot() -> list[dict]:
    rows = _json_command("list", "--json")
    if not isinstance(rows, list):
        raise ValueError("Invalid SERVLI server list")
    return rows


def backup_snapshot(name: str) -> list[dict]:
    rows = _json_command("backups", name, "--json")
    if not isinstance(rows, list):
        raise ValueError("Invalid SERVLI backup list")
    return rows


def read_console(name: str, previous: tuple[str, int]) -> tuple[tuple[str, int], str]:
    folder = servli_home() / "servers" / name / "logs"
    paths = sorted(folder.glob("console-*.log")) if folder.is_dir() else []
    if not paths:
        return previous, ""
    path = paths[-1]
    identity = str(path)
    size = path.stat().st_size
    offset = (previous[1] if previous[1] <= size else 0) if previous[0] == identity else max(0, size - 8192)
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(128 * 1024)
        current = stream.tell()
    return (identity, current), data.decode("utf-8", errors="replace")


PROPERTIES = (
    ("MOTD", "motd", "text"), ("Port", "server-port", "port"),
    ("Max players", "max-players", "number"), ("Gamemode", "gamemode", "game"),
    ("Difficulty", "difficulty", "difficulty"), ("Online mode", "online-mode", "bool"),
    ("Whitelist", "white-list", "bool"), ("View distance", "view-distance", "distance"),
    ("Simulation distance", "simulation-distance", "distance"),
)


def parse_properties(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if line and not line.lstrip().startswith("#") and "=" in line)


def validate_property(key: str, value: str) -> str:
    kinds = {field: kind for _, field, kind in PROPERTIES}
    kind = kinds.get(key, "text")
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise ValueError("Property values must be one line")
    if kind in ("port", "number", "distance"):
        if not value.isdigit() or not 1 <= int(value) <= (65535 if kind == "port" else 100000 if kind == "number" else 32):
            raise ValueError(key + " is out of range")
    elif kind == "bool" and value not in ("true", "false"):
        raise ValueError(key + " must be true or false")
    elif kind == "game" and value not in ("survival", "creative", "adventure", "spectator"):
        raise ValueError("Unsupported gamemode")
    elif kind == "difficulty" and value not in ("peaceful", "easy", "normal", "hard"):
        raise ValueError("Unsupported difficulty")
    return value


class ServerDashboard(QWidget):
    unexpected_stop = Signal(str)
    def __init__(self, run_command, parent=None):
        super().__init__(parent)
        self.run_command = run_command
        self.pool = QThreadPool.globalInstance()
        self.job = None
        self.log_job = None
        self.addon_job = None
        self.status_job = None
        self.known_running = {}
        self.expected_stops = {}
        self.server = None
        self.log_cursor = ("", 0)
        self.loaded_properties = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 20, 30, 20)
        header = QHBoxLayout()
        title = QLabel("SERVERS")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.button("REFRESH", self.refresh))
        root.addLayout(header)
        self.status = QLabel("Loading SERVLI servers...")
        root.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.card_container = QWidget()
        self.cards = QVBoxLayout(self.card_container)
        self.cards.addStretch()
        self.scroll.setWidget(self.card_container)
        root.addWidget(self.scroll, 1)
        self.detail = QFrame()
        self.detail.setObjectName("hero")
        detail_layout = QVBoxLayout(self.detail)
        detail_header = QHBoxLayout()
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("heroTitle")
        detail_header.addWidget(self.detail_title)
        detail_header.addStretch()
        detail_header.addWidget(self.button("BACK TO SERVERS", self.show_cards))
        detail_layout.addLayout(detail_header)
        self.tabs = QTabWidget()
        detail_layout.addWidget(self.tabs, 1)
        root.addWidget(self.detail, 1)
        self.detail.hide()
        self.build_tabs()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll_log)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(15000)
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start()
        self.refresh()

    def expect_stop(self, name):
        self.expected_stops[name] = time.monotonic() + 60

    def check_status(self):
        if self.status_job:
            return
        job = Job(server_snapshot)
        self.status_job = job

        def done(ok, rows):
            self.status_job = None
            if not ok:
                return
            current = {row["name"]: bool(row.get("running")) for row in rows}
            for name, was_running in self.known_running.items():
                if was_running and name in current and not current[name]:
                    if self.expected_stops.get(name, 0) < time.monotonic():
                        self.unexpected_stop.emit(name)
                    self.expected_stops.pop(name, None)
            self.expected_stops = {name: expiry for name, expiry in self.expected_stops.items() if expiry > time.monotonic()}
            self.known_running = current

        job.signals.done.connect(done)
        self.pool.start(job)

    def button(self, label, action):
        button = QPushButton(label)
        button.setObjectName("secondary")
        button.clicked.connect(action)
        return button

    def refresh(self):
        if self.job:
            return
        self.status.setText("Checking SERVLI servers...")
        job = Job(server_snapshot)
        self.job = job

        def done(ok, rows):
            self.job = None
            if not ok:
                self.status.setText(str(rows))
                return
            self.show_servers(rows)

        job.signals.done.connect(done)
        self.pool.start(job)

    def show_servers(self, rows):
        if not self.known_running:
            self.known_running = {row["name"]: bool(row.get("running")) for row in rows}
        if self.server:
            self.server = next((row for row in rows if row.get("name") == self.server.get("name")), self.server)
        while self.cards.count() > 1:
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.status.setText(f"{len(rows)} configured · {sum(bool(row.get('running')) for row in rows)} running")
        for row in rows:
            frame = QFrame()
            frame.setObjectName("hero")
            content = QHBoxLayout(frame)
            info = QVBoxLayout()
            name = QLabel(str(row.get("name", "")))
            name.setObjectName("game")
            info.addWidget(name)
            started = row.get("startedUtc")
            uptime = ""
            if started and row.get("running"):
                try:
                    seconds = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds()))
                    uptime = f" · {seconds // 3600}h {(seconds // 60) % 60}m"
                except ValueError:
                    pass
            info.addWidget(QLabel(f"{row.get('provider')} · Minecraft {row.get('minecraftVersion')} · {row.get('memory')} · port {row.get('port')} · {'RUNNING' if row.get('running') else 'STOPPED'} · PID {row.get('pid') or '—'}{uptime}"))
            content.addLayout(info, 1)
            for label, action in (("START", "start"), ("STOP", "stop"), ("RESTART", "restart")):
                button = self.button(label, lambda checked=False, item=row, command=action: self.command([command, item["name"]], self.refresh))
                button.setEnabled((not row.get("running")) if action == "start" else bool(row.get("running")))
                content.addWidget(button)
            content.addWidget(self.button("CONSOLE", lambda checked=False, item=row: self.open_server(item, "Console")))
            content.addWidget(self.button("SETTINGS", lambda checked=False, item=row: self.open_server(item, "Properties")))
            self.cards.insertWidget(self.cards.count() - 1, frame)

    def command(self, args, after=None):
        if args and args[0] in ("stop", "restart") and len(args) > 1:
            self.expect_stop(args[1])
        self.status.setText("Running SERVLI " + " ".join(args[:2]) + "...")

        def done(ok, output):
            self.status.setText((output.strip().splitlines()[-1] if output.strip() else "Done") if ok else "SERVLI failed: " + output.strip()[-200:])
            if ok and after:
                after()

        self.run_command(args, done)

    def show_cards(self):
        self.timer.stop()
        self.detail.hide()
        self.scroll.show()
        self.refresh()

    def open_server(self, row, tab="Overview"):
        self.server = row
        self.detail_title.setText(row["name"].upper())
        self.scroll.hide()
        self.detail.show()
        self.tabs.setCurrentIndex(next((index for index in range(self.tabs.count()) if self.tabs.tabText(index) == tab), 0))
        self.overview.setText(f"{row['provider']} · Minecraft {row['minecraftVersion']} · {row.get('softwareVersion')}\nStatus: {'Running' if row.get('running') else 'Stopped'} · PID: {row.get('pid') or '—'} · RAM: {row.get('memory')} · Port: {row.get('port')}")
        self.log_cursor = ("", 0)
        self.console.clear()
        self.load_properties()
        self.load_backups()
        self.load_addons()
        self.timer.start()

    def open_named(self, name):
        job = Job(server_snapshot)

        def loaded(ok, rows):
            if not ok:
                self.status.setText("Could not open server: " + str(rows))
                return
            row = next((item for item in rows if item.get("name") == name), None)
            if row:
                self.open_server(row)
            else:
                self.status.setText("Server not found: " + name)

        job.signals.done.connect(loaded)
        self.pool.start(job)

    def build_tabs(self):
        overview = QWidget(); layout = QVBoxLayout(overview)
        self.overview = QLabel(); self.overview.setWordWrap(True); layout.addWidget(self.overview)
        layout.addWidget(self.button("OPEN SERVER FOLDER", lambda: self.open_path("")))
        layout.addStretch(); self.tabs.addTab(overview, "Overview")

        console = QWidget(); layout = QVBoxLayout(console)
        row = QHBoxLayout(); self.console_command = QLineEdit(); self.console_command.setPlaceholderText("Server command")
        self.console_command.returnPressed.connect(self.send_console)
        row.addWidget(self.console_command); row.addWidget(self.button("SEND", self.send_console)); layout.addLayout(row)
        self.console = QPlainTextEdit(); self.console.setReadOnly(True); self.console.document().setMaximumBlockCount(5000); layout.addWidget(self.console, 1)
        row = QHBoxLayout(); self.pause_scroll = QCheckBox("Pause scrolling"); row.addWidget(self.pause_scroll)
        row.addWidget(self.button("CLEAR DISPLAY", self.console.clear)); row.addStretch(); layout.addLayout(row)
        self.tabs.addTab(console, "Console")

        players = QWidget(); layout = QVBoxLayout(players)
        self.players_output = QPlainTextEdit(); self.players_output.setReadOnly(True)
        layout.addWidget(self.button("REFRESH ONLINE PLAYERS", lambda: self.send_player("list")))
        self.player_name = QLineEdit(); self.player_name.setPlaceholderText("Player name"); layout.addWidget(self.player_name)
        buttons = QHBoxLayout()
        for title, command in (("OP", "op"), ("DEOP", "deop"), ("WHITELIST ADD", "whitelist add"), ("WHITELIST REMOVE", "whitelist remove"), ("KICK", "kick"), ("BAN", "ban"), ("PARDON", "pardon")):
            buttons.addWidget(self.button(title, lambda checked=False, action=command: self.send_player(action)))
        layout.addLayout(buttons); layout.addWidget(self.players_output, 1)
        self.tabs.addTab(players, "Players")

        properties = QWidget(); layout = QVBoxLayout(properties)
        form = QFormLayout(); self.property_fields = {}
        for title, key, kind in PROPERTIES:
            field = QLineEdit(); self.property_fields[key] = field; form.addRow(title, field)
        layout.addLayout(form)
        layout.addWidget(self.button("SAVE CHANGED PROPERTIES", self.save_properties))
        layout.addWidget(QLabel("Advanced server.properties (edit values below, then save):"))
        self.raw_properties = QPlainTextEdit(); layout.addWidget(self.raw_properties, 1)
        layout.addWidget(self.button("SAVE ADVANCED VALUES", self.save_raw_properties))
        self.tabs.addTab(properties, "Properties")

        backups = QWidget(); layout = QVBoxLayout(backups)
        row = QHBoxLayout(); row.addWidget(self.button("BACKUP NOW", lambda: self.command(["backup", self.name()], self.load_backups)))
        row.addWidget(self.button("REFRESH", self.load_backups)); row.addStretch(); layout.addLayout(row)
        self.backup_choice = QComboBox(); layout.addWidget(self.backup_choice)
        row = QHBoxLayout(); row.addWidget(self.button("RESTORE", self.restore_backup)); row.addWidget(self.button("DELETE BACKUP", self.delete_backup)); row.addStretch(); layout.addLayout(row)
        schedule = QHBoxLayout(); self.schedule_mode = QComboBox(); self.schedule_mode.setEditable(True)
        self.schedule_mode.addItems(["off", "30m", "hourly", "2h", "4h", "daily", "on-stop"])
        self.keep = QSpinBox(); self.keep.setRange(1, 1000); self.keep.setValue(10)
        self.max_age = QSpinBox(); self.max_age.setRange(0, 3650); self.max_age.setSuffix(" days (0 = unlimited)")
        schedule.addWidget(QLabel("Schedule")); schedule.addWidget(self.schedule_mode)
        schedule.addWidget(QLabel("Keep")); schedule.addWidget(self.keep)
        schedule.addWidget(QLabel("Max age")); schedule.addWidget(self.max_age)
        schedule.addWidget(self.button("SAVE SCHEDULE", self.save_schedule)); layout.addLayout(schedule)
        layout.addStretch(); self.tabs.addTab(backups, "Backups")

        for kind, label in (("plugins", "Plugins"), ("mods", "Mods")):
            panel = QWidget(); layout = QVBoxLayout(panel)
            view = QPlainTextEdit(); view.setReadOnly(True); setattr(self, kind + "_list", view)
            layout.addWidget(view, 1)
            row = QHBoxLayout(); row.addWidget(self.button("INSTALL FILE", lambda checked=False, category=kind: self.install_addon(category)))
            row.addWidget(self.button("OPEN FOLDER", lambda checked=False, category=kind: self.open_path("server/" + category)))
            row.addWidget(self.button("REFRESH", self.load_addons)); row.addStretch(); layout.addLayout(row)
            self.tabs.addTab(panel, label)

        files = QWidget(); layout = QVBoxLayout(files)
        for title, folder in (("OPEN SERVER DATA", "server"), ("OPEN LOGS", "logs"), ("OPEN BACKUPS", "backups")):
            layout.addWidget(self.button(title, lambda checked=False, location=folder: self.open_path(location)))
        layout.addStretch(); self.tabs.addTab(files, "Files")

    def name(self):
        return self.server["name"] if self.server else ""

    def open_path(self, folder):
        if not self.server:
            return
        path = Path(str(self.server["data"])) / folder
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.status.setText("Folder does not exist yet: " + str(path))

    def poll_log(self):
        if not self.server or self.log_job or self.pause_scroll.isChecked():
            return
        name, previous = self.name(), self.log_cursor
        job = Job(lambda: read_console(name, previous))
        self.log_job = job

        def done(ok, result):
            self.log_job = None
            if not ok or name != self.name():
                return
            self.log_cursor, chunk = result
            if chunk:
                self.console.moveCursor(QTextCursor.MoveOperation.End)
                self.console.insertPlainText(chunk)
                self.console.ensureCursorVisible()
                for line in chunk.splitlines():
                    if "There are " in line and " players online" in line:
                        self.players_output.appendPlainText(line)

        job.signals.done.connect(done)
        self.pool.start(job)

    def send_console(self):
        value = self.console_command.text().strip()
        if value:
            self.command(["send", self.name(), value])
            self.console_command.clear()

    def send_player(self, action):
        name = self.player_name.text().strip()
        if action != "list" and not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
            self.status.setText("Enter a valid Minecraft player name.")
            return
        if action in ("kick", "ban") and QMessageBox.question(self, "Confirm moderation", f"{action.title()} {name}?") != QMessageBox.StandardButton.Yes:
            return
        self.command(["send", self.name(), action + (" " + name if name else "")])

    def load_properties(self):
        if not self.server:
            return

        def loaded(ok, output):
            if not ok:
                self.status.setText("Could not read properties: " + output[-160:])
                return
            self.raw_properties.setPlainText(output)
            self.loaded_properties = parse_properties(output)
            for key, field in self.property_fields.items():
                field.setText(self.loaded_properties.get(key, ""))

        self.run_command(["properties", self.name()], loaded)

    def _save_values(self, changed):
        if not changed:
            self.status.setText("No property changes.")
            return
        name = self.name()
        pending = list(changed.items())

        def next_value():
            if not pending:
                self.load_properties()
                return
            key, value = pending.pop(0)

            def saved(ok, output):
                if not ok:
                    self.status.setText("Could not save " + key + ": " + output[-160:])
                    return
                next_value()

            self.run_command(["properties", name, key, value], saved)

        next_value()

    def save_properties(self):
        try:
            changed = {key: validate_property(key, field.text()) for key, field in self.property_fields.items() if field.text().strip() and field.text().strip() != self.loaded_properties.get(key, "")}
        except ValueError as exc:
            self.status.setText(str(exc)); return
        self._save_values(changed)

    def save_raw_properties(self):
        new = parse_properties(self.raw_properties.toPlainText())
        if any(not re.fullmatch(r"[A-Za-z0-9._-]+", key) for key in new):
            self.status.setText("Advanced properties contain an invalid key.")
            return
        try:
            changed = {key: validate_property(key, value) for key, value in new.items() if value != self.loaded_properties.get(key, "")}
        except ValueError as exc:
            self.status.setText(str(exc)); return
        self._save_values(changed)

    def load_backups(self):
        if not self.server:
            return
        name = self.name()
        job = Job(lambda: backup_snapshot(name))

        def done(ok, rows):
            if not ok or name != self.name():
                if not ok:self.status.setText(str(rows))
                return
            self.backup_choice.clear()
            for row in rows:
                self.backup_choice.addItem(f"{row['name']} · {row.get('size', 0) / (1024 * 1024):.1f} MB", row["name"])
            schedule = self.server.get("schedule") or {}
            defaults = load_settings() if not (Path(str(self.server["data"])) / "backup-schedule.json").is_file() else {}
            self.schedule_mode.setCurrentText(str(defaults.get("server_backup_mode", schedule.get("Mode", "off"))))
            self.keep.setValue(int(defaults.get("server_backup_keep", schedule.get("Keep", 10))))
            self.max_age.setValue(int(schedule.get("MaxAgeDays", 0)))

        job.signals.done.connect(done)
        self.pool.start(job)

    def restore_backup(self):
        backup = self.backup_choice.currentData()
        if backup and QMessageBox.question(self, "Restore backup", "Stop the server and restore " + backup + "? Current data will be replaced.") == QMessageBox.StandardButton.Yes:
            self.command(["restore", self.name(), backup, "--yes"], self.load_backups)

    def delete_backup(self):
        backup = self.backup_choice.currentData()
        if backup and QMessageBox.question(self, "Delete backup", "Delete " + backup + " permanently?") == QMessageBox.StandardButton.Yes:
            self.command(["delete-backup", self.name(), backup], self.load_backups)

    def save_schedule(self):
        self.command(["schedule", self.name(), self.schedule_mode.currentText().strip(), "--keep", str(self.keep.value()), "--max-age-days", str(self.max_age.value())], self.refresh)

    def load_addons(self):
        if not self.server or self.addon_job:
            return
        root = Path(str(self.server["data"])) / "server"
        name = self.name()

        def scan():
            return {kind: [path.name for path in sorted((root / kind).glob("*.jar"))] if (root / kind).is_dir() else [] for kind in ("plugins", "mods")}

        job = Job(scan)
        self.addon_job = job

        def done(ok, results):
            self.addon_job = None
            if not ok or name != self.name():
                return
            for kind, files in results.items():
                getattr(self, kind + "_list").setPlainText("\n".join(files) or "No " + kind + " found.")

        job.signals.done.connect(done)
        self.pool.start(job)

    def install_addon(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, "Install server " + kind[:-1], "", "JAR files (*.jar)")
        if path:
            self.command(["plugin" if kind == "plugins" else "mod", "install", self.name(), path], self.load_addons)
