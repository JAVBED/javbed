"""Discover, back up, and safely copy Minecraft worlds."""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import shutil
import struct
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import settings
from .instances import list_instances


@dataclass(frozen=True)
class World:
    name: str
    edition: str
    instance: str
    path: Path
    root: Path
    version: str
    last_played: float
    size: int
    icon: Path | None


def java_root() -> Path:
    configured = str(settings.load().get("minecraft_directory") or "").strip()
    if configured and Path(configured).is_absolute():
        return Path(configured) / "saves"
    if sys.platform == "win32":
        return Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming") / ".minecraft" / "saves"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "minecraft" / "saves"
    return Path.home() / ".minecraft" / "saves"


def available_roots() -> list[tuple[str, str, Path]]:
    roots = [("Java", "", java_root())]
    for item in list_instances():
        roots.append(("Java", str(item["name"]), Path(str(item["path"])) / "minecraft" / "saves"))
    configured = settings.load()
    for edition, key in (("Bedrock", "bedrock_worlds_path"), ("EDU", "edu_worlds_path")):
        value = str(configured.get(key) or "").strip()
        if value:
            roots.append((edition, "", Path(value)))
    if sys.platform == "win32":
        packages = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Packages"
        for pattern, edition in (("Microsoft.MinecraftUWP_*", "Bedrock"), ("Microsoft.MinecraftEducationEdition_*", "EDU")):
            for package in packages.glob(pattern):
                root = package / "LocalState" / "games" / "com.mojang" / "minecraftWorlds"
                if root.is_dir() and not any(existing == root for _, _, existing in roots):
                    roots.append((edition, "", root))
    return roots


def _nbt_metadata(path: Path) -> tuple[str, float, str]:
    try:
        with gzip.open(path, "rb") as source:
            data = source.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            return "", 0, ""
        cursor = 0

        def read(fmt):
            nonlocal cursor
            size = struct.calcsize(fmt)
            value = struct.unpack_from(fmt, data, cursor)[0]
            cursor += size
            return value

        def string():
            nonlocal cursor
            length = read(">H")
            value = data[cursor:cursor + length].decode("utf-8", errors="replace")
            cursor += length
            return value

        def payload(tag, depth=0):
            nonlocal cursor
            if depth > 64:
                raise ValueError("NBT nesting is too deep")
            if tag in (1, 2, 3, 4):
                return read({1: ">b", 2: ">h", 3: ">i", 4: ">q"}[tag])
            if tag in (5, 6):
                return read({5: ">f", 6: ">d"}[tag])
            if tag == 8:
                return string()
            if tag in (7, 11, 12):
                length = read(">i")
                if length < 0 or length > 4 * 1024 * 1024:
                    raise ValueError("Invalid NBT array")
                cursor += length * {7: 1, 11: 4, 12: 8}[tag]
                return None
            if tag == 9:
                child = read(">B")
                length = read(">i")
                if length < 0 or length > 10000:
                    raise ValueError("Invalid NBT list")
                return [payload(child, depth + 1) for _ in range(length)]
            if tag == 10:
                result = {}
                while True:
                    child = read(">B")
                    if child == 0:
                        return result
                    name = string()
                    value = payload(child, depth + 1)
                    if name in ("Data", "Version", "LevelName", "LastPlayed", "Name"):
                        result[name] = value
            raise ValueError("Unsupported NBT tag")

        if read(">B") != 10:
            return "", 0, ""
        string()
        root = payload(10)
        level = root.get("Data", root)
        if not isinstance(level, dict):
            return "", 0, ""
        version = level.get("Version") or {}
        return str(level.get("LevelName") or ""), float(level.get("LastPlayed") or 0) / 1000, str(version.get("Name") or "") if isinstance(version, dict) else ""
    except (OSError, EOFError, ValueError, struct.error, OverflowError):
        return "", 0, ""


def discover_worlds() -> list[World]:
    worlds = []
    for edition, instance, root in available_roots():
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_dir() or not ((path / "level.dat").is_file() or (path / "db").is_dir()):
                continue
            level = path / "level.dat"
            name, last_played, version = _nbt_metadata(level) if edition == "Java" and level.is_file() else ("", 0, "")
            if not name and (path / "levelname.txt").is_file():
                try:
                    name = (path / "levelname.txt").read_text(encoding="utf-8").strip()
                except OSError:
                    pass
            size = 0
            for folder, _, files in os.walk(path):
                for filename in files:
                    try:
                        size += (Path(folder) / filename).stat().st_size
                    except OSError:
                        pass
            icon = path / "icon.png"
            modified = level.stat().st_mtime if level.is_file() else path.stat().st_mtime
            worlds.append(World(name or path.name, edition, instance, path, root, version, last_played or modified, size, icon if icon.is_file() else None))
    return sorted(worlds, key=lambda world: world.last_played, reverse=True)


def _check_world(world: World) -> None:
    if world.path.resolve().parent != world.root.resolve() or not world.path.is_dir():
        raise ValueError("World path is outside its expected saves folder.")


def backup_folder(world: World) -> Path:
    digest = hashlib.sha256(str(world.path.resolve()).encode("utf-8")).hexdigest()[:16]
    return settings.ROOT / "backups" / "worlds" / digest


def _write_zip(folder: Path, destination: Path) -> Path:
    if destination.exists():
        raise FileExistsError("Backup destination already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".world-", suffix=".zip", dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(folder):
                for name in files:
                    path = Path(root) / name
                    if not path.is_symlink():
                        archive.write(path, path.relative_to(folder).as_posix())
        with temporary.open("rb") as source, destination.open("xb") as target:
            try:
                shutil.copyfileobj(source, target)
            except Exception:
                target.close()
                destination.unlink(missing_ok=True)
                raise
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def backup_world(world: World) -> Path:
    _check_world(world)
    folder = backup_folder(world)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return _write_zip(world.path, folder / (stamp + ".zip"))


def export_world(world: World, destination: Path) -> Path:
    _check_world(world)
    return _write_zip(world.path, destination)


def _safe_member(name: str) -> Path:
    value = PurePosixPath(name.replace("\\", "/"))
    if value.is_absolute() or not value.parts or ".." in value.parts or ":" in value.parts[0]:
        raise ValueError("Unsafe world archive path: " + name)
    return Path(*value.parts)


def _extract_world(archive_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 100000 or sum(member.file_size for member in members) > 64 * 1024**3:
            raise ValueError("World archive is too large.")
        for member in members:
            _safe_member(member.filename)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("World archive contains a link.")
        for member in members:
            target = destination / _safe_member(member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    if (destination / "level.dat").is_file() or (destination / "db").is_dir():
        return destination
    children = [path for path in destination.iterdir() if path.is_dir()]
    if len(children) == 1 and ((children[0] / "level.dat").is_file() or (children[0] / "db").is_dir()):
        return children[0]
    raise ValueError("ZIP does not contain a Minecraft world.")


def restore_world(world: World, archive_path: Path) -> Path:
    _check_world(world)
    backup_world(world)  # Protect the current world before replacing anything.
    with tempfile.TemporaryDirectory(prefix=".world-restore-", dir=world.root) as staging_name:
        staging = Path(staging_name)
        candidate = _extract_world(archive_path, staging)
        holding = world.root / (".pre-restore-" + uuid.uuid4().hex)
        if holding.resolve().parent != world.root.resolve() or candidate.resolve() == world.path.resolve():
            raise ValueError("Unsafe restore target.")
        world.path.rename(holding)
        try:
            candidate.rename(world.path)
        except Exception:
            holding.rename(world.path)
            raise
        if holding.resolve().parent != world.root.resolve():
            raise ValueError("Unsafe restore cleanup target.")
        shutil.rmtree(holding)
    return world.path


def unique_world_name(root: Path, suggestion: str) -> str:
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", suggestion).strip(" .")[:80] or "Imported World"
    name = base
    number = 2
    while (root / name).exists():
        name = f"{base} ({number})"
        number += 1
    return name


def import_world(archive_path: Path, root: Path, suggestion: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".world-import-", dir=root) as staging_name:
        candidate = _extract_world(archive_path, Path(staging_name))
        destination = root / unique_world_name(root, suggestion or archive_path.stem)
        if destination.resolve().parent != root.resolve():
            raise ValueError("Unsafe world import destination.")
        candidate.rename(destination)
    return destination


def duplicate_world(world: World) -> Path:
    _check_world(world)
    destination = world.root / unique_world_name(world.root, world.name + " Copy")
    if destination.resolve().parent != world.root.resolve():
        raise ValueError("Unsafe world duplicate destination.")
    shutil.copytree(world.path, destination)
    return destination


def trash_world(world: World) -> Path:
    _check_world(world)
    trash = settings.ROOT / "trash" / "worlds"
    trash.mkdir(parents=True, exist_ok=True)
    destination = trash / (uuid.uuid4().hex + "-" + unique_world_name(trash, world.name))
    if destination.resolve().parent != trash.resolve():
        raise ValueError("Unsafe world trash destination.")
    shutil.move(str(world.path), str(destination))
    return destination
