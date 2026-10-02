"""Ctrl+K command palette for real launcher actions."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout

from .content_registry import load as tracked_content
from .instances import list_instances
from .jobs import Job
from .servers import server_snapshot


class CommandPalette(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Search JAVBED")
        self.resize(620, 470)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("SEARCH GAMES, INSTANCES, SERVERS & COMMANDS"))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Type a game, instance, server, mod, or command...")
        self.query.textChanged.connect(self.refresh)
        root.addWidget(self.query)
        self.results = QListWidget()
        self.results.itemActivated.connect(lambda _: self.run_selected())
        root.addWidget(self.results, 1)
        self.actions = []
        self.base_actions = []
        self.populate()
        self.refresh()
        QTimer.singleShot(0, self.query.setFocus)

    def add(self, label, callback, keywords=""):
        self.base_actions.append((label, callback, keywords))

    def populate(self):
        for name in ("Home", "Java", "Bedrock", "EDU", "LCE", "Dungeons", "Dungeons 2", "Legends", "Story Mode", "Worlds", "Servers", "Updates", "Activity", "Doctor", "Settings", "Plugins"):
            self.add("Open " + name, lambda target=name: self.window.select_name(target))
        for command in self.window.plugin_manager.commands.all():
            self.add(command.title + (" — " + command.description if command.description else ""), lambda identifier=command.id: self.window.plugin_manager.commands.invoke(identifier), " ".join(command.keywords))
        for item in list_instances():
            name = str(item["name"])
            self.add("Launch " + name, lambda target=name: self.window.java_page.run(["instance", "launch", target]))
            self.add("Open " + name + " mods", lambda target=name: self.open_instance_mods(target))
            self.add("Open " + name + " folder", lambda path=str(item["path"]): QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        seen = set()
        for item in tracked_content():
            name = str(item.get("project_name") or "")
            if name and name not in seen:
                seen.add(name)
                self.add("Search Modrinth for " + name, lambda query=name: self.search_mods(query))
        job = Job(server_snapshot)

        def servers_loaded(ok, rows):
            if not ok:
                return
            for item in rows:
                name = str(item["name"])
                self.add("Open server " + name, lambda target=name: self.open_server(target))
                self.add(("Stop " if item.get("running") else "Start ") + "server " + name, lambda target=name, command="stop" if item.get("running") else "start": self.window.server_page.run([command, target]))
            self.refresh()

        job.signals.done.connect(servers_loaded)
        QThreadPool.globalInstance().start(job)

    def open_instance_mods(self, name):
        self.window.select_name("Java")
        self.window.java_page.switch_view("mods")
        browser = self.window.java_page.mods_panel
        browser.instance.setCurrentText(name)
        browser.switch_view(True)

    def search_mods(self, query):
        self.window.select_name("Java")
        self.window.java_page.switch_view("mods")
        browser = self.window.java_page.mods_panel
        browser.provider.setCurrentText("Modrinth")
        browser.query.setText(query)
        browser.search()

    def search_packs(self, query):
        self.window.select_name("Java")
        self.window.java_page.switch_view("modpacks")
        browser = self.window.java_page.modpacks_panel
        browser.query.setText(query)
        browser.search()

    def open_server(self, name):
        self.window.select_name("Servers")
        self.window.server_page.switch_view("dashboard")
        self.window.server_page.server_dashboard.open_named(name)

    def refresh(self):
        query = self.query.text().strip()
        lowered = query.lower()
        self.actions = [(label, action) for label, action, keywords in self.base_actions if lowered in (label + " " + keywords).lower()]
        if query:
            self.actions.insert(0, ("Search Modrinth for " + query, lambda value=query: self.search_mods(value)))
            self.actions.insert(1, ("Search modpacks for " + query, lambda value=query: self.search_packs(value)))
        self.results.clear()
        for label, _ in self.actions[:80]:
            self.results.addItem(label)
        if self.results.count():
            self.results.setCurrentRow(0)

    def run_selected(self):
        index = self.results.currentRow()
        if 0 <= index < min(80, len(self.actions)):
            action = self.actions[index][1]
            self.accept()
            QTimer.singleShot(0, action)

    def keyPressEvent(self, event):
        if event.key() in (16777220, 16777221):  # Return / Enter
            self.run_selected()
            return
        super().keyPressEvent(event)
