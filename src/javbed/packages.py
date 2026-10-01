"""Versioned .javbed instance packages containing metadata, never game binaries."""

from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

from . import content_registry, settings
from .instances import valid_name

FORMAT = "javbed-instance"
VERSION = 1
CONTENT_KINDS = {"mod", "resourcepack", "shader"}
ERAS = {"release", "snapshot", "beta", "alpha", "infdev", "indev", "classic", "preclassic"}


def build_manifest(instance: dict) -> dict:
    name = str(instance["name"])
    pref = instance.get("preferences", {})
    tracked = [row for row in content_registry.load() if row.get("instance") == name and row.get("kind") in CONTENT_KINDS]
    return {
        "format": FORMAT,
        "format_version": VERSION,
        "name": name,
        "minecraft": {"version": str(instance["version"]), "type": str(instance.get("era") or "release"), "loader": str(instance.get("loader") or "vanilla"), "loader_version": str(instance.get("loader_version") or "")},
        "settings": {key: pref.get(key) for key in ("memory_mb", "width", "height", "java_major") if pref.get(key) is not None},
        "modpack": pref.get("modpack") if isinstance(pref.get("modpack"), dict) else None,
        "content": [{key: row.get(key, "") for key in ("kind", "provider", "project", "version_id", "file_name", "project_name")} for row in tracked],
        "untracked": [],
    }


def validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or manifest.get("format_version") != VERSION:
        raise ValueError("Unsupported .javbed format version.")
    if not valid_name(str(manifest.get("name", ""))):
        raise ValueError("Invalid instance name in package.")
    minecraft = manifest.get("minecraft")
    if not isinstance(minecraft, dict) or not isinstance(minecraft.get("version"), str) or not minecraft["version"] or len(minecraft["version"]) > 100 or minecraft.get("type") not in ERAS or minecraft.get("loader", "vanilla") not in ("vanilla", "fabric", "quilt", "forge", "neoforge"):
        raise ValueError("Invalid Minecraft version or loader in package.")
    config = manifest.get("settings")
    if not isinstance(config, dict):
        raise ValueError("Invalid package settings.")
    for key, minimum, maximum in (("memory_mb", 512, 65536), ("width", 640, 7680), ("height", 480, 4320)):
        if key in config and (not isinstance(config[key], int) or not minimum <= config[key] <= maximum):
            raise ValueError("Invalid " + key + " in package.")
    if "java_major" in config and config["java_major"] not in (8, 17, 21, 25):
        raise ValueError("Unsupported Java runtime in package.")
    modpack = manifest.get("modpack")
    if modpack is not None and (not isinstance(modpack, dict) or modpack.get("provider") not in ("modrinth", "curseforge") or not modpack.get("project") or not modpack.get("version_id")):
        raise ValueError("Package modpack has no reproducible provider reference.")
    if not isinstance(manifest.get("content"), list):
        raise ValueError("Package content must be a list.")
    for row in manifest["content"]:
        if not isinstance(row, dict) or row.get("kind") not in CONTENT_KINDS or row.get("provider") not in ("modrinth", "curseforge") or not row.get("project") or not row.get("version_id"):
            raise ValueError("Package contains an invalid add-on reference.")
        if row["provider"] == "curseforge" and row["kind"] != "mod":
            raise ValueError("CurseForge resource packs and shaders are not supported.")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", str(row["project"])) or not re.fullmatch(r"[A-Za-z0-9._+-]{0,128}", str(row.get("version_id", ""))):
            raise ValueError("Invalid add-on identifier in package.")
    return manifest


def export_package(instance: dict, destination: Path) -> Path:
    manifest = validate_manifest(build_manifest(instance))
    game = Path(str(instance["path"])) / "minecraft"
    folders = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
    tracked = {(row["kind"], row.get("file_name", "")) for row in manifest["content"]}
    for kind, folder in folders.items():
        root = game / folder
        if root.is_dir():
            manifest["untracked"].extend({"kind": kind, "file_name": path.name} for path in root.iterdir() if path.is_file() and path.suffix.lower() in (".jar", ".zip") and (kind, path.name) not in tracked)
    icon = Path(str(instance.get("preferences", {}).get("icon") or ""))
    if icon.is_file() and icon.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and icon.stat().st_size <= 2 * 1024 * 1024:
        manifest["icon"] = "icon" + icon.suffix.lower()
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Destination already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            if manifest.get("icon"):
                archive.write(icon, manifest["icon"])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_package(source: Path) -> tuple[dict, bytes | None]:
    with zipfile.ZipFile(source) as archive:
        if "manifest.json" not in archive.namelist():
            raise ValueError("Package has no manifest.json.")
        if archive.getinfo("manifest.json").file_size > 1024 * 1024:
            raise ValueError("Package manifest is too large.")
        manifest = validate_manifest(json.loads(archive.read("manifest.json")))
        icon_name = manifest.get("icon")
        icon = None
        if icon_name:
            if icon_name not in archive.namelist() or not str(icon_name).startswith("icon."):
                raise ValueError("Invalid package icon.")
            if archive.getinfo(icon_name).file_size > 2 * 1024 * 1024:
                raise ValueError("Package icon is too large.")
            icon = archive.read(icon_name)
    return manifest, icon


def restore_icon(name: str, manifest: dict, icon: bytes | None) -> Path | None:
    if not icon:
        return None
    suffix = Path(str(manifest.get("icon", ""))).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("Unsupported icon format.")
    path = settings.ROOT / "instance_icons" / (name + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(icon)
    return path
