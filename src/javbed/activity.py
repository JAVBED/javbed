"""In-memory activity registry with honest progress reporting."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


@dataclass
class Activity:
    id: str
    item: str
    source: str
    stage: str
    received: int | None = None
    total: int | None = None
    speed: float | None = None
    state: str = "running"
    cancel: object = None
    updated_at: float = field(default_factory=time.monotonic)
    previous_bytes: int = 0


class ActivityManager(QObject):
    changed = Signal()
    finished = Signal(str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: dict[str, Activity] = {}

    def begin(self, item: str, source: str, stage: str, cancel=None) -> str:
        identifier = uuid.uuid4().hex
        self.items[identifier] = Activity(identifier, item, source, stage, cancel=cancel)
        self.changed.emit()
        return identifier

    def progress(self, identifier: str, received: int | None = None, total: int | None = None, stage: str | None = None) -> None:
        entry = self.items.get(identifier)
        if not entry or entry.state != "running":
            return
        now = time.monotonic()
        if received is not None:
            if received < entry.previous_bytes:
                entry.previous_bytes = received
                entry.speed = None
                entry.updated_at = now
            elapsed = now - entry.updated_at
            if elapsed > 0.25 and received >= entry.previous_bytes:
                entry.speed = (received - entry.previous_bytes) / elapsed
                entry.previous_bytes = received
                entry.updated_at = now
            entry.received = received
        if total is not None:
            entry.total = total if total > 0 else None
        if stage:
            entry.stage = stage
        self.changed.emit()

    def finish(self, identifier: str, success: bool, message: str = "") -> None:
        entry = self.items.get(identifier)
        if entry:
            entry.state = "completed" if success else "failed"
            entry.stage = message or ("Completed" if success else "Failed")
            entry.cancel = None
            self.changed.emit()
            self.finished.emit(entry.item, success, entry.stage)


class ActivityPage(QWidget):
    def __init__(self, manager: ActivityManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        title = QLabel("DOWNLOADS & ACTIVITY")
        title.setObjectName("heroTitle")
        root.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.rows = QVBoxLayout(container)
        self.rows.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)
        manager.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.manager.items:
            self.rows.insertWidget(0, QLabel("No activity yet."))
            return
        for entry in reversed(list(self.manager.items.values())):
            frame = QFrame()
            frame.setObjectName("hero")
            layout = QHBoxLayout(frame)
            description = QVBoxLayout()
            name = QLabel(entry.item)
            name.setObjectName("game")
            description.addWidget(name)
            description.addWidget(QLabel(entry.source + " · " + entry.stage + " · " + entry.state))
            if entry.received is not None:
                amount = f"{entry.received / (1024 * 1024):.1f} MB"
                if entry.total:
                    amount += f" / {entry.total / (1024 * 1024):.1f} MB ({entry.received * 100 // entry.total}%)"
                if entry.speed is not None:
                    amount += f" · {entry.speed / (1024 * 1024):.1f} MB/s"
                description.addWidget(QLabel(amount))
            layout.addLayout(description, 1)
            if entry.state == "running" and entry.cancel:
                button = QPushButton("CANCEL")
                button.setObjectName("secondary")
                button.clicked.connect(lambda checked=False, action=entry.cancel: action())
                layout.addWidget(button)
            self.rows.insertWidget(self.rows.count() - 1, frame)
