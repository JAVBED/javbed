"""Graphical results for JAVBED Doctor."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .diagnostics import scan
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
        job = Job(scan)
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
