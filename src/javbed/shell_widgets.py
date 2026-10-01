"""Small widgets and native-size game icons for the launcher shell."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QSize, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

def game_icon(label: str, size: int = 28) -> QIcon:
    if label in ("Java", "Bedrock"):
        image = QPixmap(28, 28)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        grass = label == "Java"
        painter.setBrush(QColor("#74c341" if grass else "#8b9296"))
        painter.drawPolygon(QPolygon([QPoint(14,2),QPoint(26,8),QPoint(14,14),QPoint(2,8)]))
        painter.setBrush(QColor("#76593a" if grass else "#474c51"))
        painter.drawPolygon(QPolygon([QPoint(2,8),QPoint(14,14),QPoint(14,27),QPoint(2,21)]))
        painter.setBrush(QColor("#9b7449" if grass else "#646b70"))
        painter.drawPolygon(QPolygon([QPoint(14,14),QPoint(26,8),QPoint(26,21),QPoint(14,27)]))
        painter.fillRect(5,14,3,2,QColor("#5d492f" if grass else "#30363a"))
        painter.fillRect(18,18,3,2,QColor("#5d492f" if grass else "#353b40"))
        painter.fillRect(20,10,3,2,QColor("#4d9c30" if grass else "#c2c7c8"))
        painter.end()
        return QIcon(image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.FastTransformation))
    if label in ("EDU", "LCE", "Dungeons", "Dungeons 2", "Legends", "Story Mode", "Story Mode 2"):
        image = QPixmap(28, 28)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        backgrounds = {
            "EDU": "#426d9d", "LCE": "#765b3d", "Dungeons": "#874b36",
            "Dungeons 2": "#4f457a", "Legends": "#397e80",
            "Story Mode": "#7b5436", "Story Mode 2": "#7b5436",
        }
        painter.setBrush(QColor(backgrounds[label]))
        painter.drawRect(1, 1, 26, 26)
        painter.setBrush(QColor("#ffffff"))
        if label == "EDU":
            # Open lesson book with a bright central spine.
            painter.setBrush(QColor("#d6ebef"))
            painter.drawPolygon(QPolygon([QPoint(4,6),QPoint(12,8),QPoint(13,22),QPoint(4,20)]))
            painter.drawPolygon(QPolygon([QPoint(24,6),QPoint(16,8),QPoint(15,22),QPoint(24,20)]))
            painter.fillRect(13,7,2,16,QColor("#f7ce70"))
            painter.fillRect(7,11,4,1,QColor("#7babbc"))
            painter.fillRect(17,11,4,1,QColor("#7babbc"))
        elif label == "LCE":
            # Console gamepad, broad enough to read at native sidebar size.
            painter.setBrush(QColor("#e6d3a8"))
            painter.drawPolygon(QPolygon([QPoint(4,11),QPoint(8,8),QPoint(20,8),QPoint(24,11),QPoint(26,20),QPoint(22,22),QPoint(18,18),QPoint(10,18),QPoint(6,22),QPoint(2,20)]))
            painter.fillRect(8,11,2,6,QColor("#55462e"))
            painter.fillRect(6,13,6,2,QColor("#55462e"))
            painter.fillRect(19,12,2,2,QColor("#4b9e60"))
            painter.fillRect(22,15,2,2,QColor("#b65c43"))
        elif label in ("Dungeons", "Dungeons 2"):
            # One dungeon blade for the first game, crossed blades for the second.
            painter.setPen(QPen(QColor("#f1d5a7"),3))
            painter.drawLine(7,6,19,20)
            painter.setPen(QPen(QColor("#2b292a"),3))
            painter.drawLine(17,18,22,23)
            painter.setPen(QPen(QColor("#f6bf63"),2))
            painter.drawLine(15,21,20,17)
            if label == "Dungeons 2":
                painter.setPen(QPen(QColor("#c4dcf2"),3))
                painter.drawLine(21,6,9,20)
                painter.setPen(QPen(QColor("#2b292a"),3))
                painter.drawLine(11,18,6,23)
        elif label == "Legends":
            # Banner and staff echo the game's rally motif.
            painter.fillRect(7,4,2,21,QColor("#f3d686"))
            painter.setBrush(QColor("#efcf78"))
            painter.drawPolygon(QPolygon([QPoint(9,5),QPoint(23,5),QPoint(21,10),QPoint(23,16),QPoint(9,16)]))
            painter.fillRect(14,8,4,5,QColor("#397e80"))
            painter.fillRect(5,24,8,2,QColor("#d6b86f"))
        else:
            # Story Mode's book and clasp.
            painter.fillRect(5,5,18,19,QColor("#e6c48b"))
            painter.fillRect(5,5,4,19,QColor("#986039"))
            painter.fillRect(10,8,10,3,QColor("#a26640"))
            painter.fillRect(10,14,10,2,QColor("#a26640"))
            painter.fillRect(17,19,6,3,QColor("#e8a94d"))
        painter.end()
        return QIcon(image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.FastTransformation))
    if label == "Home":
        return game_icon("Java", size)
    if label in ("Updates", "Settings", "Servers", "Worlds"):
        image = QPixmap(size, size)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setPen(QPen(QColor("#d8d5d3"), 2))
        if label == "Settings":
            for y, knob in ((6,8),(14,19),(22,12)):
                painter.drawLine(2,y,size-3,y)
                painter.fillRect(knob-2,y-3,5,7,QColor("#d8d5d3"))
        elif label == "Updates":
            painter.drawRect(3,3,size-7,size-7)
            painter.drawRect(6,7,6,6)
            for y in (8,12,17,21):painter.drawLine(15 if y<17 else 6,y,size-7,y)
        elif label == "Servers":
            for y in (4,12,20):
                painter.drawRect(3,y,size-7,6)
                painter.fillRect(6,y+2,2,2,QColor("#7bbb54"))
        else:
            painter.fillRect(2,4,size-4,10,QColor("#78ad58"))
            painter.fillRect(2,14,size-4,10,QColor("#7c6246"))
            painter.drawRect(2,4,size-5,20)
        painter.end()
        return QIcon(image)
    return QIcon()


class AccountHeader(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("account")
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)
        self.avatar = QLabel()
        self.avatar.setObjectName("accountAvatar")
        self.avatar.setFixedSize(25, 25)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.avatar)
        text_box = QWidget(self)
        text_box.setObjectName("accountText")
        text_box.setFixedHeight(38)
        text_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text = QVBoxLayout(text_box)
        text.setContentsMargins(0,0,0,0)
        text.setSpacing(0)
        self.name = QLabel("No Java account")
        self.name.setObjectName("accountName")
        self.name.setFixedHeight(21)
        self.detail = QLabel("Add an account")
        self.detail.setObjectName("accountDetail")
        self.detail.setFixedHeight(17)
        text.addWidget(self.name)
        text.addWidget(self.detail)
        row.addWidget(text_box, 1)
        arrow = QLabel("⌄")
        arrow.setObjectName("accountArrow")
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(arrow)
        self.set_profile(None, "")

    def set_profile(self, account, avatar):
        self.name.setText(account["username"] if account else "No Java account")
        self.detail.setText((account.get("alias") or "Microsoft account") if account else "Add an account")
        image = QPixmap(avatar) if avatar else QPixmap()
        self.avatar.setPixmap(image.scaled(25, 25, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation) if not image.isNull() else QPixmap())
        if image.isNull():
            self.avatar.setText("?")
        else:
            self.avatar.setText("")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StatusLabel(QLabel):
    text_changed = Signal(str)

    def setText(self, value):
        super().setText(value)
        self.text_changed.emit(value)


class InstallationFrame(QFrame):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and hasattr(self, "version"):
            self.version.showPopup()
        super().mousePressEvent(event)


def sidebar_button(label: str, icon_label: str = "") -> QPushButton:
    button = QPushButton(label)
    button.setObjectName("nav")
    button.setCheckable(True)
    button.setFixedHeight(56)
    button.setIcon(game_icon(icon_label or label))
    button.setIconSize(QSize(28, 28))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
