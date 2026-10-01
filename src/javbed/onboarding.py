"""First-run discovery dialog; no account login is required."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .instances import list_instances
from .jobs import Job
from .launcher_imports import discover


def first_run_snapshot(home_snapshot):
    installed, engines, servers, running, _, _, _, _ = home_snapshot()
    instances = list_instances()
    binary = "java.exe" if sys.platform == "win32" else "java"
    runtimes = [str(major) for major in (8, 17, 21, 25) if (Path.home() / ".mcli" / "runtimes" / f"java-{major}" / "bin" / binary).is_file()]
    imports = discover()
    return installed, engines, servers, running, instances, runtimes, imports


class OnboardingDialog(QDialog):
    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to JAVBED")
        self.resize(720, 530)
        self.action = "skip"
        self.pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        title = QLabel("WELCOME TO JAVBED")
        title.setObjectName("heroTitle")
        root.addWidget(title)
        root.addWidget(QLabel("Looking for your Minecraft games and launcher instances..."))
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlainText("Scanning...")
        root.addWidget(self.results, 1)
        actions = QHBoxLayout()
        for label, action in (("IMPORT", "import"), ("SKIP", "skip"), ("CONFIGURE LATER", "configure")):
            button = QPushButton(label)
            button.setObjectName("play" if action == "import" else "secondary")
            button.clicked.connect(lambda checked=False, selected=action: self.choose(selected))
            actions.addWidget(button)
        root.addLayout(actions)
        job = Job(snapshot)

        def done(ok, value):
            if not ok:
                self.results.setPlainText("Scan failed: " + str(value) + "\nYou can configure JAVBED later in Settings.")
                return
            installed, engines, servers, running, instances, runtimes, imports = value
            lines = ["GAMES", *("  " + item for item in installed), "", "JAVA INSTANCES", *("  " + item["name"] for item in instances), "", "JAVA RUNTIMES", *("  Java " + major for major in runtimes), "", "ENGINES", *(f"  {label}: {'ready' if path else 'not found'}" for label, path, _ in engines), "", "SERVERS", f"  {running or 0}/{servers or 0} running", "", "OTHER LAUNCHERS", *(f"  {item.launcher}: {item.name}" for item in imports)]
            self.results.setPlainText("\n".join(lines))

        job.signals.done.connect(done)
        self.pool.start(job)

    def choose(self, action):
        self.action = action
        self.accept()
