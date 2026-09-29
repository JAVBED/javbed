from __future__ import annotations
import os, re, shutil, subprocess, sys
from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QTimer, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from .engines import ENGINES
from .artwork import cached_art, load_async

STYLE="""QWidget{background:#211f1e;color:white;font-family:'Segoe UI'} QFrame#rail{background:#2b2928;border-right:1px solid #111} QFrame#account{background:#222120;border-bottom:1px solid #111} QLabel#logo{font-size:17px;font-weight:800} QLabel#small{font-size:11px;color:#bbb} QLabel#game{font-size:16px;font-weight:900} QFrame#topbar{background:#242221;border-bottom:1px solid #111} QPushButton#tab{background:transparent;border:0;padding:13px 10px;font-size:15px} QPushButton#tab:checked{border-bottom:3px solid #54a82f;font-weight:700} QPushButton#nav{text-align:left;background:#353231;border:1px solid #191817;padding:15px 13px;font-size:13px;font-weight:800} QPushButton#nav:hover{background:#413d3b} QPushButton#nav:checked{background:#4a4644;border-left:4px solid white} QFrame#hero{background:#171615;border:1px solid #111} QLabel#heroTitle{font-size:34px;font-weight:900} QLabel#heroSub{font-size:15px;color:#ddd} QFrame#playbar{background:#292725;border-top:1px solid #111;border-bottom:1px solid #111} QPushButton#play{background:#3c8527;border:3px solid #171717;padding:12px 65px;font-size:19px;font-weight:900} QPushButton#play:hover{background:#4c9b35} QPushButton#secondary{background:#353331;border:1px solid #666;padding:10px 14px;font-weight:700} QComboBox,QLineEdit{background:#262422;border:1px solid #666;padding:9px} QPlainTextEdit{background:#121212;border:1px solid #333;font-family:Consolas,monospace}"""

EXTRA_GAMES={
"Dungeons":(("MinecraftDungeons.exe","Dungeons.exe"),"Minecraft Dungeons"),
"Legends":(("MinecraftLegends.exe","Legends.exe"),"Minecraft Legends"),
"Dungeons 2":(("MinecraftDungeons2.exe","Dungeons2.exe"),"Minecraft Dungeons 2"),
}

class HeroArt(QLabel):
    def __init__(self,label):
        super().__init__();self.label=label;self.original=QPixmap();self.setMinimumHeight(360);self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setStyleSheet("background:#151515")
        cached=cached_art(label)
        if cached:self.set_art(str(cached))
        else:self._art_job=load_async(label,self.set_art)
    def set_art(self,path):
        if path:
            pix=QPixmap(path)
            if not pix.isNull():self.original=pix;self.apply_cover()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.apply_cover()
    def apply_cover(self):
        if self.original.isNull() or self.width() < 2 or self.height() < 2:
            return
        scaled = self.original.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

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
        hero = HeroArt(label)
        self.hero = hero
        root.addWidget(hero, 1)
        bar=QFrame();bar.setObjectName("playbar");self.playbar=bar;b=QHBoxLayout(bar);b.setContentsMargins(35,10,35,10);self.state=QLabel();b.addWidget(self.state);b.addStretch();play=QPushButton("PLAY");play.setObjectName("play");play.clicked.connect(self.launch);b.addWidget(play);root.addWidget(bar);self.refresh()
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
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0);self.root=root;self.top=self.topbar();root.addWidget(self.top)
        hero = HeroArt(label)
        self.hero = hero
        root.addWidget(hero, 1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.hide()
        bar=QFrame();bar.setObjectName("playbar");self.playbar=bar;b=QHBoxLayout(bar);b.setContentsMargins(28,8,28,8);self.controls=QHBoxLayout();b.addLayout(self.controls);self.build_controls();root.addWidget(bar)
        if self.label == "Java":
            self.build_mods()
            self.build_instances()
            self.build_accounts()
        foot = QHBoxLayout()
        self.install = QPushButton("INSTALL / UPDATE ENGINE")
        self.install.setObjectName("secondary")
        self.install.clicked.connect(self.install_engine)
        self.status = QLabel()
        foot.addWidget(self.install)
        foot.addWidget(self.status)
        foot.addStretch()
        wrap = QWidget()
        wrap.setLayout(foot)
        root.addWidget(wrap)
        self.refresh_state()
    def topbar(self):
        frame = QFrame()
        frame.setObjectName("topbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 5, 18, 5)
        tabs = (("Play", "play"), ("Instances", "instances"), ("Mods", "mods"), ("Accounts", "accounts")) if self.label == "Java" else (("Play", "play"),)
        self.tab_buttons = {}
        for title, key in tabs:
            button = QPushButton(title)
            button.setObjectName("tab")
            button.setCheckable(True)
            button.setChecked(key == "play")
            button.clicked.connect(lambda checked=False, view=key: self.switch_view(view))
            layout.addWidget(button)
            self.tab_buttons[key] = button
        layout.addStretch()
        return frame

    def switch_view(self, key):
        if self.label != "Java":
            return
        self.hero.setVisible(key == "play")
        self.playbar.setVisible(key == "play")
        self.mods_panel.setVisible(key == "mods")
        self.instances_panel.setVisible(key == "instances")
        self.accounts_panel.setVisible(key == "accounts")
        for name, button in self.tab_buttons.items():
            button.setChecked(name == key)

    def build_accounts(self):
        self.accounts_panel = QFrame()
        self.accounts_panel.setObjectName("hero")
        self.accounts_panel.hide()
        box = QVBoxLayout(self.accounts_panel)
        box.setContentsMargins(35, 25, 35, 25)
        title = QLabel("MICROSOFT ACCOUNTS")
        title.setObjectName("heroTitle")
        box.addWidget(title)
        row = QHBoxLayout()
        self.account_alias = QLineEdit()
        self.account_alias.setPlaceholderText("Account alias, e.g. main")
        row.addWidget(self.account_alias)
        row.addWidget(self.button("LOGIN", self.login_account, True))
        row.addWidget(self.button("LIST", self.list_accounts))
        row.addWidget(self.button("USE", self.use_account))
        row.addWidget(self.button("REFRESH", self.refresh_account))
        row.addWidget(self.button("REMOVE", self.remove_account))
        box.addLayout(row)
        note = QLabel("Login uses JAVLI Microsoft authentication. Follow the browser/device instructions JAVLI provides.")
        note.setObjectName("small")
        box.addWidget(note)
        self.account_output = QPlainTextEdit()
        self.account_output.setReadOnly(True)
        box.addWidget(self.account_output)
        self.root.insertWidget(2, self.accounts_panel, 1)

    def login_account(self):
        alias = self.account_alias.text().strip()
        args = ["login"]
        if alias:
            args += ["--alias", alias]
        self.run(args, target=self.account_output)

    def list_accounts(self):
        self.run(["account", "list"], target=self.account_output)

    def use_account(self):
        alias = self.account_alias.text().strip()
        if not alias:
            self.status.setText("Enter an account alias.")
            return
        self.run(["account", "use", alias], target=self.account_output)

    def refresh_account(self):
        self.run(["account", "refresh"], target=self.account_output)

    def remove_account(self):
        alias = self.account_alias.text().strip()
        if not alias:
            self.status.setText("Enter an account alias.")
            return
        self.run(["account", "remove", alias], target=self.account_output)

    def build_mods(self):
        self.mods_panel=QFrame();self.mods_panel.setObjectName("hero");self.mods_panel.hide();box=QVBoxLayout(self.mods_panel);box.setContentsMargins(35,25,35,25)
        title=QLabel("JAVA MODS");title.setObjectName("heroTitle");box.addWidget(title)
        row=QHBoxLayout();self.mod_provider=self.combo(["modrinth","curseforge"],False);self.mod_query=QLineEdit();self.mod_query.setPlaceholderText("Search mods");self.mod_version=QLineEdit();self.mod_version.setPlaceholderText("Minecraft version");self.mod_loader=self.combo(["fabric","quilt","forge","neoforge"],False)
        for w in (self.mod_provider,self.mod_query,self.mod_version,self.mod_loader):row.addWidget(w)
        row.addWidget(self.button("SEARCH",self.search_mods));box.addLayout(row)
        row2=QHBoxLayout();self.mod_instance=QLineEdit();self.mod_instance.setPlaceholderText("Instance name");self.mod_project=QLineEdit();self.mod_project.setPlaceholderText("Project slug / ID");row2.addWidget(self.mod_instance);row2.addWidget(self.mod_project);row2.addWidget(self.button("INSTALL",self.install_mod,True));row2.addWidget(self.button("LIST INSTALLED",self.list_mods));box.addLayout(row2)
        self.mod_output=QPlainTextEdit();self.mod_output.setReadOnly(True);box.addWidget(self.mod_output);self.root.insertWidget(2,self.mods_panel,1)
    def build_instances(self):
        self.instances_panel = QFrame()
        self.instances_panel.setObjectName("hero")
        self.instances_panel.hide()
        box = QVBoxLayout(self.instances_panel)
        box.setContentsMargins(35, 25, 35, 25)
        title = QLabel("JAVA INSTANCES")
        title.setObjectName("heroTitle")
        box.addWidget(title)
        row = QHBoxLayout()
        self.instance_name = QLineEdit(); self.instance_name.setPlaceholderText("Instance name")
        self.instance_era = self.combo(["release","snapshot","beta","alpha","infdev","indev","classic","preclassic"], False)
        self.instance_version = QLineEdit(); self.instance_version.setPlaceholderText("Minecraft version")
        self.instance_loader = self.combo(["none","fabric","quilt","forge","neoforge"], False)
        for widget in (self.instance_name, self.instance_era, self.instance_version, self.instance_loader): row.addWidget(widget)
        row.addWidget(self.button("CREATE", self.create_instance, True))
        box.addLayout(row)
        row2 = QHBoxLayout()
        self.clone_name = QLineEdit(); self.clone_name.setPlaceholderText("Clone as...")
        self.import_path = QLineEdit(); self.import_path.setPlaceholderText("Path to existing instance")
        row2.addWidget(self.button("LIST", self.list_instances))
        row2.addWidget(self.button("LAUNCH", self.launch_instance, True))
        row2.addWidget(self.clone_name)
        row2.addWidget(self.button("CLONE", self.clone_instance))
        row2.addWidget(self.import_path)
        row2.addWidget(self.button("IMPORT", self.import_instance))
        box.addLayout(row2)
        self.instance_output = QPlainTextEdit()
        self.instance_output.setReadOnly(True)
        box.addWidget(self.instance_output)
        self.root.insertWidget(2, self.instances_panel, 1)

    def create_instance(self):
        name = self.instance_name.text().strip(); version = self.instance_version.text().strip()
        if not name or not version: self.status.setText("Enter an instance name and Minecraft version."); return
        args = ["instance","create",name,self.instance_era.currentText(),version]
        if self.instance_loader.currentText() != "none": args += ["--loader",self.instance_loader.currentText()]
        self.run(args,target=self.instance_output)

    def list_instances(self):
        self.run(["instance","list"],target=self.instance_output)

    def launch_instance(self):
        name = self.instance_name.text().strip()
        if not name: self.status.setText("Enter an instance name."); return
        self.run(["instance","launch",name],target=self.instance_output)

    def clone_instance(self):
        source = self.instance_name.text().strip(); dest = self.clone_name.text().strip()
        if not source or not dest: self.status.setText("Enter the source instance and clone name."); return
        self.run(["instance","clone",source,dest],target=self.instance_output)

    def import_instance(self):
        path = self.import_path.text().strip()
        if not path: self.status.setText("Enter an instance path."); return
        self.run(["instance","import",path],target=self.instance_output)

    def search_mods(self):
        args=["mods","search",self.mod_query.text().strip()]
        if self.mod_version.text().strip():args+=["--minecraft",self.mod_version.text().strip()]
        if self.mod_loader.currentText():args+=["--loader",self.mod_loader.currentText()]
        if self.mod_provider.currentText()=="curseforge":args+=["--provider","curseforge"]
        self.run(args,target=self.mod_output)
    def install_mod(self):
        project=self.mod_project.text().strip();instance=self.mod_instance.text().strip()
        if not project or not instance:self.status.setText("Enter an instance and project slug / ID.");return
        args=["mods","install",project,"--instance",instance,"--loader",self.mod_loader.currentText()]
        if self.mod_provider.currentText()=="curseforge":args+=["--provider","curseforge"]
        self.run(args,target=self.mod_output)
    def list_mods(self):
        instance=self.mod_instance.text().strip()
        if not instance:self.status.setText("Enter an instance name.");return
        self.run(["mods","list","--instance",instance],target=self.mod_output)
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
            self.server=QLineEdit();self.server.setPlaceholderText("Server name");self.provider=self.combo(["paper","purpur","vanilla","fabric","quilt","forge","neoforge","bds","pocketmine","powernukkitx"],False);self.version=self.combo([],False);self.provider.currentTextChanged.connect(self.refresh_server_versions)
            for w in (self.server,self.provider,self.version):self.controls.addWidget(w)
            self.controls.addWidget(self.button("CREATE",self.create,True));self.controls.addWidget(self.button("START",lambda:self.action("start")));self.controls.addWidget(self.button("STOP",lambda:self.action("stop")))
    def refresh_server_versions(self):
        if self.label != "Servers" or not self.engine.locate():
            return
        provider = self.provider.currentText()
        cmd, error = self.engine.command("versions", provider)
        if error:
            self.status.setText(error)
            return
        if hasattr(self, "server_version_proc") and self.server_version_proc:
            if self.server_version_proc.state() != QProcess.ProcessState.NotRunning:
                self.server_version_proc.kill()
                self.server_version_proc.waitForFinished(1000)
        self.version.clear()
        self.status.setText("Loading " + provider + " versions...")
        proc = QProcess(self)
        self.server_version_proc = proc
        proc.setProgram(cmd[0])
        proc.setArguments(cmd[1:])
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        chunks = []
        def ready():
            chunks.append(bytes(proc.readAllStandardOutput()).decode(errors="replace"))
        def done(code, exit_status):
            ready()
            if provider != self.provider.currentText():
                return
            values = []
            for raw_line in "".join(chunks).splitlines():
                line = raw_line.strip()
                if not line or line.startswith("…") or " versions" in line:
                    continue
                if re.fullmatch(r"[0-9][0-9A-Za-z._+-]*", line) or line == "latest":
                    values.append(line)
            values = list(dict.fromkeys(values))
            self.version.clear()
            if values:
                self.version.addItems(values)
                self.status.setText("Ready")
            else:
                self.status.setText("No versions returned by " + provider)
        proc.readyReadStandardOutput.connect(ready)
        proc.finished.connect(done)
        proc.start()

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
            self.refresh_server_versions()
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
    def run(self,args,capture=None,quiet=False,target=None):
        cmd,error=self.engine.command(*[x for x in args if x])
        if error:self.status.setText(error);return
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:return
        if not quiet:(target or self.output).clear()
        self.proc=QProcess(self);self.proc.setProgram(cmd[0]);self.proc.setArguments(cmd[1:]);self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels);chunks=[]
        def ready():
            t=bytes(self.proc.readAllStandardOutput()).decode(errors="replace");chunks.append(t)
            if not quiet:(target or self.output).insertPlainText(t)
        def done(code,status):
            ready()
            if capture=="versions" and hasattr(self,"version"):
                vals=[]
                for line in "".join(chunks).splitlines():vals+=re.findall(r"(?<!\w)(?:[cbra]?\d+(?:\.\d+){1,3}(?:[-._][\w.-]+)?|latest)(?!\w)",line,re.I)
                vals=list(dict.fromkeys(vals))
                if vals:self.version.clear();self.version.addItems(vals)
            elif capture == "server_versions" and hasattr(self, "version"):
                values = []
                for raw_line in "".join(chunks).splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("…") or " versions" in line:
                        continue
                    if re.fullmatch(r"[0-9][0-9A-Za-z._+-]*", line) or line == "latest":
                        values.append(line)
                values = list(dict.fromkeys(values))
                self.version.clear()
                if values:
                    self.version.addItems(values)
                else:
                    self.status.setText("No versions returned by " + self.provider.currentText())
        self.proc.readyReadStandardOutput.connect(ready);self.proc.finished.connect(done);self.proc.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("JAVBED Launcher");self.resize(1280,750);self.setMinimumSize(1000,620)
        root=QWidget();layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        rail=QFrame();rail.setObjectName("rail");rail.setFixedWidth(178);r=QVBoxLayout(rail);r.setContentsMargins(0,0,0,0);r.setSpacing(0)
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
