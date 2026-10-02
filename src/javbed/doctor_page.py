"""Graphical results for JAVBED Doctor."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .diagnostics import Check, scan
from .engines import ENGINES
from .jobs import Job


class DoctorPage(QWidget):
    def __init__(self, activity=None, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.pool = QThreadPool.globalInstance()
        self.job = None
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        header = QHBoxLayout()
        title = QLabel("JAVBED DOCTOR")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch()
        refresh = QPushButton("RUN CHECKS")
        refresh.setObjectName("play")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        root.addLayout(header)
        self.status = QLabel("Ready")
        root.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.rows = QVBoxLayout(container)
        self.rows.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def refresh(self):
        if self.job:
            return
        self.status.setText("Running diagnostics...")
        manager = getattr(self.window(), "plugin_manager", None)
        extensions = manager.contributions.all("diagnostic") if manager else ()

        def run_checks():
            checks = scan()
            if manager:
                from .plugins.api import DiagnosticResult
                for extension in extensions:
                    result = manager.contributions.invoke(extension)
                    if result is None:
                        continue
                    if not isinstance(result, DiagnosticResult) or result.state not in ("healthy", "warning", "failed"):
                        manager._fail(extension.owner, "diagnostic result", TypeError("Expected DiagnosticResult with a valid state"))
                        continue
                    checks.append(Check(extension.title + ": " + result.name, result.state, result.detail))
            return checks

        job = Job(run_checks)
        self.job = job

        def done(ok, checks):
            self.job = None
            if not ok:
                self.status.setText("Doctor failed: " + str(checks))
                return
            while self.rows.count() > 1:
                item = self.rows.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for check in checks:
                frame = QFrame()
                frame.setObjectName("hero")
                layout = QHBoxLayout(frame)
                symbol = {"healthy": "✓", "warning": "⚠", "failed": "✕"}[check.state]
                text = QLabel(f"{symbol}  {check.name} — {check.detail}")
                text.setTextFormat(Qt.TextFormat.PlainText)
                text.setWordWrap(True)
                layout.addWidget(text, 1)
                if check.repair_engine:
                    button = QPushButton("INSTALL ENGINE")
                    button.setObjectName("secondary")
                    button.clicked.connect(lambda checked=False, name=check.repair_engine: self.repair(name))
                    layout.addWidget(button)
                self.rows.insertWidget(self.rows.count() - 1, frame)
            self.status.setText(f"{sum(item.state == 'healthy' for item in checks)}/{len(checks)} checks healthy")

        job.signals.done.connect(done)
        self.pool.start(job)

    def repair(self, name):
        if self.job:
            return
        self.status.setText("Installing " + name + " engine...")
        activity_id = self.activity.begin(name + " engine", "GitHub release", "Installing") if self.activity else None
        job = Job(lambda: ENGINES[name].install_latest())
        self.job = job

        def done(ok, result):
            self.job = None
            if activity_id:
                self.activity.finish(activity_id, ok, "Installed " + str(result) if ok else str(result))
            self.status.setText("Installed " + name if ok else "Install failed: " + str(result))
            if ok:
                self.refresh()

        job.signals.done.connect(done)
        self.pool.start(job)
