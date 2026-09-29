from __future__ import annotations
import re
import sys
from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from .engines import ENGINES

STYLE = """QWidget{background:#111;color:#f5f5f5;font-family:'Segoe UI'} QFrame#rail{background:#171717;border-right:1px solid #303030} QLabel#logo{font-size:27px;font-weight:900;letter-spacing:2px} QLabel#game{font-size:38px;font-weight:900} QLabel#muted{color:#aaa;font-size:13px} QLabel#heroText{font-size:16px;font-weight:600} QFrame#hero{background:#242424;border-bottom:1px solid #333} QFrame#panel{background:#1b1b1b;border:1px solid #333} QPushButton#nav{text-align:left;border:0;padding:15px 18px;font-size:15px;font-weight:650} QPushButton#nav:hover{background:#252525} QPushButton#nav:checked{background:#303030;border-left:4px solid #52a535} QPushButton#play{background:#3c8527;border:2px solid #69b64c;padding:13px 28px;font-size:16px;font-weight:900} QPushButton#play:hover{background:#4a9b32} QPushButton#install{background:#2b2b2b;border:1px solid #555;padding:11px 18px;font-weight:700} QPushButton#install:hover{background:#383838} QComboBox,QLineEdit{background:#242424;border:1px solid #555;padding:10px;min-height:20px} QPlainTextEdit{background:#0d0d0d;border:1px solid #333;font-family:Consolas,monospace;padding:8px}"""

class Signals(QObject):
    done = Signal(bool, str)

class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()
    def run(self):
        try:
            self.signals.done.emit(True, str(self.fn()))
        except Exception as exc:
            self.signals.done.emit(False, str(exc))

class GamePage(QWidget):
    def __init__(self, label):
        super().__init__()
        self.label = label
        self.engine = ENGINES[label]
        self.proc = None
        self.pool = QThreadPool.globalInstance()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        hero = QFrame()
        hero.setObjectName("hero")
        h = QVBoxLayout(hero)
        h.setContentsMargins(42, 45, 42, 34)
        kicker = QLabel("MINECRAFT")
        kicker.setObjectName("muted")
        title = QLabel({"Java":"JAVA EDITION","Bedrock":"BEDROCK EDITION","EDU":"EDUCATION EDITION","LCE":"LEGACY CONSOLE EDITION","Servers":"SERVERS"}[label])
        title.setObjectName("game")
        desc = QLabel({"Java":"Modern releases, historical versions, modloaders and instances.","Bedrock":"Choose and launch Bedrock releases, betas and previews.","EDU":"Launch classic Minecraft Education builds.","LCE":"Play Legacy Console Edition on Windows.","Servers":"Create and control Java, Bedrock and crossplay servers."}[label])
        desc.setObjectName("heroText")
        desc.setWordWrap(True)
        h.addWidget(kicker); h.addWidget(title); h.addWidget(desc)
        root.addWidget(hero)
        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(42, 28, 42, 35)
        b.setSpacing(13)
        top = QHBoxLayout()
        self.install = QPushButton("INSTALL / UPDATE ENGINE")
        self.install.setObjectName("install")
        self.install.clicked.connect(self.install_engine)
        self.engine_state = QLabel()
        self.engine_state.setObjectName("muted")
        top.addWidget(self.install); top.addWidget(self.engine_state); top.addStretch()
        b.addLayout(top)
        panel = QFrame()
        panel.setObjectName("panel")
        p = QVBoxLayout(panel)
        p.setContentsMargins(22, 20, 22, 20)
        p.setSpacing(12)
        self.controls = QVBoxLayout()
        p.addLayout(self.controls)
        self.build_controls()
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        p.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(180)
        self.output.setPlaceholderText("Launcher output")
        p.addWidget(self.output)
        b.addWidget(panel)
        root.addWidget(body, 1)
        self.refresh_state()

    def combo(self, items=(), editable=True):
        c = QComboBox(); c.setEditable(editable); c.addItems(items); return c
    def btn(self, text, fn, play=False):
        b = QPushButton(text); b.setObjectName("play" if play else "install"); b.clicked.connect(fn); return b
    def row(self, *widgets):
        row = QHBoxLayout()
        for widget in widgets: row.addWidget(widget)
        self.controls.addLayout(row)
    def build_controls(self):
        if self.label == "Java":
            self.channel = self.combo(["release","beta","classic"], False)
            self.version = self.combo([], True)
            self.row(self.channel, self.version, self.btn("REFRESH", lambda: self.run(["versions"], "versions")), self.btn("PLAY", lambda: self.run([self.channel.currentText(), self.version.currentText().strip()]), True))
        elif self.label == "Bedrock":
            self.channel = self.combo(["release","beta","preview"], False)
            self.version = self.combo([], True)
            self.row(self.channel, self.version, self.btn("REFRESH", lambda: self.run(["versions"], "versions")), self.btn("PLAY", lambda: self.run([self.channel.currentText(), self.version.currentText().strip()]), True))
        elif self.label == "EDU":
            self.version = self.combo(["1.8.9","1.7.10"], True)
            self.row(self.version, self.btn("PLAY", lambda: self.run([self.version.currentText().strip()]), True))
        elif self.label == "LCE":
            self.source = self.combo(["verified","nightly-revelations","nightly-mclce"], False)
            self.name = QLineEdit(); self.name.setPlaceholderText("Player name")
            self.row(self.source, self.name, self.btn("PLAY", self.lce, True))
        else:
            self.server = QLineEdit(); self.server.setPlaceholderText("Server name")
            self.provider = self.combo(["paper","purpur","vanilla","fabric","quilt","forge","neoforge","bds","pocketmine","powernukkitx"], False)
            self.version = self.combo(["latest"], True)
            self.row(self.server, self.provider, self.version, self.btn("VERSIONS", lambda: self.run(["versions", self.provider.currentText()], "versions")), self.btn("CREATE", self.create, True))
            self.row(self.btn("LIST", lambda: self.run(["list"])), self.btn("START", lambda: self.action("start"), True), self.btn("STOP", lambda: self.action("stop")), self.btn("RESTART", lambda: self.action("restart")), self.btn("STATUS", lambda: self.action("status")))
    def refresh_state(self):
        self.engine_state.setText("Installed" if self.engine.locate() else "Engine not installed")
    def startup_refresh(self):
        if not self.engine.locate(): return
        if self.label in ("Java", "Bedrock"): self.run(["versions"], "versions", quiet=True)
        elif self.label == "Servers": self.run(["versions", self.provider.currentText()], "versions", quiet=True)
    def install_engine(self):
        self.install.setEnabled(False)
        self.status.setText("Checking GitHub Releases...")
        job = Job(lambda: self.engine.install_latest())
        def done(ok, message):
            self.install.setEnabled(True)
            self.status.setText(("Installed " if ok else "Install failed: ") + message)
            self.refresh_state()
            if ok: self.startup_refresh()
        job.signals.done.connect(done)
        self.pool.start(job)
    def lce(self):
        args = ["launch"]
        source = self.source.currentText()
        if source != "verified": args += ["--source", source]
        if self.name.text().strip(): args += ["--name", self.name.text().strip()]
        self.run(args)
    def create(self):
        name = self.server.text().strip()
        if not name: self.status.setText("Enter a server name."); return
        self.run(["create", name, self.provider.currentText(), self.version.currentText().strip() or "latest"])
    def action(self, action):
        name = self.server.text().strip()
        if not name: self.status.setText("Enter a server name."); return
        self.run([action, name])
    def run(self, args, capture=None, quiet=False):
        cmd, error = self.engine.command(*[x for x in args if x])
        if error: self.status.setText(error); return
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.status.setText("Another command is running."); return
        if not quiet:
            self.output.clear()
        self.status.setText("Refreshing versions..." if quiet else "Running...")
        self.proc = QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        chunks = []
        def ready():
            text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
            chunks.append(text)
            if not quiet:
                self.output.insertPlainText(text)
                self.output.ensureCursorVisible()
        def finished(code, status):
            ready()
            self.status.setText("Ready" if code == 0 else f"Exited with code {code}")
            if capture == "versions" and hasattr(self, "version"):
                values = []
                for line in "".join(chunks).splitlines():
                    values += re.findall(r"(?<!\w)(?:[cbra]?\d+(?:\.\d+){1,3}(?:[-._][\w.-]+)?|latest)(?!\w)", line, re.I)
                values = list(dict.fromkeys(values))
                if values:
                    self.version.clear()
                    self.version.addItems(values)
        self.proc.readyReadStandardOutput.connect(ready)
        self.proc.finished.connect(finished)
        self.proc.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JAVBED Launcher")
        self.resize(1240, 790)
        self.setMinimumSize(960, 620)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        rail = QFrame(); rail.setObjectName("rail"); rail.setFixedWidth(230)
        nav = QVBoxLayout(rail); nav.setContentsMargins(0, 28, 0, 20)
        logo = QLabel("  JAVBED"); logo.setObjectName("logo")
        nav.addWidget(logo); nav.addSpacing(25)
        self.stack = QStackedWidget(); self.buttons = []; self.pages = []
        for index, label in enumerate(("Java","Bedrock","EDU","LCE","Servers")):
            button = QPushButton(label); button.setObjectName("nav"); button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.select(i))
            nav.addWidget(button); self.buttons.append(button)
            page = GamePage(label); self.pages.append(page); self.stack.addWidget(page)
        nav.addStretch()
        footer = QLabel("  JAVBED LAUNCHER"); footer.setObjectName("muted"); nav.addWidget(footer)
        layout.addWidget(rail); layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.select(0)
        QTimer.singleShot(250, self.refresh_all_versions)
    def refresh_all_versions(self):
        for page in self.pages: page.startup_refresh()
    def select(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.buttons): button.setChecked(i == index)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JAVBED")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())

if __name__ == "__main__":
    main()
