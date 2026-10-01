"""JAVBED's Minecraft Launcher inspired desktop theme."""

STYLE = """
QWidget {
    background: #e9e9e9;
    color: #202020;
    font-family: 'Segoe UI';
    font-size: 12px;
}
QFrame#rail { background: #202020; border-right: 1px solid #111; }
QFrame#rail QLabel { background: transparent; color: #f1f1f1; }
QFrame#account { background: #303030; border-bottom: 1px solid #111; }
QLabel#logo { font-size: 23px; font-weight: 900; letter-spacing: 2px; }
QLabel#railSection { color: #a9a9a9; font-size: 10px; font-weight: 800; padding: 12px 12px 4px; }
QLabel#small { color: #5d5d5d; font-size: 11px; }
QLabel#game { font-size: 17px; font-weight: 800; }
QLabel#heroTitle { font-size: 31px; font-weight: 900; }
QLabel#heroSub { font-size: 15px; color: #444; }
QFrame#topbar { background: #f8f8f8; border-bottom: 1px solid #c8c8c8; }
QFrame#playbar { background: #dadada; border-top: 1px solid #b9b9b9; border-bottom: 1px solid #b9b9b9; }
QFrame#hero { background: #f7f7f7; border: 1px solid #bebebe; }
QPushButton#nav {
    background: #262626; color: #e9e9e9; border: 0;
    text-align: left; padding: 9px 14px; font-size: 12px; font-weight: 700;
}
QPushButton#nav:hover { background: #383838; }
QPushButton#nav:checked { background: #454545; border-left: 4px solid #77b334; padding-left: 10px; color: white; }
QPushButton#tab { background: transparent; border: 0; padding: 13px 12px; font-size: 13px; font-weight: 700; }
QPushButton#tab:checked { border-bottom: 4px solid #68a52f; }
QPushButton#play {
    background: #3b8526; color: white; border: 2px solid #1f4e18;
    border-bottom: 5px solid #1f4e18; padding: 10px 28px;
    font-size: 17px; font-weight: 900; min-height: 25px;
}
QPushButton#play:hover { background: #4c9c34; }
QPushButton#play:disabled { background: #8eaa80; border-color: #687d5f; color: #dedede; }
QPushButton#secondary {
    background: #efefef; color: #222; border: 1px solid #8e8e8e;
    border-bottom: 3px solid #777; padding: 8px 12px; font-weight: 800;
}
QPushButton#secondary:hover { background: #fff; }
QPushButton#secondary:disabled { color: #888; background: #e1e1e1; }
QComboBox, QLineEdit, QSpinBox {
    background: #fff; color: #222; border: 1px solid #929292; padding: 7px;
    selection-background-color: #4a8a2d;
}
QPlainTextEdit { background: #fff; color: #222; border: 1px solid #bcbcbc; font-family: Consolas, monospace; }
QProgressBar { background: #c9c9c9; color: #111; border: 1px solid #888; text-align: center; min-height: 16px; }
QProgressBar::chunk { background: #63a52f; }
"""
