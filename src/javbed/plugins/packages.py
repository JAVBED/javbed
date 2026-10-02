"""Validate and install plugin directories or ZIP/.javbedplugin packages."""

import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .manifest import PluginManifest

MAX_FILES = 2000
MAX_UNPACKED = 256 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_ARCHIVE = 100 * 1024 * 1024


def _member(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe plugin archive path")
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or "." in path.parts or ".." in path.parts or ":" in path.parts[0]:
        raise ValueError("Unsafe plugin archive path")
    return path


def inspect(source: Path) -> PluginManifest:
    source = Path(source)
    if source.is_dir():
        if source.is_symlink():
            raise ValueError("Plugin directory cannot be a symlink")
        return PluginManifest.read(source)
    if source.suffix.lower() not in (".zip", ".javbedplugin") or not source.is_file() or source.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Choose a plugin directory, ZIP, or .javbedplugin package")
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_UNPACKED:
            raise ValueError("Plugin package is too large")
        seen = set()
        for item in members:
            path = _member(item.filename)
            lowered = path.as_posix().rstrip("/").lower()
            if lowered in seen:
                raise ValueError("Duplicate plugin archive path")
            seen.add(lowered)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("Plugin archive contains a link or special file")
            if item.file_size > MAX_FILE or (item.compress_size and item.file_size > item.compress_size * 1000):
                raise ValueError("Plugin archive contains an oversized file")
        if "javbed-plugin.json" not in seen:
            raise ValueError("Package must contain javbed-plugin.json at its root")
        data = archive.read("javbed-plugin.json")
        if len(data) > 64 * 1024:
            raise ValueError("Plugin manifest is too large")
        import json
        manifest = PluginManifest.from_data(json.loads(data.decode("utf-8")))
        if manifest.entrypoint.lower() not in seen:
            raise ValueError("Missing plugin entrypoint")
        return manifest


def install(source: Path, plugin_root: Path, *, replace=False) -> PluginManifest:
    source = Path(source)
    plugin_root = Path(plugin_root)
    if plugin_root.is_symlink():
        raise ValueError("Plugin directory cannot be a symlink")
    manifest = inspect(source)
    plugin_root.mkdir(parents=True, exist_ok=True)
    target = plugin_root / manifest.id
    if target.is_symlink() or (target.exists() and not replace):
        raise FileExistsError("Plugin ID is already installed: " + manifest.id)
    with tempfile.TemporaryDirectory(prefix=".plugin-stage-", dir=plugin_root) as temporary:
        stage = Path(temporary) / "plugin"
        stage.mkdir()
        if source.is_dir():
            count, size = 0, 0
            for path in source.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Plugin directory contains a symlink")
                relative = path.relative_to(source)
                if path.is_dir():
                    (stage / relative).mkdir(parents=True, exist_ok=True)
                elif path.is_file():
                    count += 1
                    size += path.stat().st_size
                    if count > MAX_FILES or size > MAX_UNPACKED or path.stat().st_size > MAX_FILE:
                        raise ValueError("Plugin directory is too large")
                    destination = stage / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
                else:
                    raise ValueError("Plugin directory contains a special file")
        else:
            archive_source = Path(temporary) / "package.zip"
            with source.open("rb") as original, archive_source.open("xb") as output:
                copied = 0
                while chunk := original.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_ARCHIVE:
                        raise ValueError("Plugin package is too large")
                    output.write(chunk)
            if inspect(archive_source) != manifest:
                raise ValueError("Plugin package changed during installation")
            with zipfile.ZipFile(archive_source) as archive:
                for item in archive.infolist():
                    relative = _member(item.filename)
                    destination = stage.joinpath(*relative.parts)
                    if not destination.resolve().is_relative_to(stage.resolve()):
                        raise ValueError("Unsafe plugin archive path")
                    if item.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(item) as input_file, destination.open("xb") as output:
                            shutil.copyfileobj(input_file, output)
        installed = PluginManifest.read(stage)
        if installed != manifest:
            raise ValueError("Plugin manifest changed during installation")
        backup = plugin_root / (".plugin-backup-" + uuid.uuid4().hex)
        old = target.exists()
        if old:
            os.replace(target, backup)
        try:
            os.replace(stage, target)
        except Exception:
            if old:
                os.replace(backup, target)
            raise
        if old:
            try:
                shutil.rmtree(backup)
            except OSError:
                pass  # The new plugin is complete; retain the previous copy.
    return manifest


def uninstall(plugin_root: Path, identifier: str):
    from .manifest import ID
    if not ID.fullmatch(identifier):
        raise ValueError("Invalid plugin ID")
    target = Path(plugin_root) / identifier
    if target.is_symlink():
        raise ValueError("Refusing to uninstall a symlink")
    shutil.rmtree(target)
