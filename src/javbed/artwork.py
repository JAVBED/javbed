from __future__ import annotations
import io, os, urllib.request, zipfile
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

ROOT=Path(os.getenv("LOCALAPPDATA") or (Path.home()/".local"/"share"))/"JAVBED"/"artwork"
BUNDLES={
"Java":"https://www.minecraft.net/content/dam/minecraftnet/games/minecraft/software/wallpapers_minecraft_pc_bundle.zip",
"Bedrock":"https://www.minecraft.net/content/dam/minecraftnet/games/minecraft/software/wallpapers_minecraft_bedrock_edition.zip",
"Dungeons":"https://www.minecraft.net/content/dam/minecraftnet/games/dungeons/software/wallpaper_dungeons.zip",
"Legends":"https://www.minecraft.net/content/dam/minecraftnet/games/badger/software/wallpapers_legends_cover_.zip",
}
ALIASES={"EDU":"Java","LCE":"Java","Servers":"Bedrock","Dungeons 2":"Dungeons"}

class ArtSignals(QObject):
    done=Signal(str)

class ArtJob(QRunnable):
    def __init__(self,label):
        super().__init__();self.label=label;self.signals=ArtSignals()
    def run(self):
        try:self.signals.done.emit(str(fetch_art(self.label) or ""))
        except Exception:self.signals.done.emit("")

def cached_art(label):
    key=ALIASES.get(label,label)
    for ext in (".jpg",".jpeg",".png",".webp"):
        p=ROOT/(key.lower().replace(" ","_")+ext)
        if p.exists():return p
    return None

def fetch_art(label):
    key=ALIASES.get(label,label);cached=cached_art(label)
    if cached:return cached
    url=BUNDLES.get(key)
    if not url:return None
    ROOT.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(url,headers={"User-Agent":"JAVBED Launcher"})
    with urllib.request.urlopen(req,timeout=30) as response:data=response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        candidates=[i for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in (".jpg",".jpeg",".png",".webp")]
        if not candidates:return None
        # Wallpaper bundles commonly contain several resolutions. The largest file is normally the highest-resolution hero.
        chosen=max(candidates,key=lambda i:i.file_size)
        ext=Path(chosen.filename).suffix.lower()
        target=ROOT/(key.lower().replace(" ","_")+ext)
        target.write_bytes(z.read(chosen))
        return target

def load_async(label,callback):
    job=ArtJob(label);job.signals.done.connect(callback);QThreadPool.globalInstance().start(job)
    return job
