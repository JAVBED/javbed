"""Graphical world library. Disk scans and archive operations run off the UI thread."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .jobs import Job
from .worlds import (available_roots, backup_world, discover_worlds, duplicate_world,
                     export_world, import_world, restore_world, trash_world)


class WorldPage(QWidget):
    def __init__(self, play, parent=None):
        super().__init__(parent)
        self.play = play
        self.pool = QThreadPool.globalInstance()
        self.job = None
        root = QVBoxLayout(self)
        root.setContentsMargins(35, 25, 35, 25)
        header = QHBoxLayout()
        title = QLabel("WORLD MANAGER")
        title.setObjectName("heroTitle")
        header.addWidget(title)
        header.addStretch()
        for label, action in (("IMPORT WORLD ZIP", self.import_zip), ("REFRESH", self.refresh)):
            button = QPushButton(label)
            button.setObjectName("secondary")
            button.clicked.connect(action)
            header.addWidget(button)
        root.addLayout(header)
        self.status = QLabel("Scanning worlds...")
        root.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.cards = QVBoxLayout(self.container)
        self.cards.addStretch()
        scroll.setWidget(self.container)
        root.addWidget(scroll, 1)
        self.refresh()

    def work(self, label, function, after=None):
        if self.job:
            self.status.setText("Another world operation is running.")
            return
        self.status.setText(label)
        job = Job(function)
        self.job = job

        def done(ok, result):
            self.job = None
            self.status.setText(("Done: " if ok else "Failed: ") + str(result)[:200])
            if ok and after:
                after(result)

        job.signals.done.connect(done)
        self.pool.start(job)

    def refresh(self):
        self.work("Scanning worlds...", discover_worlds, self.show_worlds)

    def show_worlds(self, rows):
        while self.cards.count() > 1:
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.status.setText(f"{len(rows)} world(s) found")
        for world in rows:
            card = QFrame()
            card.setObjectName("hero")
            layout = QVBoxLayout(card)
            top = QHBoxLayout()
            icon = QLabel()
            icon.setFixedSize(48, 48)
            if world.icon:
                icon.setPixmap(QPixmap(str(world.icon)).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                icon.setText("◼")
            top.addWidget(icon)
            details = QVBoxLayout()
            title = QLabel(world.name)
            title.setObjectName("game")
            details.addWidget(title)
            stamp = datetime.fromtimestamp(world.last_played).strftime("%Y-%m-%d %H:%M")
            details.addWidget(QLabel(f"{world.edition} {world.instance} · {world.version or 'Version unknown'} · {world.size / (1024 * 1024):.1f} MB · {stamp}"))
            top.addLayout(details, 1)
            play = QPushButton("PLAY")
            play.setObjectName("play")
            play.clicked.connect(lambda checked=False, item=world: self.play(item))
            top.addWidget(play)
            layout.addLayout(top)
            actions = QHBoxLayout()
            for label, callback in (
                ("BACKUP", lambda w=world: self.operate("Backing up world...", lambda: backup_world(w))),
                ("RESTORE", lambda w=world: self.restore(w)),
                ("DUPLICATE", lambda w=world: self.operate("Duplicating world...", lambda: duplicate_world(w))),
                ("EXPORT", lambda w=world: self.export(w)),
                ("OPEN FOLDER", lambda w=world: QDesktopServices.openUrl(QUrl.fromLocalFile(str(w.path)))),
                ("DELETE", lambda w=world: self.delete(w)),
            ):
                button = QPushButton(label)
                button.setObjectName("secondary")
                button.clicked.connect(lambda checked=False, fn=callback: fn())
                actions.addWidget(button)
            actions.addStretch()
            layout.addLayout(actions)
            self.cards.insertWidget(self.cards.count() - 1, card)

    def operate(self, label, function):
        self.work(label, function, lambda _: self.refresh())

    def import_zip(self, path=""):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Import Minecraft world", "", "ZIP archives (*.zip)")
        if not path:
            return
        roots = [(edition, instance, root) for edition, instance, root in available_roots()]
        options = [f"{edition} {instance or 'Vanilla'} — {root}" for edition, instance, root in roots]
        from PySide6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(self, "Import world", "Destination", options, 0, False)
        if ok:
            root = roots[options.index(choice)][2]
            self.operate("Importing world...", lambda: import_world(Path(path), root))

    def export(self, world):
        path, _ = QFileDialog.getSaveFileName(self, "Export world", world.name + ".zip", "ZIP archives (*.zip)")
        if path:
            self.operate("Exporting world...", lambda: export_world(world, Path(path)))

    def restore(self, world):
        path, _ = QFileDialog.getOpenFileName(self, "Restore world backup", "", "ZIP archives (*.zip)")
        if path and QMessageBox.question(self, "Restore world", "Restore this backup? The current world will be backed up first.") == QMessageBox.StandardButton.Yes:
            self.operate("Restoring world...", lambda: restore_world(world, Path(path)))

    def delete(self, world):
        if QMessageBox.question(self, "Delete world", f"Move {world.name} to JAVBED's recoverable trash?") == QMessageBox.StandardButton.Yes:
            self.operate("Moving world to trash...", lambda: trash_world(world))
