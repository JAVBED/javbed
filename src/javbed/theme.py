"""Launcher colors and widget states measured from ref.png."""

import re

from PySide6.QtGui import QColor


TOKENS = {
    "main": "#171615",
    "sidebar": "#312d2c",
    "header": "#262423",
    "navigation": "#312d2c",
    "selected": "#262423",
    "hover": "#403b39",
    "text": "#ffffff",
    "muted": "#aaa6a3",
    "divider": "#171615",
    "border": "#504b48",
    "green": "#3c8527",
    "green_hover": "#4c9b35",
    "green_pressed": "#2e6a1d",
}

STYLE = """
QWidget{background:@main@;color:@text@;font-family:'Segoe UI';font-size:12px}
QLabel{background:transparent}
QFrame#rail{background:@sidebar@;border-right:2px solid @divider@}
QFrame#account{background:@sidebar@;border-bottom:2px solid @divider@}
QFrame#account:hover{background:@hover@}
QWidget#accountText{background:transparent}
QLabel#accountAvatar{background:#53616b;border:1px solid #777;border-radius:12px;font-weight:700}
QLabel#accountName{background:transparent;font-size:14px;font-weight:650}
QLabel#accountDetail{background:transparent;font-size:11px;color:@muted@}
QLabel#accountArrow{background:transparent;font-size:18px;color:@text@}
QLabel#small{font-size:11px;color:@muted@}
QLabel#game{font-size:16px;font-weight:700}
QLabel#javaHeading{background:transparent;font-size:12px;font-weight:800}
QFrame#topbar{background:@header@;border-bottom:0}
QPushButton#tab,QToolButton#tab{background:transparent;border:0;border-bottom:3px solid transparent;padding:2px 10px;font-size:15px;font-weight:400}
QPushButton#tab:hover,QToolButton#tab:hover{background:#343130}
QPushButton#tab:checked,QToolButton#tab:checked{border-bottom:3px solid @green@;font-weight:650}
QToolButton#tab::menu-indicator{image:none;width:0}
QPushButton#nav{text-align:left;background:@navigation@;border:0;border-bottom:2px solid @divider@;padding:4px 11px;font-size:11px;font-weight:650}
QPushButton#nav:hover{background:@hover@}
QPushButton#nav:pressed{background:#252322}
QPushButton#nav:checked{background:@selected@;border-left:3px solid @text@;padding-left:8px}
QPushButton#moreNav{background:@sidebar@;border:0;border-bottom:2px solid @divider@;font-size:20px}
QPushButton#moreNav:hover{background:@hover@}
QFrame#hero{background:#242221;border:1px solid #393532}
QLabel#heroTitle{font-size:30px;font-weight:800}
QLabel#heroSub{font-size:15px;color:#d0ccca}
QFrame#playbar{background:@header@;border-top:2px solid @border@;border-bottom:2px solid @divider@}
QFrame#installationSelector{background:#302c2b;border:1px solid @green@}
QFrame#installationSelector:hover{background:#3a3532}
QLabel#installationIcon{background:transparent}
QLabel#installationTitle{background:transparent;font-size:11px;font-weight:750}
QComboBox#installationVersion{background:transparent;border:0;padding:0 18px 0 0;font-size:11px;color:@text@}
QComboBox#installationVersion::drop-down{border:0;width:17px}
QComboBox#installationVersion::down-arrow{image:none}
QPushButton#play{background:@green@;border:3px solid #151515;padding:10px 30px;font-family:Consolas;font-size:22px;font-weight:900}
QPushButton#play:hover{background:@green_hover@}
QPushButton#play:pressed{background:@green_pressed@}
QPushButton#play:disabled{background:#56634e;color:#b4b4b4}
QPushButton#secondary{background:#373331;border:1px solid #635d5a;padding:8px 12px;font-weight:650}
QPushButton#secondary:hover{background:#45403d}
QPushButton#secondary:pressed{background:#292624}
QFrame#newsSurface{background:@main@;border-top:2px solid @divider@}
QPushButton#newsCard{background:#292625;border:2px solid #aaa4a0;padding:0}
QPushButton#newsCard:hover{border-color:@text@}
QPushButton#newsCard:pressed{border-color:@green@}
QComboBox,QLineEdit{background:#302c2b;border:1px solid #625c59;padding:8px}
QComboBox:hover,QLineEdit:hover{border-color:#8a827e}
QComboBox:focus,QLineEdit:focus{border-color:@green@}
QPlainTextEdit{background:#1b1a19;border:1px solid #393532;font-family:Consolas,monospace}
QProgressBar{background:#302c2b;border:1px solid #625c59;text-align:center;min-height:16px}
QProgressBar::chunk{background:@green@}
QMenu{background:#302c2b;border:1px solid #625c59;padding:4px}
QMenu::item{padding:7px 20px}
QMenu::item:selected{background:#504941}
QLabel#launcherToast{background:#312d2c;border:1px solid #77716d;padding:9px 13px;color:@text@}
"""


def stylesheet(settings=None):
    settings = settings or {}
    accent = str(settings.get("accent_color") or TOKENS["green"])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = TOKENS["green"]
    colors = dict(TOKENS)
    colors["green"] = accent
    colors["green_hover"] = QColor(accent).lighter(115).name()
    colors["green_pressed"] = QColor(accent).darker(125).name()
    style = STYLE
    for key, value in colors.items():
        style = style.replace("@" + key + "@", value)
    if settings.get("compact_navigation"):
        style = style.replace("padding:4px 11px;font-size:11px", "padding:8px 11px;font-size:12px")
    return style
