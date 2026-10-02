"""Permission checked, stable facades exposed to third-party code."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .api import JAVBED_PLUGIN_API, InstanceInfo, ServerInfo, WorldInfo
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
        return Path(item.path)

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
        self.notifications = NotificationsFacade(manager, owner)
        self.files = FilesFacade(manager, owner)
        self.deep_links = DeepLinksFacade(manager, owner)
        self.downloads = DownloadsFacade(manager, owner)
        self.settings = PluginSettings(manager, owner)
