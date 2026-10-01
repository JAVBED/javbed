"""Small widgets shared by the launcher shell and Java Play screen."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QSize, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .artwork import cached_art


def game_icon(label: str, size: int = 28) -> QIcon:
    if label in ("Java", "Bedrock"):
        image = QPixmap(28,28)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#74c341"))
        painter.drawPolygon(QPolygon([QPoint(14,2),QPoint(26,8),QPoint(14,14),QPoint(2,8)]))
        painter.setBrush(QColor("#76593a"))
        painter.drawPolygon(QPolygon([QPoint(2,8),QPoint(14,14),QPoint(14,27),QPoint(2,21)]))
        painter.setBrush(QColor("#9b7449"))
        painter.drawPolygon(QPolygon([QPoint(14,14),QPoint(26,8),QPoint(26,21),QPoint(14,27)]))
        painter.fillRect(5,14,3,2,QColor("#5d492f"))
        painter.fillRect(18,18,3,2,QColor("#5d492f"))
        painter.fillRect(20,10,3,2,QColor("#4d9c30"))
        painter.end()
        return QIcon(image.scaled(size,size,Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.FastTransformation))
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
    path = cached_art(label if label not in ("Home", "Worlds", "Servers") else "Java")
    if not path:
        return QIcon()
    image = QPixmap(str(path))
    if image.isNull():
        return QIcon()
    scaled = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    left = max(0, (scaled.width() - size) // 2)
    top = max(0, (scaled.height() - size) // 2)
    return QIcon(scaled.copy(left, top, size, size))


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
