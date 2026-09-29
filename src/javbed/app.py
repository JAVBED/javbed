from __future__ import annotations
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from .engines import ENGINES

STYLE = """
QWidget { background: #0b0e14; color: #eef2f7; font-family: "Segoe UI"; }
QFrame#sidebar { background: #10151d; border-right: 1px solid #202936; }
QLabel#brand { font-size: 25px; font-weight: 800; letter-spacing: 2px; }
QLabel#eyebrow { color: #7f8da3; font-size: 11px; font-weight: 700; }
QLabel#title { font-size: 32px; font-weight: 800; }
QLabel#subtitle { color: #9ba8b8; font-size: 14px; }
QPushButton#nav { text-align: left; padding: 12px 16px; border: 0; border-radius: 9px; font-size: 14px; font-weight: 600; }
QPushButton#nav:hover { background: #171e29; }
QPushButton#nav:checked { background: #202a38; color: white; }
QFrame#card { background: #111721; border: 1px solid #222d3b; border-radius: 16px; }
QPushButton#launch { background: #f0f3f7; color: #10141a; border: 0; border-radius: 9px; padding: 11px 18px; font-weight: 800; }
QPushButton#launch:hover { background: white; }
QLabel#status { color: #8fa0b5; padding-top: 8px; }
"""

DESCRIPTIONS = {
    "Java": "Install, manage and launch Minecraft Java Edition.",
    "Bedrock": "Manage Minecraft Bedrock Edition from one clean desktop home.",
    "EDU": "Launch and manage Minecraft Education Edition.",
    "LCE": "Tools for Minecraft Legacy Console Edition.",
    "Servers": "Create, configure and run Minecraft servers.",
}

class EditionPage(QWidget):
    def __init__(self, label: str):
        super().__init__()
        self.engine = ENGINES[label]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(44, 38, 44, 44)
        layout.setSpacing(10)
        eyebrow = QLabel("JAVBED"); eyebrow.setObjectName("eyebrow")
        title = QLabel(label); title.setObjectName("title")
        subtitle = QLabel(DESCRIPTIONS[label]); subtitle.setObjectName("subtitle"); subtitle.setWordWrap(True)
        card = QFrame(); card.setObjectName("card"); card.setMaximumWidth(720)
        box = QVBoxLayout(card); box.setContentsMargins(28, 26, 28, 26); box.setSpacing(14)
        heading = QLabel("Server control center" if label == "Servers" else f"{label} Edition")
        heading.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        detail = QLabel(f"Powered by the {self.engine.project} engine."); detail.setObjectName("subtitle")
        launch = QPushButton("Open " + label); launch.setObjectName("launch"); launch.setCursor(Qt.CursorShape.PointingHandCursor); launch.setMaximumWidth(180)
        launch.clicked.connect(self.launch)
        self.status = QLabel(""); self.status.setObjectName("status"); self.status.setWordWrap(True)
        for widget in (heading, detail, launch, self.status): box.addWidget(widget)
        for widget in (eyebrow, title, subtitle): layout.addWidget(widget)
        layout.addSpacing(24); layout.addWidget(card); layout.addStretch()

    def launch(self):
        ok, message = self.engine.launch()
        self.status.setText(("✓ " if ok else "• ") + message)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JAVBED")
        self.resize(1120, 720); self.setMinimumSize(900, 580)
        root = QWidget(); shell = QHBoxLayout(root); shell.setContentsMargins(0, 0, 0, 0); shell.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar); side.setContentsMargins(22, 28, 22, 24); side.setSpacing(7)
        brand = QLabel("JAVBED"); brand.setObjectName("brand"); side.addWidget(brand); side.addSpacing(26)
        self.stack = QStackedWidget(); self.buttons = []
        for index, label in enumerate(("Java", "Bedrock", "EDU", "LCE", "Servers")):
            button = QPushButton(label); button.setObjectName("nav"); button.setCheckable(True); button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=index: self.select(i))
            side.addWidget(button); self.buttons.append(button); self.stack.addWidget(EditionPage(label))
        side.addStretch()
        footer = QLabel("One launcher. Every edition."); footer.setObjectName("eyebrow"); footer.setWordWrap(True); side.addWidget(footer)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        shell.addWidget(sidebar); shell.addWidget(self.stack, 1); self.setCentralWidget(root); self.select(0)

    def select(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.buttons): button.setChecked(i == index)

def main():
    app = QApplication(sys.argv); app.setApplicationName("JAVBED"); app.setStyleSheet(STYLE)
    window = MainWindow(); window.show()
    raise SystemExit(app.exec())

if __name__ == "__main__": main()
