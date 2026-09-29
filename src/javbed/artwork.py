from __future__ import annotations
import sys
from pathlib import Path

FILES = {
    "Java": "java.webp",
    "Bedrock": "bedrock.webp",
    "EDU": "edu.webp",
    "LCE": "lce.webp",
    "Dungeons": "dungeons.webp",
    "Dungeons 2": "dungeons2.webp",
    "Legends": "legends.webp",
}

def artwork_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "javbed_artwork"
    return Path(__file__).resolve().parent / "assets" / "artwork"

def cached_art(label):
    name = FILES.get(label)
    if not name:
        return None
    path = artwork_dir() / name
    return path if path.exists() else None

def load_async(label, callback):
    path = cached_art(label)
    callback(str(path) if path else "")
    return None
