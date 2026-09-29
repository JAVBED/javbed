from __future__ import annotations
import os, re, shutil, subprocess, sys
from PySide6.QtCore import QObject,QProcess,QRunnable,QThreadPool,QTimer,Signal
from PySide6.QtWidgets import QApplication,QComboBox,QFrame,QHBoxLayout,QLabel,QLineEdit,QMainWindow,QPlainTextEdit,QPushButton,QStackedWidget,QVBoxLayout,QWidget
from .engines import ENGINES

STYLE="""QWidget{background:#211f1e;color:white;font-family:'Segoe UI'} QFrame#rail{background:#2b2928;border-right:1px solid #111} QFrame#account{background:#222120;border-bottom:1px solid #111} QLabel#logo{font-size:17px;font-weight:800} QLabel#small{font-size:11px;color:#bbb} QLabel#game{font-size:16px;font-weight:900} QFrame#topbar{background:#242221;border-bottom:1px solid #111} QPushButton#tab{background:transparent;border:0;padding:13px 10px;font-size:15px} QPushButton#tab:checked{border-bottom:3px solid #54a82f;font-weight:700} QPushButton#nav{text-align:left;background:#353231;border:1px solid #191817;padding:15px 13px;font-size:13px;font-weight:800} QPushButton#nav:hover{background:#413d3b} QPushButton#nav:checked{background:#4a4644;border-left:4px solid white} QFrame#hero{background:#171615;border:1px solid #111} QLabel#heroTitle{font-size:34px;font-weight:900} QLabel#heroSub{font-size:15px;color:#ddd} QFrame#playbar{background:#292725;border-top:1px solid #111;border-bottom:1px solid #111} QPushButton#play{background:#3c8527;border:3px solid #171717;padding:12px 65px;font-size:19px;font-weight:900} QPushButton#play:hover{background:#4c9b35} QPushButton#secondary{background:#353331;border:1px solid #666;padding:10px 14px;font-weight:700} QComboBox,QLineEdit{background:#262422;border:1px solid #666;padding:9px} QPlainTextEdit{background:#121212;border:1px solid #333;font-family:Consolas,monospace}"""

EXTRA_GAMES={
"Dungeons":(("MinecraftDungeons.exe","Dungeons.exe"),"Minecraft Dungeons"),
"Legends":(("MinecraftLegends.exe","Legends.exe"),"Minecraft Legends"),
"Dungeons 2":(("MinecraftDungeons2.exe","Dungeons2.exe"),"Minecraft Dungeons 2"),
}

class Signals(QObject): done=Signal(bool,str)
class Job(QRunnable):
    def __init__(self,fn):super().__init__();self.fn=fn;self.signals=Signals()
    def run(self):
        try:self.signals.done.emit(True,str(self.fn()))
        except Exception as e:self.signals.done.emit(False,str(e))

def find_game(names):
    for name in names:
        p=shutil.which(name)
        if p:return p
    if sys.platform=="win32":
        roots=[os.getenv("ProgramFiles"),os.getenv("ProgramFiles(x86)"),os.getenv("LOCALAPPDATA")]
        for root in filter(None,roots):
            for name in names:
                for base in ("Minecraft Launcher","Microsoft Studios","XboxGames"):
                    p=os.path.join(root,base,name)
                    if os.path.isfile(p):return p
    return None

class ExtraPage(QWidget):
    def __init__(self,label):
        super().__init__();self.label=label
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        root.addWidget(self.topbar())
        hero=QFrame();hero.setObjectName("hero");h=QVBoxLayout(hero);h.setContentsMargins(55,70,55,70)
        title=QLabel(EXTRA_GAMES[label][1].upper());title.setObjectName("heroTitle")
        sub=QLabel("Launch the installed game from JAVBED." if label!="Dungeons 2" else "Ready for Dungeons 2 when a launchable installation becomes available.");sub.setObjectName("heroSub");sub.setWordWrap(True)
        h.addWidget(title);h.addWidget(sub);h.addStretch();root.addWidget(hero,1)
        bar=QFrame();bar.setObjectName("playbar");b=QHBoxLayout(bar);b.setContentsMargins(35,10,35,10);self.state=QLabel();b.addWidget(self.state);b.addStretch();play=QPushButton("PLAY");play.setObjectName("play");play.clicked.connect(self.launch);b.addWidget(play);root.addWidget(bar);self.refresh()
    def topbar(self):
        f=QFrame();f.setObjectName("topbar");l=QHBoxLayout(f);l.setContentsMargins(18,5,18,5)
        for text in ("Play",):
            b=QPushButton(text);b.setObjectName("tab");b.setCheckable(True);b.setChecked(text=="Play");l.addWidget(b)
        l.addStretch();return f
    def refresh(self):
        self.path=find_game(EXTRA_GAMES[self.label][0]);self.state.setText("Installed" if self.path else "Not detected")
    def launch(self):
        self.refresh()
        if self.path:subprocess.Popen([self.path])
        else:self.state.setText("Game executable not found on this PC.")

class GamePage(QWidget):
    def __init__(self,label):
        super().__init__();self.label=label;self.engine=ENGINES[label];self.proc=None;self.pool=QThreadPool.globalInstance()
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0);root.addWidget(self.topbar())
        hero=QFrame();hero.setObjectName("hero");h=QVBoxLayout(hero);h.setContentsMargins(55,45,55,35)
        title=QLabel({"Java":"MINECRAFT: JAVA EDITION","Bedrock":"MINECRAFT: BEDROCK EDITION","EDU":"MINECRAFT EDUCATION","LCE":"MINECRAFT: LEGACY CONSOLE EDITION","Servers":"JAVBED SERVERS"}[label]);title.setObjectName("heroTitle")
        sub=QLabel({"Java":"Modern and historical Java builds in one launcher.","Bedrock":"Release, beta and preview Bedrock builds.","EDU":"Classic Minecraft Education builds.","LCE":"Legacy Console Edition launcher.","Servers":"Create and control Minecraft servers."}[label]);sub.setObjectName("heroSub")
        h.addWidget(title);h.addWidget(sub);h.addStretch()
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumHeight(125);h.addWidget(self.output);root.addWidget(hero,1)
        bar=QFrame();bar.setObjectName("playbar");b=QHBoxLayout(bar);b.setContentsMargins(28,8,28,8);self.controls=QHBoxLayout();b.addLayout(self.controls);self.build_controls();root.addWidget(bar)
        foot=QHBoxLayout();self.install=QPushButton("INSTALL / UPDATE ENGINE");self.install.setObjectName("secondary");self.install.clicked.connect(self.install_engine);self.status=QLabel();foot.addWidget(self.install);foot.addWidget(self.status);foot.addStretch();wrap=QWidget();wrap.setLayout(foot);root.addWidget(wrap);self.refresh_state()
    def topbar(self):
        f=QFrame();f.setObjectName("topbar");l=QHBoxLayout(f);l.setContentsMargins(18,5,18,5)
        for text in ("Play",):
            b=QPushButton(text);b.setObjectName("tab");b.setCheckable(True);b.setChecked(text=="Play");l.addWidget(b)
        l.addStretch();return f
    def combo(self,items=(),editable=True):c=QComboBox();c.setEditable(editable);c.addItems(items);return c
    def button(self,text,fn,play=False):b=QPushButton(text);b.setObjectName("play" if play else "secondary");b.clicked.connect(fn);return b
    def build_controls(self):
        if self.label=="Java":
            self.channel=self.combo(["release","snapshot","beta","alpha","infdev","indev","classic","preclassic"],False);self.version=self.combo([],True);self.controls.addWidget(self.version);self.controls.addWidget(self.channel);self.controls.addStretch();self.controls.addWidget(self.button("PLAY",lambda:self.run([self.channel.currentText(),self.version.currentText().strip()]),True));self.channel.currentTextChanged.connect(self.refresh_java_versions)
        elif self.label=="Bedrock":
            self.channel=self.combo(["release","beta","preview"],False);self.version=self.combo([],True);self.controls.addWidget(self.version);self.controls.addWidget(self.channel);self.controls.addStretch();self.controls.addWidget(self.button("PLAY",lambda:self.run([self.channel.currentText(),self.version.currentText().strip()]),True))
        elif self.label=="EDU":
            self.version=self.combo(["1.8.9","1.7.10"],True);self.controls.addWidget(self.version);self.controls.addStretch();self.controls.addWidget(self.button("PLAY",lambda:self.run([self.version.currentText().strip()]),True))
        elif self.label=="LCE":
            self.source=self.combo(["verified","nightly-revelations","nightly-mclce"],False);self.name=QLineEdit();self.name.setPlaceholderText("Player name");self.controls.addWidget(self.source);self.controls.addWidget(self.name);self.controls.addStretch();self.controls.addWidget(self.button("PLAY",self.lce,True))
        else:
            self.server=QLineEdit();self.server.setPlaceholderText("Server name");self.provider=self.combo(["paper","purpur","vanilla","fabric","quilt","forge","neoforge","bds","pocketmine","powernukkitx"],False);self.version=self.combo(["latest"],True)
            for w in (self.server,self.provider,self.version):self.controls.addWidget(w)
            self.controls.addWidget(self.button("CREATE",self.create,True));self.controls.addWidget(self.button("START",lambda:self.action("start")));self.controls.addWidget(self.button("STOP",lambda:self.action("stop")))
    def refresh_java_versions(self):
        if self.label == "Java" and self.engine.locate():
            self.run(["versions", "--type", self.channel.currentText()], "versions", True)

    def refresh_state(self):
        p = self.engine.locate()
        self.status.setText(("Using " + str(p)) if p else "Engine not installed")

    def startup_refresh(self):
        if not self.engine.locate():
            return
        if self.label == "Java":
            self.refresh_java_versions()
        elif self.label == "Bedrock":
            self.run(["versions"], "versions", True)
        elif self.label == "Servers":
            self.run(["versions", self.provider.currentText()], "versions", True)
    def install_engine(self):
        self.install.setEnabled(False);self.status.setText("Checking GitHub Releases...")
        job=Job(lambda:self.engine.install_latest())
        def done(ok,msg):self.install.setEnabled(True);self.status.setText(("Installed " if ok else "Install failed: ")+msg);self.refresh_state();self.startup_refresh() if ok else None
        job.signals.done.connect(done);self.pool.start(job)
    def lce(self):
        a=["launch"];s=self.source.currentText()
        if s!="verified":a+=["--source",s]
        if self.name.text().strip():a+=["--name",self.name.text().strip()]
        self.run(a)
    def create(self):
        n=self.server.text().strip()
        if not n:self.status.setText("Enter a server name.");return
        self.run(["create",n,self.provider.currentText(),self.version.currentText().strip() or "latest"])
    def action(self,a):
        n=self.server.text().strip()
        if not n:self.status.setText("Enter a server name.");return
        self.run([a,n])
    def run(self,args,capture=None,quiet=False):
        cmd,error=self.engine.command(*[x for x in args if x])
        if error:self.status.setText(error);return
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:return
        if not quiet:self.output.clear()
        self.proc=QProcess(self);self.proc.setProgram(cmd[0]);self.proc.setArguments(cmd[1:]);self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels);chunks=[]
        def ready():
            t=bytes(self.proc.readAllStandardOutput()).decode(errors="replace");chunks.append(t)
            if not quiet:self.output.insertPlainText(t)
        def done(code,status):
            ready()
            if capture=="versions" and hasattr(self,"version"):
                vals=[]
                for line in "".join(chunks).splitlines():vals+=re.findall(r"(?<!\w)(?:[cbra]?\d+(?:\.\d+){1,3}(?:[-._][\w.-]+)?|latest)(?!\w)",line,re.I)
                vals=list(dict.fromkeys(vals))
                if vals:self.version.clear();self.version.addItems(vals)
        self.proc.readyReadStandardOutput.connect(ready);self.proc.finished.connect(done);self.proc.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("JAVBED Launcher");self.resize(1280,760);self.setMinimumSize(1000,650)
        root=QWidget();layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        rail=QFrame();rail.setObjectName("rail");rail.setFixedWidth(180);r=QVBoxLayout(rail);r.setContentsMargins(0,0,0,0);r.setSpacing(0)
        account=QFrame();account.setObjectName("account");a=QVBoxLayout(account);name=QLabel("JAVBED");name.setObjectName("logo");sub=QLabel("Universal Minecraft launcher");sub.setObjectName("small");a.addWidget(name);a.addWidget(sub);r.addWidget(account)
        self.stack=QStackedWidget();self.buttons=[];self.pages=[]
        entries=("Java","Bedrock","EDU","LCE","Dungeons","Dungeons 2","Legends","Servers")
        for i,label in enumerate(entries):
            b=QPushButton(("MINECRAFT:\n" if label not in ("Servers","Dungeons","Dungeons 2","Legends") else "MINECRAFT\n" if label!="Servers" else "")+label.upper());b.setObjectName("nav");b.setCheckable(True);b.clicked.connect(lambda checked=False,x=i:self.select(x));r.addWidget(b);self.buttons.append(b)
            page=ExtraPage(label) if label in EXTRA_GAMES else GamePage(label);self.pages.append(page);self.stack.addWidget(page)
        r.addStretch();layout.addWidget(rail);layout.addWidget(self.stack,1);self.setCentralWidget(root);self.select(0);QTimer.singleShot(300,self.refresh_all)
    def refresh_all(self):
        for p in self.pages:
            if isinstance(p,GamePage):p.startup_refresh()
            elif isinstance(p,ExtraPage):p.refresh()
    def select(self,i):
        self.stack.setCurrentIndex(i)
        for n,b in enumerate(self.buttons):b.setChecked(n==i)

def main():
    app=QApplication(sys.argv);app.setApplicationName("JAVBED");app.setStyleSheet(STYLE);w=MainWindow();w.show();raise SystemExit(app.exec())
if __name__=="__main__":main()
