from __future__ import annotations
import os, re, shutil, subprocess, sys, threading
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRunnable, QThreadPool, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QInputDialog
from .engines import ENGINES
from . import history
from .accounts import active_account, avatar_path
from .instances import get_instance, launch_environment, managed_runtime_path, preferences as instance_preferences, snapshot as instance_snapshot
from . import content
from .jobs import Job
from .home import HomePage
from .instance_library import InstanceLibrary
from .content_browser import ContentBrowser
from .modpack_browser import ModpackBrowser
from .world_page import WorldPage
from . import safemode
from .crashdoctor import diagnose
from .servers import ServerDashboard, server_snapshot
from .activity import ActivityManager, ActivityPage
from .doctor_page import DoctorPage
from .artwork import cached_art, load_async
from .settings import apply_environment, load as load_settings, save as save_settings
from .services import engine_status, javbed_update, open_url
from .storymode import DOWNLOAD_URLS, DownloadCancelled, detect_game as detect_story_mode, download_iso
from .theme import STYLE
from . import __version__

EXTRA_GAMES={
"Dungeons":(("MinecraftDungeons.exe","Dungeons.exe"),"Minecraft Dungeons"),
"Legends":(("MinecraftLegends.exe","Legends.exe"),"Minecraft Legends"),
"Dungeons 2":(("MinecraftDungeons2.exe","Dungeons2.exe"),"Minecraft Dungeons 2"),
}
STORE_PRODUCTS = {
    "Dungeons": "9P8MK4NC0LJB",
    "Legends": "9N98Z825TNFW",
}
EXTRA_PATH_KEYS = {
    "Dungeons": "game_dungeons_path",
    "Dungeons 2": "game_dungeons2_path",
    "Legends": "game_legends_path",
}
GAME_FOLDER_NAMES = {
    "Dungeons": ("Minecraft Dungeons",),
    "Dungeons 2": ("Minecraft Dungeons II", "Minecraft Dungeons 2"),
    "Legends": ("Minecraft Legends", "Minecraft Legends - Windows"),
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
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - self.width()) // 2)
        y = 0
        self.setPixmap(scaled.copy(x, y, self.width(), self.height()))

class DownloadSignals(QObject):
    progress = Signal(object, object)
    done = Signal(bool, str)

class DownloadJob(QRunnable):
    def __init__(self, url, destination):
        super().__init__();self.url=url;self.destination=destination;self.signals=DownloadSignals();self.cancelled=threading.Event()
    def run(self):
        try:
            download_iso(self.url,self.destination,self.signals.progress.emit,self.cancelled)
            ok,message=True,str(self.destination)
        except DownloadCancelled as exc:
            ok,message=False,str(exc)
        except Exception as exc:
            ok,message=False,str(exc)
        try:self.signals.done.emit(ok,message)
        except RuntimeError:pass

class EngineUpdateSignals(QObject):
    progress=Signal(str)
    bytes_progress=Signal(str,int,object)
    done=Signal(bool)

class EngineUpdateJob(QRunnable):
    def __init__(self):
        super().__init__();self.signals=EngineUpdateSignals()
    def run(self):
        success=True
        for label,engine in ENGINES.items():
            try:
                self.signals.progress.emit("Updating "+label+"...")
                try:message=label+": "+engine.install_latest(download_progress=lambda received,total, name=label:self.signals.bytes_progress.emit(name,received,total))
                except Exception as exc:message=label+" update failed: "+str(exc);success=False
                self.signals.progress.emit(message)
            except RuntimeError:return
        try:self.signals.done.emit(success)
        except RuntimeError:pass

def find_game(label, names):
    saved=str(load_settings().get(EXTRA_PATH_KEYS.get(label,""),"")).strip()
    if saved and Path(saved).is_file():return ("exe", saved)
    for name in names:
        path = shutil.which(name)
        if path: return ("exe", path)
    if sys.platform != "win32": return None
    folder_names = GAME_FOLDER_NAMES.get(label, ())
    candidates = []
    steam = Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)"))/"Steam"/"steamapps"/"common"
    xbox = Path("C:/XboxGames")
    for folder in folder_names:
        candidates.extend((steam/folder, xbox/folder/"Content", xbox/folder))
    patterns = {
        "Dungeons": ("**/Dungeons.exe", "**/Dungeons-Win64-Shipping.exe", "**/MinecraftDungeons.exe"),
        "Dungeons 2": ("**/Dungeons2*.exe", "**/DungeonsII*.exe", "**/MinecraftDungeons2*.exe"),
        "Legends": ("**/MinecraftLegends.Windows.exe", "**/MinecraftLegends.exe", "**/MinecraftLegends*.exe"),
    }.get(label, ())
    for root in candidates:
        if not root.exists(): continue
        for pattern in patterns:
            found = next(root.glob(pattern), None)
            if found and found.is_file(): return ("exe", str(found))
    # Resolve an actual AppX application ID; never guess PackageFamilyName!App.
    try:
        if label == "Dungeons":
            filter_script = "$_.Name -match 'MinecraftDungeons' -and $_.Name -notmatch 'Dungeons2|DungeonsII'"
        elif label == "Dungeons 2":
            filter_script = "$_.Name -match 'MinecraftDungeons2|MinecraftDungeonsII|Dungeons2|DungeonsII'"
        else:
            filter_script = "$_.Name -match 'MinecraftLegends'"
        script = "$apps=Get-AppxPackage | Where-Object {" + filter_script + "}; foreach($p in $apps){try{$m=Get-AppxPackageManifest $p; foreach($a in $m.Package.Applications.Application){if($a.Id){Write-Output ($p.PackageFamilyName+'!'+$a.Id); exit}}}catch{}}"
        ps = subprocess.run(["powershell","-NoProfile","-Command",script],capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        app_id = ps.stdout.strip().splitlines()[0] if ps.stdout.strip() else ""
        if app_id: return ("shell", "shell:AppsFolder\\" + app_id)
    except Exception: pass
    return None


def open_store_product(label):
    if sys.platform != "win32": return False
    query = {"Dungeons":"Minecraft Dungeons","Dungeons 2":"Minecraft Dungeons II","Legends":"Minecraft Legends"}.get(label)
    if not query: return False
    from urllib.parse import quote
    os.startfile("ms-windows-store://search/?query=" + quote(query))
    return True

def store_helper_path():
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"): candidates.append(Path(sys._MEIPASS)/"Javbed.StoreHelper.exe")
    candidates.append(Path(__file__).resolve().parents[2]/"store-helper"/"publish"/"Javbed.StoreHelper.exe")
    found = shutil.which("Javbed.StoreHelper.exe")
    if found: candidates.append(Path(found))
    return next((p for p in candidates if p.exists()), None)

def store_game_key(label):
    return {"Dungeons":"dungeons","Dungeons 2":"dungeons2","Legends":"legends"}.get(label)

def detect_extra_game(label):
    target=find_game(label,EXTRA_GAMES[label][0])
    helper=store_helper_path() if sys.platform=="win32" else None
    key=store_game_key(label)
    if not target and helper and key:
        result=subprocess.run([str(helper),"status",key],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if result.returncode==0 and "INSTALLED" in result.stdout.splitlines():
            appid=next((line[6:] for line in result.stdout.splitlines() if line.startswith("APPID|") and line[6:]),"")
            if appid:target=("shell","shell:AppsFolder\\"+appid)
    return target,bool(helper and key)

def home_snapshot():
    installed=[]
    for label in ("Java","Bedrock","EDU","LCE"):
        if ENGINES[label].locate():installed.append(label)
    for label in ("Dungeons","Dungeons 2","Legends"):
        try:
            if detect_extra_game(label)[0]:installed.append(label)
        except (OSError,subprocess.SubprocessError):
            pass
    settings=load_settings()
    for index, label in enumerate(("Story Mode Season 1", "Story Mode Season 2")):
        if detect_story_mode(settings,index):
            installed.append(label)
    statuses=engine_status()
    server_text="SERVLI unavailable";server_count=None;running_count=None
    server_engine=ENGINES["Servers"]
    if server_engine.locate():
        try:
            command,error=server_engine.command("list")
            if not error:
                result=subprocess.run(command,capture_output=True,text=True,timeout=8,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                rows=[line for line in result.stdout.splitlines() if line.strip()]
                server_count=sum(bool(re.search(r"\b(?:RUNNING|STOPPED)\b", line)) for line in rows)
                running_count=sum(bool(re.search(r"\bRUNNING\b", line)) for line in rows)
                server_text=result.stdout.strip() or "No servers yet"
        except (OSError,subprocess.SubprocessError) as exc:
            server_text=str(exc)
    account = active_account()
    avatar = avatar_path(account)
    return installed,statuses,server_count,running_count,server_text,account,str(avatar or ""),history.summary()

def mount_story_iso(iso):
    script="$img=Mount-DiskImage -ImagePath '" + iso.replace("'","''") + "' -PassThru; $vol=$img | Get-Volume; Write-Output ($vol.DriveLetter+':')"
    result=subprocess.run(["powershell","-NoProfile","-Command",script],capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "Could not mount the ISO.")
    drive=result.stdout.strip().splitlines()[-1]
    candidates=[]
    for pattern in ("setup.exe","install.exe","*.exe"):
        candidates.extend(Path(drive).glob(pattern))
    installer=next((path for path in candidates if path.is_file()),None)
    if not installer:raise RuntimeError("Mounted ISO, but no installer executable was found.")
    return installer

class ExtraPage(QWidget):
    def __init__(self,label):
        super().__init__();self.label=label;self.pool=QThreadPool.globalInstance();self.launch_target=None;self.helper_available=False;self.scan_job=None
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        root.addWidget(self.topbar())
        hero = HeroArt(label)
        self.hero = hero
        root.addWidget(hero, 1)
        bar=QFrame();bar.setObjectName("playbar");self.playbar=bar;b=QHBoxLayout(bar);b.setContentsMargins(35,10,35,10);self.state=QLabel();b.addWidget(self.state);b.addStretch()
        self.locate_button=QPushButton("LOCATE GAME");self.locate_button.setObjectName("secondary");self.locate_button.clicked.connect(self.locate);b.addWidget(self.locate_button)
        self.play=QPushButton("PLAY");self.play.setObjectName("play");self.play.clicked.connect(self.launch);b.addWidget(self.play);root.addWidget(bar);self.refresh()
    def topbar(self):
        f=QFrame();f.setObjectName("topbar");l=QHBoxLayout(f);l.setContentsMargins(18,5,18,5)
        for text in ("Play",):
            b=QPushButton(text);b.setObjectName("tab");b.setCheckable(True);b.setChecked(text=="Play");l.addWidget(b)
        l.addStretch();return f
    def refresh(self):
        if self.scan_job:return
        self.state.setText("Checking installation...");self.play.setEnabled(False);self.locate_button.setEnabled(False)
        job=Job(lambda:detect_extra_game(self.label));self.scan_job=job
        def done(ok,result):
            self.scan_job=None;self.play.setEnabled(True);self.locate_button.setEnabled(True)
            if not ok:
                self.state.setText("Detection failed: "+str(result)[:120]);return
            self.launch_target,self.helper_available=result
            self.state.setText("Game located" if self.launch_target else "Not detected — use Locate Game")
            self.play.setText("PLAY" if self.launch_target else ("INSTALL" if self.helper_available else "GET"))
        job.signals.done.connect(done);self.pool.start(job)
    def locate(self):
        filter_text="Executables (*.exe);;All files (*)" if sys.platform=="win32" else "All files (*)"
        path,_=QFileDialog.getOpenFileName(self,"Locate "+self.label+" executable","",filter_text)
        if path:
            data=load_settings();data[EXTRA_PATH_KEYS[self.label]]=path;save_settings(data);self.refresh()
    def launch(self):
        if self.launch_target:
            kind,target=self.launch_target
            try:
                if kind=="shell": subprocess.Popen(["explorer.exe",target])
                else:
                    process = subprocess.Popen([target],cwd=str(Path(target).parent))
                    history.watch_process(process, self.label)
            except OSError as exc:
                self.state.setText("Launch failed: "+str(exc)[:140])
            return
        helper=store_helper_path() if self.helper_available else None; key=store_game_key(self.label)
        if helper and key:
            self.play.setEnabled(False); self.state.setText("Installing...")
            proc=QProcess(self); self.store_proc=proc; proc.setProgram(str(helper)); proc.setArguments(["install",key]); proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels); self.store_chunks=[]
            def ready():
                text=bytes(proc.readAllStandardOutput()).decode(errors="replace")
                if text:self.store_chunks.append(text)
                for line in text.splitlines():
                    if line.startswith("PROGRESS|"):
                        parts=line.split("|"); self.state.setText(f"{parts[2]} {parts[1]}%")
            def done(code,status):
                ready(); self.play.setEnabled(True)
                if code==0:
                    self.refresh()
                else:
                    message="".join(self.store_chunks).strip().splitlines()
                    detail=message[-1] if message else "Unknown Store/Gaming Services error."
                    self.state.setText("Install failed: "+detail[:180])
            proc.readyReadStandardOutput.connect(ready); proc.finished.connect(done); proc.start(); return
        if open_store_product(self.label): self.state.setText("Opened Microsoft Store.")
        else:self.state.setText("No automatic install source configured.")


class StoryModePage(QWidget):
    def __init__(self, activity=None):
        super().__init__();self.activity=activity;self.paths=load_settings();self.pool=QThreadPool.globalInstance();self.download_job=None;self.iso_job=None;root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        top=QFrame();top.setObjectName("topbar");tl=QHBoxLayout(top);tl.setContentsMargins(18,5,18,5);tl.addWidget(QLabel("Story Mode"));tl.addStretch();root.addWidget(top)
        self.hero=HeroArt("Story Mode");root.addWidget(self.hero,1)
        bar=QFrame();bar.setObjectName("playbar");b=QHBoxLayout(bar);b.setContentsMargins(28,8,28,8)
        self.season=QComboBox();self.season.addItems(["Season 1","Season 2"]);self.season.currentIndexChanged.connect(self.refresh);b.addWidget(self.season)
        self.state=QLabel();b.addWidget(self.state);b.addStretch()
        locate=QPushButton("LOCATE INSTALLATION");locate.setObjectName("secondary");locate.clicked.connect(self.locate);b.addWidget(locate)
        self.download=QPushButton("DOWNLOAD ISO");self.download.setObjectName("secondary");self.download.clicked.connect(self.download_selected);b.addWidget(self.download)
        self.iso_button=QPushButton("INSTALL FROM ISO");self.iso_button.setObjectName("secondary");self.iso_button.clicked.connect(self.install_iso);b.addWidget(self.iso_button)
        self.play=QPushButton("PLAY");self.play.setObjectName("play");self.play.clicked.connect(self.launch);b.addWidget(self.play);root.addWidget(bar)
        progress_row=QHBoxLayout();self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.hide();progress_row.addWidget(self.progress)
        self.cancel_download=QPushButton("PAUSE DOWNLOAD");self.cancel_download.setObjectName("secondary");self.cancel_download.hide();self.cancel_download.clicked.connect(self.pause_download);progress_row.addWidget(self.cancel_download)
        root.addLayout(progress_row);self.refresh()
    def key(self):return "story_mode_s1_path" if self.season.currentIndex()==0 else "story_mode_s2_path"
    def title(self):return "Story Mode" if self.season.currentIndex()==0 else "Story Mode 2"
    def detect(self, season_index=None):
        index=self.season.currentIndex() if season_index is None else season_index
        return detect_story_mode(self.paths,index)
    def refresh(self):
        self.target=self.detect();self.state.setText("Installed" if self.target else "Not detected");self.play.setEnabled(bool(self.target));self.play.setText("PLAY" if self.target else "PLAY")
    def locate(self):
        path,_=QFileDialog.getOpenFileName(self,"Locate Minecraft: Story Mode executable","","Executable (*.exe);;All files (*)")
        if path:self.paths=load_settings();self.paths[self.key()]=path;save_settings(self.paths);self.refresh()
    def launch(self):
        self.refresh()
        if self.target:
            try:
                process = subprocess.Popen([str(self.target)],cwd=str(self.target.parent))
                history.watch_process(process, self.title())
            except OSError as exc:self.state.setText("Launch failed: "+str(exc)[:140])
    def download_selected(self):
        title=self.title();url=DOWNLOAD_URLS.get(title)
        if not url:self.state.setText("No download URL configured for "+title+".");return
        filename="Minecraft " + title + ".iso"
        selected,_=QFileDialog.getSaveFileName(self,"Save "+title+" ISO",str(Path.home()/"Downloads"/filename),"ISO images (*.iso);;All files (*)")
        if not selected:return
        destination=Path(selected)
        self.download.setEnabled(False);self.season.setEnabled(False)
        self.progress.setRange(0,100);self.progress.setValue(0);self.progress.show();self.cancel_download.show()
        self.state.setText("Downloading " + title + "...")
        job=DownloadJob(url,destination);self.download_job=job
        activity_id=self.activity.begin(title+" ISO",url,"Downloading",job.cancelled.set) if self.activity else None
        def on_progress(received,total):
            if activity_id:self.activity.progress(activity_id,received,total,"Downloading")
            if total:
                percent=min(100,received*100//total)
                self.progress.setRange(0,100);self.progress.setValue(percent)
                self.state.setText(f"Downloading {title}: {percent}%")
            else:
                self.progress.setRange(0,0)
                self.state.setText(f"Downloading {title}: {received//(1024*1024)} MB")
        def on_done(ok,message):
            if activity_id:self.activity.finish(activity_id,ok,"Downloaded" if ok else message[:180])
            self.download.setEnabled(True);self.season.setEnabled(True);self.progress.hide();self.cancel_download.hide();self.cancel_download.setEnabled(True);self.download_job=None
            self.state.setText(("Downloaded " + destination.name if ok else "Download failed: " + message[:140]))
            if ok:self.state.setToolTip(message)
        job.signals.progress.connect(on_progress);job.signals.done.connect(on_done);self.pool.start(job)
    def pause_download(self):
        if self.download_job:
            self.cancel_download.setEnabled(False)
            self.state.setText("Pausing download...")
            self.download_job.cancelled.set()
    def install_iso(self, iso=""):
        if sys.platform!="win32":self.state.setText("ISO installation is currently Windows-only.");return
        if not iso:iso,_=QFileDialog.getOpenFileName(self,"Select Story Mode ISO","","ISO images (*.iso);;All files (*)")
        if not iso:return
        self.iso_button.setEnabled(False);self.state.setText("Mounting ISO...")
        job=Job(lambda:mount_story_iso(iso));self.iso_job=job
        def done(ok,result):
            self.iso_job=None;self.iso_button.setEnabled(True)
            if not ok:self.state.setText("ISO install failed: "+str(result)[:140]);return
            try:
                subprocess.Popen([str(result)],cwd=str(result.parent))
                self.state.setText("Installer opened. Locate the game here after installation.")
            except OSError as exc:self.state.setText("Could not open installer: "+str(exc)[:140])
        job.signals.done.connect(done);self.pool.start(job)

class GamePage(QWidget):
    game_ended = Signal(str, object)
    def __init__(self,label,activity=None):
        super().__init__();self.label=label;self.activity=activity;self.engine=ENGINES[label];self.proc=None;self.pool=QThreadPool.globalInstance()
        self.safe_mode_active = set()
        self.game_ended.connect(self.on_game_ended)
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
            self.build_modpacks()
            self.build_instances()
            self.build_accounts()
            self.build_resources()
            self.build_shaders()
        if self.label == "Servers":
            self.build_server_console()
            self.build_server_dashboard()
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
        tabs = (("Play","play"),("Instances","instances"),("Mods","mods"),("Modpacks","modpacks"),("Resource Packs","resources"),("Shaders","shaders"),("Accounts","accounts")) if self.label=="Java" else ((("Servers","play"),("Dashboard","dashboard"),("Console","console")) if self.label=="Servers" else (("Play","play"),))
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
        if self.label == "Servers":
            self.hero.setVisible(key == "play")
            self.playbar.setVisible(key == "play")
            self.server_console_panel.setVisible(key == "console")
            self.server_dashboard.setVisible(key == "dashboard")
            if key == "dashboard":self.server_dashboard.refresh()
            for name, button in self.tab_buttons.items(): button.setChecked(name == key)
            return
        if self.label != "Java":
            return
        self.hero.setVisible(key == "play")
        self.playbar.setVisible(key == "play")
        self.mods_panel.setVisible(key == "mods")
        if key == "mods":
            self.mods_panel.refresh_instances()
        self.instances_panel.setVisible(key == "instances")
        if key == "instances":
            self.instances_panel.refresh()
        self.modpacks_panel.setVisible(key == "modpacks")
        self.resources_panel.setVisible(key == "resources")
        self.shaders_panel.setVisible(key == "shaders")
        if key == "resources":
            self.resources_panel.refresh_instances()
        if key == "shaders":
            self.shaders_panel.refresh_instances()
        self.accounts_panel.setVisible(key == "accounts")
        for name, button in self.tab_buttons.items():
            button.setChecked(name == key)

    def build_server_console(self):
        self.server_console_panel=QFrame();self.server_console_panel.setObjectName("hero");self.server_console_panel.hide();box=QVBoxLayout(self.server_console_panel);box.setContentsMargins(35,25,35,25)
        title=QLabel("SERVER MANAGEMENT");title.setObjectName("heroTitle");box.addWidget(title)
        row=QHBoxLayout();self.server_command=QLineEdit();self.server_command.setPlaceholderText("Server console command");row.addWidget(self.server_command);row.addWidget(self.button("SEND",self.send_server_command,True));row.addWidget(self.button("LOGS",self.server_logs));row.addWidget(self.button("STATUS",lambda:self.action("status")));box.addLayout(row)
        row2=QHBoxLayout();self.property_key=QLineEdit();self.property_key.setPlaceholderText("Property key");self.property_value=QLineEdit();self.property_value.setPlaceholderText("Property value");row2.addWidget(self.property_key);row2.addWidget(self.property_value);row2.addWidget(self.button("GET",self.get_property));row2.addWidget(self.button("SET",self.set_property));box.addLayout(row2)
        row3=QHBoxLayout();self.player_name=QLineEdit();self.player_name.setPlaceholderText("Player name");row3.addWidget(self.player_name);row3.addWidget(self.button("OP",lambda:self.player_command("op")));row3.addWidget(self.button("DEOP",lambda:self.player_command("deop")));row3.addWidget(self.button("WHITELIST ADD",lambda:self.player_command("whitelist add")));row3.addWidget(self.button("WHITELIST REMOVE",lambda:self.player_command("whitelist remove")));row3.addWidget(self.button("LIST PLAYERS",lambda:self.player_command("list")));box.addLayout(row3)
        row4=QHBoxLayout();self.backup_name=QLineEdit();self.backup_name.setPlaceholderText("Backup filename for restore");row4.addWidget(self.button("BACKUP",self.create_backup,True));row4.addWidget(self.button("LIST BACKUPS",self.list_backups));row4.addWidget(self.backup_name);row4.addWidget(self.button("RESTORE",self.restore_backup));box.addLayout(row4)
        self.server_console_output=QPlainTextEdit();self.server_console_output.setReadOnly(True);box.addWidget(self.server_console_output);self.root.insertWidget(2,self.server_console_panel,1)

    def build_server_dashboard(self):
        self.server_dashboard = ServerDashboard(lambda args, callback: self.run(args, target=self.output, finished=callback), self)
        self.server_dashboard.hide()
        self.root.insertWidget(2, self.server_dashboard, 1)

    def selected_server(self):
        name=self.server.text().strip()
        if not name:self.status.setText("Enter a server name.")
        return name
    def send_server_command(self):
        name=self.selected_server();cmd=self.server_command.text().strip()
        if name and cmd:self.run(["send",name,*cmd.split()],target=self.server_console_output)
    def server_logs(self):
        name=self.selected_server()
        if name:self.run(["logs",name],target=self.server_console_output)
    def get_property(self):
        name=self.selected_server();key=self.property_key.text().strip()
        if name and key:self.run(["properties",name,key],target=self.server_console_output)
    def set_property(self):
        name=self.selected_server();key=self.property_key.text().strip();value=self.property_value.text().strip()
        if name and key:self.run(["properties",name,key,value],target=self.server_console_output)
    def player_command(self,command):
        name=self.selected_server();player=self.player_name.text().strip()
        if not name:return
        parts=command.split()
        if command!="list" and not player:self.status.setText("Enter a player name.");return
        self.run(["send",name,*parts,*(([player] if command!="list" else []))],target=self.server_console_output)
    def create_backup(self):
        name=self.selected_server()
        if name:self.run(["backup",name],target=self.server_console_output)
    def list_backups(self):
        name=self.selected_server()
        if name:self.run(["backups",name],target=self.server_console_output)
    def restore_backup(self):
        name=self.selected_server();backup=self.backup_name.text().strip()
        if name and backup:self.run(["restore",name,backup,"--yes"],target=self.server_console_output)

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

    def build_modpacks(self):
        self.modpacks_panel = ModpackBrowser(
            lambda args, callback: self.run(args, target=self.output, finished=callback), self
        )
        self.modpacks_panel.hide()
        self.root.insertWidget(2, self.modpacks_panel, 1)

    def build_mods(self):
        self.mods_panel = ContentBrowser("mod", lambda args, callback: self.run(args, target=self.output, finished=callback), self)
        self.mods_panel.hide()
        self.root.insertWidget(2, self.mods_panel, 1)

    def build_resources(self):
        self.resources_panel = ContentBrowser("resourcepack", lambda args, callback: self.run(args, target=self.output, finished=callback), self)
        self.resources_panel.hide()
        self.root.insertWidget(2, self.resources_panel, 1)

    def build_shaders(self):
        self.shaders_panel = ContentBrowser("shader", lambda args, callback: self.run(args, target=self.output, finished=callback), self)
        self.shaders_panel.hide()
        self.root.insertWidget(2, self.shaders_panel, 1)

    def build_instances(self):
        self.instance_output = QPlainTextEdit()
        self.instance_output.setReadOnly(True)
        self.instances_panel = InstanceLibrary(
            lambda args, callback: self.run(args, target=self.instance_output, finished=callback), self
        )
        self.instances_panel.hide()
        self.root.insertWidget(2, self.instances_panel, 1)

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
            self.controls.addWidget(self.button("CREATE",self.create,True));self.controls.addWidget(self.button("LIST",lambda:self.run(["list"],target=self.output)));self.controls.addWidget(self.button("START",lambda:self.action("start")));self.controls.addWidget(self.button("STOP",lambda:self.action("stop")));self.controls.addWidget(self.button("RESTART",lambda:self.action("restart")));self.controls.addWidget(self.button("STATUS",lambda:self.action("status")))
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
        self.status.setText(("Using " + str(p)) if p else "Engine not configured — install it or choose a path in Settings")

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
        self.run([a,n],target=self.server_console_output if hasattr(self,"server_console_output") else self.output)
    def play_safe_mode(self, name):
        if name in self.safe_mode_active:
            self.status.setText("Safe Mode is already running for " + name)
            return
        job = Job(lambda: safemode.prepare(name))
        self.status.setText("Temporarily disabling mods...")

        def prepared(ok, result):
            if not ok:
                self.status.setText("Safe Mode failed: " + str(result))
                return
            self.safe_mode_active.add(name)
            self.status.setText(f"Safe Mode: {result} mod(s) disabled until Minecraft exits.")

            def launched(success, output):
                tracked = next((pid for target, pid in safemode.pending() if target == name), 0)
                if not success or not tracked:
                    self.safe_mode_active.discard(name)
                    self.pool.start(Job(lambda: safemode.restore(name)))
                    self.status.setText("Safe Mode launch was not confirmed; restoring mods.")

            self.run(["instance", "launch", name], finished=launched)

        job.signals.done.connect(prepared)
        self.pool.start(job)

    def on_game_ended(self, name, result):
        self.safe_mode_active.discard(name)
        if result.get("restore_error"):
            self.status.setText("Safe Mode restoration needs attention: " + result["restore_error"])
        diagnosis = result.get("diagnosis")
        if not diagnosis:
            return
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("Crash Detected")
        box.setText("CRASH DETECTED\n\nLikely cause: " + diagnosis.cause)
        box.setInformativeText("Evidence: " + diagnosis.evidence)
        paths = {}
        for title, path in (("OPEN LOG", diagnosis.log), ("OPEN CRASH REPORT", diagnosis.report)):
            if path:
                paths[box.addButton(title, QMessageBox.ButtonRole.ActionRole)] = path
        mods = get_instance(name) if name else None
        if mods:
            paths[box.addButton("OPEN MODS FOLDER", QMessageBox.ButtonRole.ActionRole)] = Path(str(mods["path"])) / "minecraft" / "mods"
            safe = box.addButton("PLAY SAFE MODE", QMessageBox.ButtonRole.ActionRole)
        else:
            safe = None
        box.addButton("CLOSE", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        selected = box.clickedButton()
        if selected in paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[selected])))
        elif selected == safe and name:
            self.play_safe_mode(name)

    def run(self,args,capture=None,quiet=False,target=None,finished=None):
        cmd,error=self.engine.command(*[x for x in args if x])
        if error:
            self.status.setText(error)
            if finished:finished(False,error)
            return
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            if finished:finished(False,"Another JAVLI command is still running.")
            return
        if self.label == "Java" and len(args) > 2 and args[:2] == ["instance", "launch"]:
            major = instance_preferences(args[2]).get("java_major")
            if major and not managed_runtime_path(int(major)).is_file():
                self.status.setText(f"Installing Java {major} for {args[2]}...")

                def installed(ok, output):
                    if ok and managed_runtime_path(int(major)).is_file():
                        self.run(args, capture=capture, quiet=quiet, target=target, finished=finished)
                    elif finished:
                        finished(False, output or f"Java {major} installation failed.")

                self.run(["java", "install", str(major)], target=target, finished=installed)
                return
        if not quiet:(target or self.output).clear()
        proc=QProcess(self);self.proc=proc;proc.setProgram(cmd[0]);proc.setArguments(cmd[1:]);proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels);chunks=[]
        tracked_action = bool(args) and (args[0] in ("mods", "modpack", "resourcepack", "shader", "java") and len(args)>1 and args[1] in ("install", "update") or args[0] in ("create", "update", "backup") or args[:2] == ["instance", "create"])
        activity_id = self.activity.begin(" ".join(args[:3]), self.label, "Running backend", None) if self.activity and tracked_action else None
        if self.label == "Java" and args and (args[0] == "instance" and len(args) > 2 and args[1] == "launch" or args[0] in ("release", "snapshot", "beta", "alpha", "infdev", "indev", "classic", "preclassic")):
            environment = QProcessEnvironment.systemEnvironment()
            for key, value in launch_environment(args[2] if args[0] == "instance" else "").items():
                environment.insert(key, value)
            proc.setProcessEnvironment(environment)
        def ready():
            try:t=bytes(proc.readAllStandardOutput()).decode(errors="replace")
            except RuntimeError:return
            chunks.append(t)
            if not quiet:(target or self.output).insertPlainText(t)
        def done(code,status):
            ready()
            if activity_id:self.activity.finish(activity_id,code==0,"Completed" if code==0 else ("".join(chunks).strip()[-160:] or "Failed"))
            if code == 0 and self.label != "Servers":
                launch = bool(args) and (args[0] == "launch" or (self.label == "Java" and args[0] == "instance" and len(args) > 2 and args[1] == "launch") or (self.label in ("Java", "Bedrock", "EDU") and args[0] not in ("versions", "mods", "modpack", "resourcepack", "shader", "instance", "account", "login", "java", "update")))
                if launch:
                    match = re.search(r"\bPID\s+(\d+)\b", "".join(chunks))
                    if match:
                        instance = args[2] if args[0] == "instance" else ""
                        info = get_instance(instance) if instance else None
                        version = str(info.get("version", "")) if info else (args[-1] if self.label in ("Java", "Bedrock", "EDU") and args else "")
                        loader = str(info.get("loader", "")) if info else ""
                        channel = str(info.get("era", "")) if info else (args[0] if self.label in ("Java", "Bedrock") else "")
                        def exited(started, exit_code):
                            restore_error = ""
                            if instance in self.safe_mode_active:
                                try:safemode.restore(instance)
                                except Exception as exc:restore_error = str(exc)
                            diagnosis = None
                            if self.label == "Java" and instance and info:
                                try:diagnosis = diagnose(Path(str(info["path"])) / "minecraft", started, exit_code)
                                except OSError:pass
                            self.game_ended.emit(instance, {"diagnosis": diagnosis, "restore_error": restore_error})
                        if instance in self.safe_mode_active:
                            try:safemode.set_pid(instance, int(match.group(1)))
                            except Exception as exc:self.status.setText("Safe Mode journal error: " + str(exc))
                        watched = history.watch_pid(int(match.group(1)), self.label, instance=instance, version=version, channel=channel, loader=loader, on_exit=exited)
                        if not watched and instance in self.safe_mode_active:
                            self.pool.start(Job(lambda: safemode.restore(instance)))
                            self.safe_mode_active.discard(instance)
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
            if finished:
                finished(code == 0, "".join(chunks))
        proc.readyReadStandardOutput.connect(ready);proc.finished.connect(done);proc.start()

class UpdatesPage(QWidget):
    def __init__(self, activity=None, window=None):
        super().__init__();self.activity=activity;self.window=window;self.pool=QThreadPool.globalInstance();self.update_job=None;self.check_job=None;self.global_running=False;self.global_failed=False; root=QVBoxLayout(self); root.setContentsMargins(36,28,36,28)
        title=QLabel("UPDATES & ENGINES"); title.setObjectName("heroTitle"); root.addWidget(title)
        self.output=QPlainTextEdit(); self.output.setReadOnly(True); root.addWidget(self.output)
        row=QHBoxLayout(); refresh=QPushButton("REFRESH STATUS"); refresh.setObjectName("secondary"); refresh.clicked.connect(self.refresh); self.update_button=QPushButton("UPDATE MANAGED ENGINES"); self.update_button.setObjectName("play"); self.update_button.clicked.connect(self.update_engines); self.self_btn=QPushButton("CHECK JAVBED UPDATE"); self.self_btn.setObjectName("secondary"); self.self_btn.clicked.connect(self.check_self); row.addWidget(refresh);row.addWidget(self.update_button);row.addWidget(self.self_btn)
        self.all_button=QPushButton("UPDATE ALL");self.all_button.setObjectName("play");self.all_button.clicked.connect(self.update_all);row.addWidget(self.all_button)
        row.addStretch();root.addLayout(row); self.refresh()
    def refresh(self):
        text=["JAVBED "+__version__,""]
        for label,path,tag in engine_status(): text.append(f"{label}: {path or 'not found'} {tag}".rstrip())
        self.output.setPlainText("\n".join(text))
    def update_engines(self, after=None):
        if self.update_job:return
        self.update_button.setEnabled(False);self.output.appendPlainText("\nUpdating managed engines...")
        job=EngineUpdateJob();self.update_job=job
        activity_id=self.activity.begin("Managed engines","GitHub releases","Updating",None) if self.activity else None
        job.signals.progress.connect(self.output.appendPlainText)
        if activity_id:job.signals.progress.connect(lambda line:self.activity.progress(activity_id,stage=line))
        if activity_id:job.signals.bytes_progress.connect(lambda label,received,total:self.activity.progress(activity_id,received,total,"Downloading "+label))
        def done(success):
            if self.global_running and not success:self.global_failed=True
            if activity_id:self.activity.finish(activity_id,success,"Update pass complete" if success else "Some engine updates failed")
            self.update_job=None;self.update_button.setEnabled(True)
            self.output.appendPlainText("\nUpdate pass complete.")
            if callable(after):after()
        job.signals.done.connect(done);self.pool.start(job)
    def check_self(self, after=None):
        if self.check_job:return
        self.self_btn.setEnabled(False);self.output.appendPlainText("\nChecking JAVBED release...")
        job=Job(lambda:javbed_update(__version__));self.check_job=job
        def done(ok,result):
            self.check_job=None;self.self_btn.setEnabled(True)
            if not ok:
                if self.global_running:self.global_failed=True
                self.output.appendPlainText("Update check failed: "+str(result))
                if callable(after):after()
                return
            tag,new,url=result
            if new:
                self.output.appendPlainText(f"JAVBED {tag} is available.")
                self.self_btn.setText("OPEN RELEASE")
                self.self_btn.clicked.disconnect()
                self.self_btn.clicked.connect(lambda:open_url(url))
            else:self.output.appendPlainText("JAVBED is up to date.")
            if callable(after):after()
        job.signals.done.connect(done);self.pool.start(job)

    def update_all(self):
        if self.global_running or self.check_job or self.update_job or not self.window:
            return
        self.global_running=True
        self.global_failed=False
        self.all_button.setEnabled(False)
        activity_id=self.activity.begin("Update All","JAVBED, engines, mods, SERVLI","Checking JAVBED") if self.activity else None

        def stage(message):
            self.output.appendPlainText(message)
            if activity_id:self.activity.progress(activity_id,stage=message)

        def finish():
            summary="Update pass finished with issues." if self.global_failed else "Update pass complete. Running servers were skipped."
            stage(summary)
            self.global_running=False
            self.all_button.setEnabled(True)
            if activity_id:self.activity.finish(activity_id,not self.global_failed,summary)

        def update_servers():
            stage("Checking server software...")
            job=Job(server_snapshot)

            def listed(ok, rows):
                if not ok:
                    self.global_failed=True
                    stage("Server updates unavailable: "+str(rows))
                    finish();return
                queue=[row for row in rows if not row.get("running") and row.get("provider")!="bds"]
                for row in rows:
                    if row.get("running"):
                        stage("Skipped running server: "+row["name"])
                    elif row.get("provider")=="bds":
                        stage("Skipped BDS version change: "+row["name"])

                def next_server():
                    if not queue:
                        finish();return
                    row=queue.pop(0)
                    stage("Updating server "+row["name"]+"...")
                    def updated(ok, output):
                        if not ok:self.global_failed=True
                        stage(("Updated " if ok else "Server update failed: ")+row["name"])
                        next_server()
                    self.window.server_page.run(["update",row["name"]],target=self.window.server_page.output,finished=updated)

                next_server()

            job.signals.done.connect(listed)
            self.pool.start(job)

        def update_mods():
            browser=self.window.java_page.mods_panel
            browser.refresh_instances(False)
            names=[browser.instance.itemText(index) for index in range(browser.instance.count())]
            stage("Checking tracked mods across "+str(len(names))+" Java instances...")

            def next_instance():
                if not names:
                    check_modpacks();return
                name=names.pop(0)
                browser.instance.blockSignals(True)
                browser.instance.setCurrentText(name)
                browser.instance.blockSignals(False)
                stage("Updating mods in "+name+"...")
                def updated():
                    if browser.status.text().startswith("Update failed"):
                        self.global_failed=True
                        stage(name+": "+browser.status.text())
                    next_instance()
                browser.update_all(updated)

            next_instance()

        def check_modpacks():
            stage("Checking installed modpacks...")

            def query():
                messages=[]
                key=str(load_settings().get("curseforge_api_key") or "")
                for item in instance_snapshot():
                    pack=item.get("preferences",{}).get("modpack") or {}
                    if not pack.get("project"):
                        continue
                    try:
                        latest=content.newest_compatible(pack["provider"],"modpack",pack["project"],str(item["version"]),str(item.get("loader") or "vanilla"),key)
                        if latest and latest["id"]!=pack.get("version_id"):
                            messages.append(item["name"]+": newer compatible modpack "+str(latest["version"])+" available in Modpacks")
                    except Exception as exc:
                        messages.append(item["name"]+": modpack check failed: "+str(exc)[:120])
                return messages

            job=Job(query)
            def checked(ok, messages):
                if not ok:
                    self.global_failed=True
                    stage("Modpack checks failed: "+str(messages))
                else:
                    for message in messages:stage(message)
                    if any("check failed" in message for message in messages):self.global_failed=True
                update_servers()
            job.signals.done.connect(checked)
            self.pool.start(job)

        self.check_self(lambda:self.update_engines(update_mods))

class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.data = load_settings()
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 28, 36, 28)
        title = QLabel("SETTINGS")
        title.setObjectName("heroTitle")
        root.addWidget(title)
        form = QFormLayout()
        self.memory = QSpinBox(); self.memory.setRange(512, 65536); self.memory.setSuffix(" MB"); self.memory.setValue(int(self.data["java_memory_mb"]))
        self.width = QSpinBox(); self.width.setRange(640, 7680); self.width.setValue(int(self.data["resolution_width"]))
        self.height = QSpinBox(); self.height.setRange(480, 4320); self.height.setValue(int(self.data["resolution_height"]))
        self.fullscreen = QCheckBox(); self.fullscreen.setChecked(bool(self.data["fullscreen"]))
        self.close_on_launch = QCheckBox(); self.close_on_launch.setChecked(bool(self.data["close_on_launch"]))
        self.check_updates = QCheckBox(); self.check_updates.setChecked(bool(self.data["check_updates"]))
        self.minecraft_dir = QLineEdit(str(self.data["minecraft_directory"]))
        self.java_runtime = QLineEdit(str(self.data["java_runtime"]))
        self.curseforge = QLineEdit(str(self.data["curseforge_api_key"])); self.curseforge.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Java memory", self.memory); form.addRow("Window width", self.width); form.addRow("Window height", self.height); form.addRow("Fullscreen", self.fullscreen); form.addRow("Close launcher on game start", self.close_on_launch); form.addRow("Check for updates", self.check_updates); form.addRow("Minecraft directory", self.minecraft_dir); form.addRow("Java runtime", self.java_runtime); form.addRow("CurseForge API key", self.curseforge)
        self.bedrock_worlds = QLineEdit(str(self.data.get("bedrock_worlds_path", "")))
        self.edu_worlds = QLineEdit(str(self.data.get("edu_worlds_path", "")))
        self.servli_home = QLineEdit(str(self.data.get("servli_home", "")))
        form.addRow("Bedrock worlds folder", self.bedrock_worlds)
        form.addRow("EDU worlds folder", self.edu_worlds)
        form.addRow("SERVLI home", self.servli_home)
        self.engine_fields = {}
        for label, key in (("JAVLI path","engine_java"),("BEDLI path","engine_bedrock"),("EDULI path","engine_edu"),("LEGLI path","engine_lce"),("SERVLI path","engine_servers")):
            field = QLineEdit(str(self.data.get(key,""))); self.engine_fields[key]=field; form.addRow(label, field)
        root.addLayout(form)
        actions = QHBoxLayout()
        save_btn = QPushButton("SAVE SETTINGS"); save_btn.setObjectName("play"); save_btn.clicked.connect(self.save)
        folder_btn = QPushButton("OPEN JAVBED DATA FOLDER"); folder_btn.setObjectName("secondary"); folder_btn.clicked.connect(self.open_data)
        actions.addWidget(save_btn); actions.addWidget(folder_btn); actions.addStretch(); root.addLayout(actions)
        self.status = QLabel(""); root.addWidget(self.status); root.addStretch()
    def save(self):
        self.data=load_settings()
        self.data.update({"java_memory_mb":self.memory.value(),"resolution_width":self.width.value(),"resolution_height":self.height.value(),"fullscreen":self.fullscreen.isChecked(),"close_on_launch":self.close_on_launch.isChecked(),"check_updates":self.check_updates.isChecked(),"minecraft_directory":self.minecraft_dir.text().strip(),"java_runtime":self.java_runtime.text().strip(),"curseforge_api_key":self.curseforge.text().strip(),"bedrock_worlds_path":self.bedrock_worlds.text().strip(),"edu_worlds_path":self.edu_worlds.text().strip(),"servli_home":self.servli_home.text().strip()})
        for key, field in self.engine_fields.items(): self.data[key]=field.text().strip()
        save_settings(self.data); apply_environment(self.data); self.status.setText("Settings saved.")
    def open_data(self):
        from .settings import ROOT
        ROOT.mkdir(parents=True,exist_ok=True)
        if sys.platform=="win32": os.startfile(ROOT)
        elif sys.platform=="darwin": subprocess.Popen(["open",str(ROOT)])
        else: subprocess.Popen(["xdg-open",str(ROOT)])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.activity=ActivityManager(self);self.setWindowTitle("JAVBED Launcher");self.resize(1280,750);self.setMinimumSize(1000,620);self.setAcceptDrops(True)
        root=QWidget();layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        rail=QFrame();rail.setObjectName("rail");rail.setFixedWidth(178);r=QVBoxLayout(rail);r.setContentsMargins(0,0,0,0);r.setSpacing(0)
        account=QFrame();account.setObjectName("account");a=QVBoxLayout(account)
        name=QLabel("JAVBED");name.setObjectName("logo");a.addWidget(name)
        self.account_button=QPushButton("No Java account  ▾")
        self.account_button.setObjectName("secondary")
        self.account_button.clicked.connect(self.show_account_menu)
        a.addWidget(self.account_button)
        r.addWidget(account)
        from PySide6.QtWidgets import QScrollArea
        nav_scroll=QScrollArea();nav_scroll.setWidgetResizable(True);nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }")
        nav_content=QWidget();nav_layout=QVBoxLayout(nav_content);nav_layout.setContentsMargins(0,0,0,0);nav_layout.setSpacing(0)
        nav_scroll.setWidget(nav_content);r.addWidget(nav_scroll,1)
        self.stack=QStackedWidget();self.buttons=[];self.pages=[]
        entries=("Home","Java","Bedrock","EDU","LCE","Dungeons","Dungeons 2","Legends","Story Mode","Worlds","Servers","Updates","Activity","Doctor","Settings")
        for i,label in enumerate(entries):
            display=label.upper() if label in ("Home","Settings","Updates","Activity","Doctor","Worlds") else (("MINECRAFT:\n" if label not in ("Servers","Dungeons","Dungeons 2","Legends","Story Mode") else "MINECRAFT\n" if label!="Servers" else "")+label.upper())
            b=QPushButton(display);b.setObjectName("nav");b.setCheckable(True);b.clicked.connect(lambda checked=False,x=i:self.select(x));nav_layout.addWidget(b);self.buttons.append(b)
            if label == "Home":
                page = HomePage(self, home_snapshot)
            elif label == "Worlds":
                page = WorldPage(self.play_world, self)
            elif label == "Story Mode":
                page = StoryModePage(self.activity)
            elif label == "Activity":
                page = ActivityPage(self.activity)
            elif label == "Doctor":
                page = DoctorPage(self.activity)
            elif label == "Settings":
                page = SettingsPage()
            elif label == "Updates":
                page = UpdatesPage(self.activity, self)
            elif label in EXTRA_GAMES:
                page = ExtraPage(label)
            else:
                page = GamePage(label, self.activity)
            self.pages.append(page)
            self.stack.addWidget(page)
            if label=="Java":self.java_page=page
            if label=="Servers":self.server_page=page
            if label=="Story Mode":self.story_page=page
        nav_layout.addStretch();layout.addWidget(rail);layout.addWidget(self.stack,1);self.setCentralWidget(root);self.select(0);QTimer.singleShot(300,self.refresh_all);QTimer.singleShot(500,self.recover_safe_modes)
    def recover_safe_modes(self):
        for name, pid in safemode.pending():
            def restore_after_exit(started, code, target=name):
                try:safemode.restore(target)
                except (OSError, ValueError):pass
            attached = pid > 0 and history.watch_pid(pid, "Java", instance=name, on_exit=restore_after_exit, record_session=False)
            if not attached:
                self.java_page.pool.start(Job(lambda target=name: safemode.restore(target)))
    def update_account(self, account, avatar):
        self.account_button.setText((account["username"] + "  ▾") if account else "No Java account  ▾")
        self.account_button.setIcon(QIcon(avatar) if avatar else QIcon())
    def open_accounts(self):
        self.select_name("Java")
        self.java_page.switch_view("accounts")
    def show_account_menu(self):
        from .accounts import accounts
        active, rows = accounts()
        menu = QMenu(self)
        for row in rows:
            alias = row["alias"]
            action = menu.addAction(("✓ " if alias == active else "") + row["username"] + " (" + alias + ")")
            action.triggered.connect(lambda checked=False, value=alias: self.switch_account(value))
        if rows:
            menu.addSeparator()
        menu.addAction("Add Account", self.open_accounts)
        menu.addAction("Refresh Account", self.refresh_active_account)
        menu.addAction("Account Manager", self.open_accounts)
        menu.exec(self.account_button.mapToGlobal(self.account_button.rect().bottomLeft()))
    def switch_account(self, alias):
        self.java_page.run(["account", "use", alias], target=self.java_page.account_output)
        if self.java_page.proc:
            self.java_page.proc.finished.connect(lambda *_: self.pages[0].refresh())
    def refresh_active_account(self):
        self.java_page.run(["account", "refresh"], target=self.java_page.account_output)
        if self.java_page.proc:
            self.java_page.proc.finished.connect(lambda *_: self.pages[0].refresh())
    def refresh_all(self):
        for p in self.pages:
            if isinstance(p,GamePage):p.startup_refresh()
            elif isinstance(p,ExtraPage):p.refresh()
    def select_name(self,name):
        entries=("Home","Java","Bedrock","EDU","LCE","Dungeons","Dungeons 2","Legends","Story Mode","Worlds","Servers","Updates","Activity","Doctor","Settings")
        if name in entries:self.select(entries.index(name))
    def play_world(self, world):
        if world.edition == "Java" and world.instance:
            self.select_name("Java")
            self.java_page.run(["instance", "launch", world.instance])
        elif world.edition == "Java":
            self.select_name("Java")
            self.java_page.run(["release", world.version or "latest"])
        elif world.edition in ("Bedrock", "EDU"):
            self.select_name(world.edition)
            page = self.pages[self.stack.currentIndex()]
            if world.edition == "Bedrock":
                page.run(["release", "latest"])
            else:
                page.run([page.version.currentText().strip()])
    def dragEnterEvent(self, event):
        supported = {".jar", ".mrpack", ".javbed", ".zip", ".iso"}
        if event.mimeData().hasUrls() and any(Path(url.toLocalFile()).suffix.lower() in supported for url in event.mimeData().urls() if url.isLocalFile()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_dropped_file(Path(url.toLocalFile()))
        event.acceptProposedAction()

    def open_dropped_file(self, source):
        if not source.is_file():
            return
        suffix = source.suffix.lower()
        if suffix == ".javbed":
            self.select_name("Java")
            self.java_page.switch_view("instances")
            self.java_page.instances_panel.import_portable(str(source))
        elif suffix == ".mrpack":
            self.select_name("Java")
            self.java_page.switch_view("modpacks")
            self.java_page.modpacks_panel.open_mrpack(str(source))
        elif suffix == ".iso":
            self.select_name("Story Mode")
            self.story_page.install_iso(str(source))
        elif suffix == ".zip":
            choice, ok = QInputDialog.getItem(self, "Install ZIP", source.name + " is a:", ["World", "Resource pack", "Shader pack"], 0, False)
            if not ok:return
            if choice == "World":
                self.select_name("Worlds")
                self.pages[self.stack.currentIndex()].import_zip(str(source))
            else:
                self.copy_addon(source, "resourcepacks" if choice == "Resource pack" else "shaderpacks")
        elif suffix == ".jar":
            self.copy_addon(source, "mods")

    def copy_addon(self, source, folder):
        from .instances import list_instances
        rows = list_instances()
        names = [str(row["name"]) for row in rows]
        if not names:
            self.select_name("Java")
            self.java_page.switch_view("instances")
            return
        name, ok = QInputDialog.getItem(self, "Choose Java instance", "Install " + source.name + " into", names, 0, False)
        if not ok:return
        instance = next(row for row in rows if row["name"] == name)
        destination = Path(str(instance["path"])) / "minecraft" / folder / source.name
        if destination.exists():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Already installed", source.name + " already exists in " + name + ".")
            return
        job = Job(lambda: self._copy_addon_file(source, destination))
        job.signals.done.connect(lambda success, result: self.java_page.status.setText(("Installed " if success else "Install failed: ") + str(result)[:180]))
        self.java_page.pool.start(job)
        self.select_name("Java")

    @staticmethod
    def _copy_addon_file(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as original, destination.open("xb") as target:
            try:
                shutil.copyfileobj(original, target)
            except Exception:
                target.close()
                destination.unlink(missing_ok=True)
                raise
        return destination.name
    def select(self,i):
        self.stack.setCurrentIndex(i)
        for n,b in enumerate(self.buttons):b.setChecked(n==i)
        if i == 0 and self.pages:
            self.pages[0].refresh()
    def closeEvent(self,event):
        if hasattr(self,"story_page") and self.story_page.download_job:
            self.story_page.download_job.cancelled.set()
        for process in self.findChildren(QProcess):
            if process.state()!=QProcess.ProcessState.NotRunning:
                process.blockSignals(True)
                process.kill()
                process.waitForFinished(1000)
        super().closeEvent(event)

def main():
    app=QApplication(sys.argv);app.setApplicationName("JAVBED");app.setStyleSheet(STYLE);apply_environment(load_settings());w=MainWindow();w.show();raise SystemExit(app.exec())
if __name__=="__main__":main()
