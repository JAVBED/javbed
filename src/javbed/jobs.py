"""Small QRunnable wrapper for blocking backend work."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    done = Signal(bool, object)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            ok, result = True, self.fn()
        except Exception as exc:
            ok, result = False, str(exc)
        try:
            self.signals.done.emit(ok, result)
        except RuntimeError:
            pass  # The window may have closed before the job finished.
