"""Quiet, deduplicated launcher notifications."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal


class NotificationCenter(QObject):
    posted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_seen: dict[str, float] = {}

    def post(self, key: str, message: str, cooldown: int = 300) -> bool:
        now = time.monotonic()
        if now - self.last_seen.get(key, -10**12) < cooldown:
            return False
        self.last_seen[key] = now
        self.posted.emit(message)
        return True
