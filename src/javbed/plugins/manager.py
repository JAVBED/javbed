"""Discovery, lifecycle, capability enforcement and crash isolation."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import urllib.request
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal

from javbed import __version__
from javbed.engines import ENGINES
from javbed.settings import ROOT

from .api import JavbedPlugin
from .context import PluginContext
from .manifest import PluginManifest, compare, satisfies
from .registries import CommandRegistry, EventBus, RouteRegistry, UIRegistry


class _Dispatcher(QObject):
    requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.requested.connect(lambda fn: fn())

    def post(self, fn):
        if QCoreApplication.instance():
            self.requested.emit(fn)
        else:
            fn()


@dataclass
class PluginRecord:
    path: Path
    manifest: PluginManifest | None = None
    enabled: bool = False
    status: str = "disabled"
    error: str = ""
    startup_seconds: float = 0.0
    plugin: JavbedPlugin | None = None
    logger: logging.Logger | None = None
    module_prefix: str = ""
    approved_permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def id(self):
        return self.manifest.id if self.manifest else self.path.name


@dataclass
class DownloadTask:
    future: object
    cancel_event: threading.Event

    def cancel(self):
        self.cancel_event.set()


class PluginManager:
    def __init__(self, root: Path | None = None, *, safe_mode=False, app_version=__version__):
        self.root = Path(root) if root is not None else ROOT
        self.plugin_root = self.root / "plugins"
        self.data_root = self.root / "plugin-data"
        self.log_root = self.root / "logs" / "plugins"
        self.state_file = self.root / "plugins.json"
        self.safe_mode = safe_mode
        self.app_version = app_version
        self.records: dict[str, PluginRecord] = {}
        self.errors: list[str] = []
        self.events = EventBus(self._fail)
        self.commands = CommandRegistry(self._fail)
        self.ui = UIRegistry(self._fail)
        self.files = RouteRegistry(self._fail)
        self.links = RouteRegistry(self._fail)
        self._state = self._read_state()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="javbed-plugin")
        self._dispatcher = _Dispatcher()
        self._notify = lambda owner, title, message: None
        self._activity = None
        self._run_command = None
        self._downloads: list[DownloadTask] = []
        self._closed = False

    def _read_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".plugins-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(self._state, output, indent=2)
            os.replace(temporary, self.state_file)
        finally:
            temporary.unlink(missing_ok=True)

    def discover(self):
        if self.plugin_root.is_symlink():
            raise ValueError("Plugin directory cannot be a symlink")
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        self.records.clear()
        for directory in sorted(self.plugin_root.iterdir()):
            if not directory.is_dir() or directory.is_symlink() or directory.name.startswith("."):
                continue
            try:
                manifest = PluginManifest.read(directory)
                if manifest.id in self.records or directory.name != manifest.id:
                    raise ValueError("Duplicate plugin ID or directory name differs from ID")
                state = self._state.get(manifest.id, {})
                approved = frozenset(state.get("approved_permissions", [])) if isinstance(state, dict) else frozenset()
                enabled = bool(state.get("enabled")) if isinstance(state, dict) else False
                record = PluginRecord(directory, manifest, enabled, approved_permissions=approved)
                if enabled and approved != manifest.permissions.names:
                    record.status = "approval required"
                    record.error = "Requested permissions changed. Review and approve them again."
                self.records[manifest.id] = record
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                key = directory.name
                if key in self.records:
                    key += " (duplicate)"
                self.records[key] = PluginRecord(directory, status="invalid", error=str(exc))
        return self.records

    def _dependency_order(self, ids):
        visiting, visited, order = set(), set(), []

        def visit(identifier):
            if identifier in visited:
                return
            if identifier in visiting:
                raise ValueError("Circular plugin dependency: " + identifier)
            record = self.records.get(identifier)
            if not record or not record.manifest:
                raise ValueError("Missing plugin dependency: " + identifier)
            visiting.add(identifier)
            for dependency, requirement in record.manifest.dependencies.items():
                candidate = self.records.get(dependency)
                if not candidate or not candidate.manifest or not candidate.enabled:
                    raise ValueError(f"{identifier} requires enabled plugin {dependency}")
                if not satisfies(candidate.manifest.version, requirement):
                    raise ValueError(f"{identifier} requires {dependency} {requirement}")
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)
            order.append(identifier)

        for identifier in ids:
            visit(identifier)
        return order

    def load_enabled(self):
        if self.safe_mode:
            return
        ids = [record.id for record in self.records.values() if record.enabled and record.manifest and record.approved_permissions == record.manifest.permissions.names]
        for identifier in ids:
            try:
                self._dependency_order([identifier])
            except ValueError as exc:
                record = self.records[identifier]
                record.status, record.error = "blocked", str(exc)
        for identifier in ids:
            record = self.records[identifier]
            if record.status == "blocked":
                continue
            try:
                for dependency in self._dependency_order([identifier]):
                    if self.records[dependency].status in ("error", "blocked", "invalid"):
                        raise ValueError("Plugin dependency failed: " + dependency)
                    if self.records[dependency].status != "enabled":
                        self._load(self.records[dependency])
            except Exception as exc:
                if record.status != "error":
                    record.status, record.error = "blocked", str(exc)

    def _logger(self, record):
        self.log_root.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("javbed.plugin." + record.id)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        handler = logging.FileHandler(self.log_root / (record.id + ".log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [plugin:" + record.id + "] %(levelname)s %(message)s"))
        logger.addHandler(handler)
        record.logger = logger
        return logger

    def _load(self, record):
        if self.safe_mode or not record.manifest or record.approved_permissions != record.manifest.permissions.names:
            raise ValueError("Plugin is not approved for this session")
        if compare(self.app_version, record.manifest.minimum_version) < 0 or (record.manifest.maximum_version and compare(self.app_version, record.manifest.maximum_version) > 0):
            raise ValueError("Incompatible JAVBED application version")
        start = time.monotonic()
        logger = self._logger(record)
        record.status = "loading"
        try:
            prefix = "javbed_ext_" + hashlib.sha256(record.id.encode()).hexdigest()[:16] + "_" + uuid.uuid4().hex[:8]
            package = types.ModuleType(prefix)
            package.__path__ = [str(record.path)]
            sys.modules[prefix] = package
            record.module_prefix = prefix
            importlib.invalidate_caches()
            spec = importlib.util.spec_from_file_location(prefix + ".plugin", record.path / record.manifest.entrypoint)
            if not spec or not spec.loader:
                raise ImportError("Cannot load plugin entrypoint")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            factory = getattr(module, "create_plugin", None)
            if not callable(factory):
                raise TypeError("Plugin entrypoint must define create_plugin()")
            plugin = factory()
            if not isinstance(plugin, JavbedPlugin):
                raise TypeError("create_plugin() must return JavbedPlugin")
            record.plugin = plugin
            context = PluginContext(self, record.id, logger)
            plugin.on_load(context)
            if record.status != "loading":
                raise RuntimeError(record.error or "Plugin was quarantined during load")
            plugin.on_enable()
            if record.status != "loading":
                raise RuntimeError(record.error or "Plugin was quarantined during enable")
            record.status, record.error = "enabled", ""
            logger.info("Loaded")
        except Exception as exc:
            if record.status != "error":
                self._fail(record.id, "load", exc)
            raise
        finally:
            record.startup_seconds = time.monotonic() - start
            if record.startup_seconds > 1:
                logger.warning("Slow startup: %.2f seconds", record.startup_seconds)

    def check_active(self, owner):
        record = self.records.get(owner)
        if not record or record.status not in ("loading", "enabled"):
            raise RuntimeError("Plugin is not active")

    def require(self, owner, permission):
        self.check_active(owner)
        self.records[owner].manifest.permissions.require(permission)

    def enable(self, identifier, *, approve=False):
        if self.safe_mode:
            raise RuntimeError("Plugins cannot be enabled during Safe Mode")
        record = self.records[identifier]
        if record.plugin and record.status == "enabled":
            return
        if not record.manifest:
            raise ValueError(record.error)
        if approve:
            record.approved_permissions = record.manifest.permissions.names
        if record.approved_permissions != record.manifest.permissions.names:
            raise PermissionError("Review and approve requested permissions before enabling")
        record.enabled = True
        self._state[identifier] = {"enabled": True, "approved_permissions": sorted(record.approved_permissions)}
        self._save_state()
        try:
            for dependency in self._dependency_order([identifier]):
                if self.records[dependency].status != "enabled":
                    self._load(self.records[dependency])
        except Exception as exc:
            if record.status != "error":
                record.status, record.error = "blocked", str(exc)
            raise

    def _cleanup(self, record):
        owner = record.id
        for registry in (self.events, self.commands, self.ui, self.files, self.links):
            registry.remove_owner(owner)
        if record.module_prefix:
            for name in list(sys.modules):
                if name == record.module_prefix or name.startswith(record.module_prefix + "."):
                    sys.modules.pop(name, None)
            record.module_prefix = ""
        record.plugin = None
        if record.logger:
            for handler in record.logger.handlers[:]:
                record.logger.removeHandler(handler)
                handler.close()
            record.logger = None

    def disable(self, identifier, *, persist=True):
        if persist:
            dependents = [item.id for item in self.records.values() if item.plugin and item.manifest and identifier in item.manifest.dependencies and item.id != identifier]
            if dependents:
                raise ValueError("Disable dependent plugins first: " + ", ".join(dependents))
        record = self.records[identifier]
        plugin = record.plugin
        if plugin:
            for method in (plugin.on_disable, plugin.on_unload):
                try:
                    method()
                except Exception:
                    if record.logger:
                        record.logger.error("Lifecycle callback failed:\n%s", traceback.format_exc())
        self._cleanup(record)
        record.status = "disabled"
        if persist:
            record.enabled = False
            self._state[identifier] = {"enabled": False, "approved_permissions": sorted(record.approved_permissions)}
            self._save_state()

    def reload(self, identifier):
        record = self.records[identifier]
        self.disable(identifier, persist=False)
        if record.enabled:
            self._load(record)

    def install(self, source, *, replace=False):
        from .packages import install, inspect
        incoming = inspect(Path(source))
        if compare(self.app_version, incoming.minimum_version) < 0 or (incoming.maximum_version and compare(self.app_version, incoming.maximum_version) > 0):
            raise ValueError("Plugin is incompatible with this JAVBED version")
        identifier = incoming.id
        if replace:
            dependents = [item.id for item in self.records.values() if item.plugin and item.manifest and identifier in item.manifest.dependencies and item.id != identifier]
            if dependents:
                raise ValueError("Disable dependent plugins before updating: " + ", ".join(dependents))
        was_active = bool(replace and identifier in self.records and self.records[identifier].plugin)
        if was_active:
            self.disable(identifier, persist=False)
        try:
            manifest = install(Path(source), self.plugin_root, replace=replace)
        except Exception:
            if was_active:
                self._load(self.records[identifier])
            raise
        state = self._state.get(manifest.id, {})
        approved = frozenset(state.get("approved_permissions", [])) if isinstance(state, dict) else frozenset()
        self.records[manifest.id] = PluginRecord(self.plugin_root / manifest.id, manifest, False, approved_permissions=approved)
        return self.records[manifest.id]

    def uninstall(self, identifier):
        from .packages import uninstall
        dependents = [item.id for item in self.records.values() if item.plugin and item.manifest and identifier in item.manifest.dependencies and item.id != identifier]
        if dependents:
            raise ValueError("Disable dependent plugins first: " + ", ".join(dependents))
        if identifier in self.records and self.records[identifier].plugin:
            self.disable(identifier)
        uninstall(self.plugin_root, identifier)
        self.records.pop(identifier, None)
        self._state.pop(identifier, None)
        self._save_state()

    def _fail(self, owner, operation, exc):
        record = self.records.get(owner)
        message = f"{operation}: {exc}"
        if record:
            if record.logger:
                record.logger.error("%s\n%s", message, traceback.format_exc())
            record.status, record.error = "error", message
            self._cleanup(record)
        self.errors.append(f"{owner}: {message}")
        self.notify(owner, "Plugin error", f"{owner}: {message}")

    def shutdown(self):
        if self._closed:
            return
        self.events.emit("javbed.closing")
        self._closed = True
        for task in list(self._downloads):
            task.cancel()
        for identifier in reversed(list(self.records)):
            if self.records[identifier].plugin:
                self.disable(identifier, persist=False)
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._run_command = None

    def attach(self, *, notify=None, activity=None, run_command=None):
        if notify:
            self._notify = notify
        self._activity = activity
        self._run_command = run_command

    def notify(self, owner, title, message):
        self._dispatcher.post(lambda: self._notify(owner, title, message))

    def backend_future(self, engine, *args):
        if self._closed:
            raise RuntimeError("Plugin manager has shut down")
        if self._run_command:
            future = Future()
            def finished(ok, output):
                if future.done():
                    return
                if ok:
                    future.set_result(True)
                else:
                    future.set_exception(RuntimeError(str(output)[-500:] or "Backend command failed"))
            try:
                self._dispatcher.post(lambda: self._run_command(engine, args, finished))
            except Exception as exc:
                future.set_exception(exc)
            return future
        command, error = ENGINES[engine].command(*args)
        if error:
            raise RuntimeError(error)
        def run():
            result = subprocess.run(command, capture_output=True, text=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip()[-500:] or "Backend command failed")
            return True
        return self._executor.submit(run)

    def download(self, owner, url, target, title):
        if self._closed:
            raise RuntimeError("Plugin manager has shut down")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("Downloads require an HTTPS URL")
        cancelled = threading.Event()
        self._dispatcher.post(lambda: self.events.emit("download.started", title=title, destination=str(target)))
        activity_id = {"value": None}
        if self._activity:
            self._dispatcher.post(lambda: activity_id.update(value=self._activity.begin(title, owner, "Downloading", cancelled.set)))

        def run():
            partial = target.with_name(target.name + ".part")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                request = urllib.request.Request(url, headers={"User-Agent": "JAVBED Plugin API/1"})
                with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as output:
                    total = int(response.headers.get("Content-Length") or 0)
                    received = 0
                    while chunk := response.read(256 * 1024):
                        if cancelled.is_set():
                            raise RuntimeError("Download cancelled")
                        output.write(chunk)
                        received += len(chunk)
                        if self._activity:
                            self._dispatcher.post(lambda n=received, t=total: self._activity.progress(activity_id["value"], n, t) if activity_id["value"] else None)
                        self._dispatcher.post(lambda n=received, t=total: self.events.emit("download.progress", title=title, received=n, total=t))
                os.replace(partial, target)
                self._dispatcher.post(lambda: self.events.emit("download.completed", title=title, destination=str(target), message="Completed"))
                if self._activity:
                    self._dispatcher.post(lambda: self._activity.finish(activity_id["value"], True, "Completed") if activity_id["value"] else None)
                return target
            except Exception as exc:
                partial.unlink(missing_ok=True)
                self._dispatcher.post(lambda e=str(exc): self.events.emit("download.failed", title=title, destination=str(target), message=e))
                if self._activity:
                    self._dispatcher.post(lambda e=str(exc): self._activity.finish(activity_id["value"], False, e) if activity_id["value"] else None)
                raise

        task = DownloadTask(self._executor.submit(run), cancelled)
        self._downloads.append(task)
        task.future.add_done_callback(lambda _: self._downloads.remove(task) if task in self._downloads else None)
        return task
