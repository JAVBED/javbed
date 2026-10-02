"""Permission checked, stable facades exposed to third-party code."""

import json
import os
import tempfile
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .api import JAVBED_PLUGIN_API, InstanceInfo, ModInfo, ServerInfo, WorldInfo
from .manifest import ID


@dataclass(frozen=True)
class PluginPaths:
    data: Path


class PluginSettings:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    @property
    def _file(self):
        return self.manager.data_root / self.owner / "settings.json"

    def get(self, key, default=None):
        self.manager.require(self.owner, "settings.read")
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return data.get(key, default) if isinstance(data, dict) else default
        except (OSError, ValueError):
            return default

    def set(self, key, value):
        self.manager.require(self.owner, "settings.write")
        if not isinstance(key, str) or not key or len(key) > 120:
            raise ValueError("Invalid setting key")
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        self._file.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".settings-", dir=self._file.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(data, output, indent=2)
            os.replace(temporary, self._file)
        finally:
            temporary.unlink(missing_ok=True)


class EventsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def subscribe(self, event, callback):
        self.manager.check_active(self.owner)
        family = event.split(".", 1)[0] if isinstance(event, str) else ""
        needed = {"account": "accounts.read", "game": "instances.read", "instance": "instances.read", "mod": "mods.read", "world": "worlds.read", "server": "servers.read", "download": "network"}.get(family)
        if needed:
            self.manager.require(self.owner, needed)
        if family == "download":
            self.manager.require(self.owner, "files.read")
        return self.manager.events.subscribe(self.owner, event, callback)

    def unsubscribe(self, token):
        self.manager.events.unsubscribe(token, self.owner)


class CommandsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def register(self, **kwargs):
        self.manager.require(self.owner, "commands")
        return self.manager.commands.register(self.owner, **kwargs)


class UIFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def _register(self, kind, *, id, title, callback):
        self.manager.require(self.owner, "ui")
        required = {"instance_action": "instances.read", "server_action": "servers.read", "world_action": "worlds.read"}.get(kind)
        if required:
            self.manager.require(self.owner, required)
        return self.manager.ui.register(self.owner, kind, id=id, title=title, callback=callback)

    def register_page(self, *, id, title, widget_factory):
        return self._register("page", id=id, title=title, callback=widget_factory)

    def register_settings_page(self, *, id, title, widget_factory):
        return self._register("settings_page", id=id, title=title, callback=widget_factory)

    def register_instance_action(self, *, id, title, callback):
        return self._register("instance_action", id=id, title=title, callback=callback)

    def register_server_action(self, *, id, title, callback):
        return self._register("server_action", id=id, title=title, callback=callback)

    def register_world_action(self, *, id, title, callback):
        return self._register("world_action", id=id, title=title, callback=callback)

    def register_context_action(self, *, target, id, title, callback):
        if target not in ("instance", "server", "world"):
            raise ValueError("Context action target must be instance, server or world")
        return self._register(target + "_action", id=id, title=title, callback=callback)

class InstancesFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def list(self):
        self.manager.require(self.owner, "instances.read")
        from javbed.instances import list_instances
        return [InstanceInfo(str(row["name"]), str(row.get("version") or ""), str(row.get("loader") or "vanilla"), str(row.get("era") or "release"), str(row.get("path") or "")) for row in list_instances()]

    def get(self, name):
        return next((row for row in self.list() if row.name == name), None)

    def launch(self, name):
        self.manager.require(self.owner, "instances.launch")
        self._name(name)
        return self.manager.backend_future("Java", "instance", "launch", name)

    def open_folder(self, name):
        item = self.get(name)
        if not item:
            raise ValueError("Instance not found")
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        path = Path(item.path)
        if not path.is_dir():
            raise FileNotFoundError(path)
        self.manager._dispatcher.post(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        return path

    def create(self, name, era, version, loader="vanilla"):
        self.manager.require(self.owner, "instances.modify")
        self._name(name)
        if loader not in ("vanilla", "fabric", "quilt", "forge", "neoforge"):
            raise ValueError("Unsupported loader")
        args = ("instance", "create", name, era, version) + (("--loader", loader) if loader != "vanilla" else ())
        return self.manager.backend_future("Java", *args)

    def clone(self, name, new_name):
        self.manager.require(self.owner, "instances.modify")
        self._name(name); self._name(new_name)
        return self.manager.backend_future("Java", "instance", "clone", name, new_name)

    def delete(self, name):
        self.manager.require(self.owner, "instances.modify")
        self._name(name)
        return self.manager.backend_future("Java", "instance", "delete", name)

    @staticmethod
    def _name(name):
        from javbed.instances import valid_name
        if not isinstance(name, str) or not valid_name(name):
            raise ValueError("Invalid instance name")


class ServersFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def list(self):
        self.manager.require(self.owner, "servers.read")
        from javbed.servers import server_snapshot
        return [ServerInfo(str(row["name"]), str(row.get("provider") or ""), str(row.get("minecraftVersion") or ""), bool(row.get("running")), int(row["port"]) if row.get("port") else None) for row in server_snapshot()]

    def get(self, name):
        return next((row for row in self.list() if row.name == name), None)

    def _run(self, permission, command, name, *args):
        self.manager.require(self.owner, permission)
        if not isinstance(name, str) or not name or len(name) > 100 or any(char in name for char in "/\\\x00\r\n"):
            raise ValueError("Invalid server name")
        return self.manager.backend_future("Servers", command, name, *args)

    def start(self, name): return self._run("servers.modify", "start", name)
    def stop(self, name): return self._run("servers.modify", "stop", name)
    def restart(self, name): return self._run("servers.modify", "restart", name)
    def backup(self, name): return self._run("servers.modify", "backup", name)
    def send_command(self, name, command):
        if not isinstance(command, str) or not command.strip() or "\n" in command or "\r" in command:
            raise ValueError("Invalid console command")
        return self._run("servers.console", "send", name, command)


class AccountsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def list(self):
        self.manager.require(self.owner, "accounts.read")
        from javbed.accounts import accounts
        _, rows = accounts()
        return tuple({"alias": row["alias"], "username": row["username"], "uuid": row["uuid"]} for row in rows)


class WorldsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def list(self):
        self.manager.require(self.owner, "worlds.read")
        from javbed.worlds import discover_worlds
        return [WorldInfo(row.name, row.edition, row.instance, str(row.path), row.version) for row in discover_worlds()]

    def backup(self, name, instance=""):
        self.manager.require(self.owner, "worlds.modify")
        from javbed.worlds import backup_world, discover_worlds
        world = next((row for row in discover_worlds() if row.name == name and row.instance == instance), None)
        if not world:
            raise ValueError("World not found")
        return self.manager._executor.submit(backup_world, world)

    def restore(self, name, archive, instance=""):
        self.manager.require(self.owner, "worlds.modify")
        from javbed.worlds import discover_worlds, restore_world
        world = next((row for row in discover_worlds() if row.name == name and row.instance == instance), None)
        if not world:
            raise ValueError("World not found")
        source = Path(archive).resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != ".zip":
            raise ValueError("Choose a ZIP world backup")
        return self.manager._executor.submit(restore_world, world, source)


class ModsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def _folder(self, instance):
        from javbed.instances import get_instance, valid_name
        if not isinstance(instance, str) or not valid_name(instance):
            raise ValueError("Invalid instance name")
        item = get_instance(instance)
        if not item:
            raise ValueError("Instance not found")
        path = Path(str(item["path"])).resolve() / "minecraft" / "mods"
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Mods directory cannot be a symlink")
        return path

    def list(self, instance):
        self.manager.require(self.owner, "mods.read")
        folder = self._folder(instance)
        if not folder.is_dir():
            return ()
        return tuple(ModInfo(instance, path.name.removesuffix(".disabled"), str(path), not path.name.endswith(".disabled")) for path in sorted(folder.iterdir()) if path.is_file() and path.name.lower().endswith((".jar", ".jar.disabled")))

    def install(self, instance, project, *, provider="modrinth"):
        self.manager.require(self.owner, "mods.modify")
        self._folder(instance)
        from javbed.instances import get_instance
        item = get_instance(instance)
        if not isinstance(project, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", project) or provider not in ("modrinth", "curseforge"):
            raise ValueError("Invalid mod project or provider")
        args = ("mods", "install", project, "--instance", instance, "--minecraft", str(item["version"]), "--loader", str(item.get("loader") or "vanilla"))
        if provider == "curseforge":
            args += ("--provider", "curseforge")
        return self.manager.backend_future("Java", *args)

    def remove(self, instance, filename):
        self.manager.require(self.owner, "mods.modify")
        folder = self._folder(instance)
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9._ -]+\.jar(?:\.disabled)?", filename) or filename in (".", ".."):
            raise ValueError("Invalid mod filename")
        target = folder / filename
        if target.is_symlink() or not target.is_file() or target.resolve().parent != folder.resolve():
            raise ValueError("Mod file not found or unsafe")
        def remove():
            target.unlink()
            from javbed import content_registry
            content_registry.remove(instance, "mod", filename.removesuffix(".disabled"))
            self.manager._dispatcher.post(lambda: self.manager.events.emit("mod.removed", instance=instance))
            return True
        return self.manager._executor.submit(remove)


class ProcessFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def launch(self, executable, *args):
        self.manager.require(self.owner, "process.launch")
        path = Path(executable).resolve(strict=True)
        if not path.is_file() or (os.name == "nt" and path.suffix.lower() != ".exe") or any(not isinstance(arg, str) or "\x00" in arg for arg in args):
            raise ValueError("Choose an executable and string arguments")
        return self.manager._executor.submit(lambda: subprocess.Popen([str(path), *args], cwd=str(path.parent), shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).pid)


class JavaFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def install_runtime(self, major):
        self.manager.require(self.owner, "java_tools")
        if type(major) is not int or major not in (8, 17, 21, 25):
            raise ValueError("Unsupported Java major version")
        return self.manager.backend_future("Java", "java", "install", str(major))

    def register_tool(self, *, id, title, callback):
        self.manager.require(self.owner, "java_tools")
        return self.manager.contributions.register(self.owner, "java_tool", id=id, title=title, callback=callback)


class TasksFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def run(self, callback, *args):
        self.manager.check_active(self.owner)
        if not callable(callback):
            raise ValueError("Task callback must be callable")
        return self.manager.submit_task(self.owner, callback, *args)


class ContributionsFacade:
    def __init__(self, manager, owner, kind, permission):
        self.manager, self.owner, self.kind, self.permission = manager, owner, kind, permission

    def register(self, *, id, title, callback):
        self.manager.require(self.owner, self.permission)
        if self.kind == "update_provider":
            self.manager.require(self.owner, "network")
        if self.kind == "metadata":
            self.manager.require(self.owner, "instances.read")
        return self.manager.contributions.register(self.owner, self.kind, id=id, title=title, callback=callback)


class ImportersFacade(ContributionsFacade):
    def __init__(self, manager, owner):
        super().__init__(manager, owner, "importer", "importers")

    def register(self, *, id, title, extension, callback):
        self.manager.require(self.owner, "importers")
        self.manager.require(self.owner, "files.read")
        if not isinstance(extension, str) or not re.fullmatch(r"\.[A-Za-z0-9]{1,19}", extension):
            raise ValueError("Invalid importer extension")
        registered = super().register(id=id, title=title, callback=callback)
        try:
            self.manager.files.register(self.owner, extension.lower(), lambda path: self.manager.contributions.invoke_id(id, path))
        except Exception:
            self.manager.contributions.unregister(self.owner, id)
            raise
        return registered


class NotificationsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def show(self, *, title, message):
        self.manager.require(self.owner, "notifications")
        self.manager.notify(self.owner, str(title), str(message))


class FilesFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def register_handler(self, *, extension, callback):
        self.manager.require(self.owner, "files.read")
        if not isinstance(extension, str) or not extension.startswith(".") or not extension[1:].isalnum() or len(extension) > 20:
            raise ValueError("Invalid file extension")
        self.manager.files.register(self.owner, extension.lower(), callback)

    def read_bytes(self, path):
        self.manager.require(self.owner, "files.read")
        source = Path(path).resolve(strict=True)
        if not source.is_file() or source.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("File is not regular or exceeds 64 MiB")
        return source.read_bytes()

    def write_bytes(self, path, data):
        self.manager.require(self.owner, "files.write")
        if not isinstance(data, bytes) or len(data) > 64 * 1024 * 1024:
            raise ValueError("Expected at most 64 MiB of bytes")
        raw_target = Path(path)
        if raw_target.is_symlink():
            raise ValueError("Unsafe file destination")
        target = raw_target.resolve()
        if not target.parent.is_dir():
            raise ValueError("Unsafe file destination")
        fd, name = tempfile.mkstemp(prefix=".javbed-plugin-", dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target


class DeepLinksFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def register(self, callback):
        self.manager.require(self.owner, "deep_links")
        self.manager.links.register(self.owner, self.owner, callback)


class DownloadsFacade:
    def __init__(self, manager, owner):
        self.manager, self.owner = manager, owner

    def download(self, *, url, destination, title):
        self.manager.require(self.owner, "network")
        target = Path(destination).resolve()
        data = (self.manager.data_root / self.owner).resolve()
        if not target.is_relative_to(data):
            self.manager.require(self.owner, "files.write")
        return self.manager.download(self.owner, url, target, title)


class PluginContext:
    api_version = JAVBED_PLUGIN_API

    def __init__(self, manager, owner, logger):
        if not ID.fullmatch(owner):
            raise ValueError("Invalid plugin ID")
        (manager.data_root / owner).mkdir(parents=True, exist_ok=True)
        self.logger = logger
        self.paths = PluginPaths(manager.data_root / owner)
        self.events = EventsFacade(manager, owner)
        self.commands = CommandsFacade(manager, owner)
        self.ui = UIFacade(manager, owner)
        self.instances = InstancesFacade(manager, owner)
        self.servers = ServersFacade(manager, owner)
        self.accounts = AccountsFacade(manager, owner)
        self.worlds = WorldsFacade(manager, owner)
        self.mods = ModsFacade(manager, owner)
        self.process = ProcessFacade(manager, owner)
        self.java = JavaFacade(manager, owner)
        self.tasks = TasksFacade(manager, owner)
        self.integrations = ContributionsFacade(manager, owner, "game", "integrations")
        self.server_providers = ContributionsFacade(manager, owner, "server_provider", "server_providers")
        self.diagnostics = ContributionsFacade(manager, owner, "diagnostic", "diagnostics")
        self.metadata = ContributionsFacade(manager, owner, "metadata", "metadata")
        self.update_providers = ContributionsFacade(manager, owner, "update_provider", "update_providers")
        self.importers = ImportersFacade(manager, owner)
        self.notifications = NotificationsFacade(manager, owner)
        self.files = FilesFacade(manager, owner)
        self.deep_links = DeepLinksFacade(manager, owner)
        self.downloads = DownloadsFacade(manager, owner)
        self.settings = PluginSettings(manager, owner)
