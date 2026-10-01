"""The original dark JAVBED desktop theme."""

import re

from PySide6.QtGui import QColor

STYLE = """
QWidget{background:#211f1e;color:white;font-family:'Segoe UI'}
QFrame#rail{background:#2b2928;border-right:1px solid #111}
QFrame#account{background:#222120;border-bottom:1px solid #111}
QLabel#logo{font-size:17px;font-weight:800}
QLabel#small{font-size:11px;color:#bbb}
QLabel#game{font-size:16px;font-weight:900}
QFrame#topbar{background:#242221;border-bottom:1px solid #111}
QPushButton#tab{background:transparent;border:0;padding:13px 10px;font-size:15px}
QPushButton#tab:checked{border-bottom:3px solid #54a82f;font-weight:700}
QPushButton#nav{text-align:left;background:#353231;border:1px solid #191817;padding:15px 13px;font-size:13px;font-weight:800}
QPushButton#nav:hover{background:#413d3b}
QPushButton#nav:checked{background:#4a4644;border-left:4px solid white}
QFrame#hero{background:#171615;border:1px solid #111}
QLabel#heroTitle{font-size:34px;font-weight:900}
QLabel#heroSub{font-size:15px;color:#ddd}
QFrame#playbar{background:#292725;border-top:1px solid #111;border-bottom:1px solid #111}
QPushButton#play{background:#3c8527;border:3px solid #171717;padding:12px 65px;font-size:19px;font-weight:900}
QPushButton#play:hover{background:#4c9b35}
QPushButton#secondary{background:#353331;border:1px solid #666;padding:10px 14px;font-weight:700}
QComboBox,QLineEdit{background:#262422;border:1px solid #666;padding:9px}
QPlainTextEdit{background:#121212;border:1px solid #333;font-family:Consolas,monospace}
QProgressBar{background:#262422;border:1px solid #666;text-align:center;min-height:16px}
QProgressBar::chunk{background:#54a82f}
"""


def stylesheet(settings=None):
    settings = settings or {}
    accent = str(settings.get("accent_color") or "#3c8527")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = "#3c8527"
    light = QColor(accent).lighter(115).name()
    style = STYLE.replace("#3c8527", accent).replace("#4c9b35", light).replace("#54a82f", light)
    if settings.get("compact_navigation"):
        style = style.replace("padding:15px 13px;font-size:13px", "padding:8px 11px;font-size:12px")
    return style
