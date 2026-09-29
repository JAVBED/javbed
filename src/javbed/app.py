from __future__ import annotations
import re, sys
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QApplication,QComboBox,QFrame,QHBoxLayout,QLabel,QLineEdit,QMainWindow,QPlainTextEdit,QPushButton,QStackedWidget,QVBoxLayout,QWidget)
from .engines import ENGINES

STYLE="""QWidget{background:#0b0e14;color:#eef2f7;font-family:'Segoe UI'} QFrame#sidebar{background:#10151d;border-right:1px solid #202936} QLabel#brand{font-size:25px;font-weight:800;letter-spacing:2px} QLabel#title{font-size:30px;font-weight:800} QLabel#muted{color:#91a0b3} QPushButton#nav{text-align:left;padding:12px 16px;border:0;border-radius:9px;font-size:14px;font-weight:600} QPushButton#nav:hover{background:#171e29} QPushButton#nav:checked{background:#202a38} QFrame#card{background:#111721;border:1px solid #222d3b;border-radius:16px} QComboBox,QLineEdit{background:#0d121a;border:1px solid #2b3748;border-radius:8px;padding:9px;min-height:20px} QPushButton#primary{background:#eef2f7;color:#10141a;border:0;border-radius:8px;padding:10px 16px;font-weight:800} QPushButton#secondary{background:#202a38;border:0;border-radius:8px;padding:10px 16px;font-weight:700} QPlainTextEdit{background:#080b10;border:1px solid #202936;border-radius:10px;padding:8px;font-family:Consolas,monospace}"""

class RunnerPage(QWidget):
    def __init__(self,label):
        super().__init__(); self.label=label; self.engine=ENGINES[label]; self.proc=None
        root=QVBoxLayout(self); root.setContentsMargins(42,34,42,38); root.setSpacing(12)
        title=QLabel(label); title.setObjectName("title"); root.addWidget(title)
        sub=QLabel({"Java":"Minecraft Java Edition","Bedrock":"Minecraft Bedrock Edition","EDU":"Minecraft Education Edition","LCE":"Minecraft Legacy Console Edition","Servers":"Minecraft server manager"}[label]); sub.setObjectName("muted"); root.addWidget(sub)
        card=QFrame(); card.setObjectName("card"); box=QVBoxLayout(card); box.setContentsMargins(24,22,24,22); box.setSpacing(12)
        self.controls=QVBoxLayout(); box.addLayout(self.controls); self.build_controls()
        self.status=QLabel("Ready"); self.status.setObjectName("muted"); box.addWidget(self.status)
        self.output=QPlainTextEdit(); self.output.setReadOnly(True); self.output.setPlaceholderText("Command output"); self.output.setMinimumHeight(230); box.addWidget(self.output)
        root.addWidget(card); root.addStretch()

    def combo(self, items=(), editable=True):
        c=QComboBox(); c.setEditable(editable); c.addItems(items); return c
    def row(self,*widgets):
        l=QHBoxLayout()
        for w in widgets:l.addWidget(w)
        self.controls.addLayout(l)
    def button(self,text,fn,primary=False):
        b=QPushButton(text); b.setObjectName("primary" if primary else "secondary"); b.clicked.connect(fn); return b

    def build_controls(self):
        if self.label=="Java":
            self.channel=self.combo(["release","beta","classic"],False); self.version=self.combo([],True)
            self.row(self.channel,self.version,self.button("Refresh versions",lambda:self.run(["versions"],capture="versions")),self.button("Install / Launch",self.java_launch,True))
        elif self.label=="Bedrock":
            self.channel=self.combo(["release","beta","preview"],False); self.version=self.combo([],True)
            self.row(self.channel,self.version,self.button("Refresh versions",lambda:self.run(["versions"],capture="versions")),self.button("Install / Launch",lambda:self.run([self.channel.currentText(),self.version.currentText().strip()]),True))
        elif self.label=="EDU":
            self.version=self.combo(["1.8.9","1.7.10"],True)
            self.row(self.version,self.button("Launch",lambda:self.run([self.version.currentText().strip()]),True))
        elif self.label=="LCE":
            self.source=self.combo(["verified","nightly-revelations","nightly-mclce"],False); self.name=QLineEdit(); self.name.setPlaceholderText("Player name (optional)")
            self.row(self.source,self.name,self.button("Launch",self.lce_launch,True))
        else:
            self.server=QLineEdit(); self.server.setPlaceholderText("Server name")
            self.provider=self.combo(["paper","purpur","vanilla","fabric","quilt","forge","neoforge","bds","pocketmine","powernukkitx"],False)
            self.version=self.combo(["latest"],True)
            self.row(self.server,self.provider,self.version,self.button("Versions",self.server_versions),self.button("Create",self.server_create,True))
            self.row(self.button("List",lambda:self.run(["list"])),self.button("Start",lambda:self.server_action("start")),self.button("Stop",lambda:self.server_action("stop")),self.button("Restart",lambda:self.server_action("restart")),self.button("Status",lambda:self.server_action("status")))

    def java_launch(self): self.run([self.channel.currentText(),self.version.currentText().strip()])
    def lce_launch(self):
        args=["launch"]; src=self.source.currentText()
        if src!="verified": args += ["--source",src]
        if self.name.text().strip(): args += ["--name",self.name.text().strip()]
        self.run(args)
    def server_versions(self): self.run(["versions",self.provider.currentText()],capture="versions")
    def server_create(self):
        name=self.server.text().strip(); version=self.version.currentText().strip() or "latest"
        if not name: self.status.setText("Enter a server name."); return
        self.run(["create",name,self.provider.currentText(),version])
    def server_action(self,action):
        name=self.server.text().strip()
        if not name: self.status.setText("Enter a server name."); return
        self.run([action,name])

    def run(self,args,capture=None):
        cmd,error=self.engine.command(*[a for a in args if a])
        if error: self.status.setText(error); return
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning: self.status.setText("A command is already running."); return
        self.output.clear(); self.status.setText("Running: "+" ".join(args))
        self.proc=QProcess(self); self.proc.setProgram(cmd[0]); self.proc.setArguments(cmd[1:]); self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        captured=[]
        def ready():
            text=bytes(self.proc.readAllStandardOutput()).decode(errors="replace"); captured.append(text); self.output.insertPlainText(text); self.output.ensureCursorVisible()
        def done(code,status):
            ready(); self.status.setText("Done." if code==0 else f"Command exited with code {code}.")
            if capture=="versions":
                vals=[]
                for line in "".join(captured).splitlines():
                    vals += re.findall(r"(?<!\w)(?:[cbra]?\d+(?:\.\d+){1,3}(?:[-._][\w.-]+)?|latest)(?!\w)",line,re.I)
                vals=list(dict.fromkeys(vals))
                if vals:
                    self.version.clear(); self.version.addItems(vals)
        self.proc.readyReadStandardOutput.connect(ready); self.proc.finished.connect(done); self.proc.start()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("JAVBED"); self.resize(1180,760); self.setMinimumSize(920,600)
        root=QWidget(); shell=QHBoxLayout(root); shell.setContentsMargins(0,0,0,0); shell.setSpacing(0)
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(205); nav=QVBoxLayout(side); nav.setContentsMargins(20,27,20,22)
        brand=QLabel("JAVBED"); brand.setObjectName("brand"); nav.addWidget(brand); nav.addSpacing(25)
        self.stack=QStackedWidget(); self.buttons=[]
        for i,label in enumerate(("Java","Bedrock","EDU","LCE","Servers")):
            b=QPushButton(label); b.setObjectName("nav"); b.setCheckable(True); b.clicked.connect(lambda checked=False,x=i:self.select(x)); nav.addWidget(b); self.buttons.append(b); self.stack.addWidget(RunnerPage(label))
        nav.addStretch(); shell.addWidget(side); shell.addWidget(self.stack,1); self.setCentralWidget(root); self.select(0)
    def select(self,i):
        self.stack.setCurrentIndex(i)
        for n,b in enumerate(self.buttons):b.setChecked(n==i)

def main():
    app=QApplication(sys.argv); app.setApplicationName("JAVBED"); app.setStyleSheet(STYLE); w=MainWindow(); w.show(); raise SystemExit(app.exec())
if __name__=="__main__":main()
