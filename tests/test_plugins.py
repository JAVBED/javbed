"""Plugin API contract, lifecycle, package safety and failure isolation."""

import json
import tempfile
import unittest
import zipfile
import stat
import threading
from pathlib import Path
from unittest.mock import patch

from javbed.plugins.context import PluginContext
from javbed.plugins.api import DiagnosticResult, GameInfo, ServerInfo, UpdateInfo
from javbed.plugins.manager import PluginManager
from javbed.plugins.manifest import PluginManifest, compare
from javbed.plugins.packages import inspect, install
from javbed.plugins.permissions import HIGH_RISK, PermissionSet


def manifest(identifier="com.example.hello", permissions=None, **extra):
    data = {
        "manifest_version": 1, "api_version": 1, "id": identifier,
        "name": "Hello", "version": "1.0.0", "description": "Example",
        "author": "Example", "entrypoint": "plugin.py",
        "javbed": {"minimum_version": "0.1.0", "maximum_version": None},
        "permissions": permissions if permissions is not None else ["commands", "settings.read", "settings.write"],
    }
    data.update(extra)
    return data


def make_plugin(root, identifier="com.example.hello", permissions=None, code=None, **extra):
    directory = root / "plugins" / identifier
    directory.mkdir(parents=True)
    (directory / "javbed-plugin.json").write_text(json.dumps(manifest(identifier, permissions, **extra)), encoding="utf-8")
    (directory / "plugin.py").write_text(code or "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context):\n        self.context = context\n        context.commands.register(id='example.hello', title='Hello', callback=lambda: None)\ndef create_plugin(): return Plugin()\n", encoding="utf-8")
    return directory


class PluginTests(unittest.TestCase):
    def test_failed_update_restores_previous_plugin(self):
        old_code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): context.commands.register(id='example.hello', title='Hello', callback=lambda: None)\ndef create_plugin(): return Plugin()\n"
        broken_code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): raise RuntimeError('broken update')\ndef create_plugin(): return Plugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["commands"], code=old_code)
            source = root / "incoming"
            source.mkdir()
            (source / "javbed-plugin.json").write_text(json.dumps(manifest(permissions=["commands"], version="1.1.0")), encoding="utf-8")
            (source / "plugin.py").write_text(broken_code, encoding="utf-8")
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            with self.assertRaises(RuntimeError):
                manager.update(source, approve=True)
            self.assertEqual(manager.records["com.example.hello"].manifest.version, "1.0.0")
            self.assertEqual(manager.records["com.example.hello"].status, "enabled")
            self.assertTrue(manager.commands.invoke("example.hello"))
            manager.shutdown()

    def test_attached_callbacks_run_off_caller_thread(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["commands", "ui", "deep_links"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            seen = []
            ready = threading.Event()
            main_thread = threading.get_ident()
            def callback():
                seen.append(threading.get_ident())
                ready.set()
            manager.commands.register("com.example.hello", id="example.test", title="Test", callback=callback)
            manager.attach()
            self.assertTrue(manager.commands.invoke("example.test"))
            self.assertTrue(ready.wait(2))
            self.assertNotEqual(seen[0], main_thread)
            manager.shutdown()

    def test_structured_provider_contracts_and_cleanup(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["integrations", "server_providers", "servers.read", "servers.modify", "servers.console", "update_providers", "network"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            calls = []
            context.integrations.register(id="example.games", title="Games", discover=lambda: [GameInfo("game1", "Game One")], launch=lambda game: calls.append(("launch", game)))
            self.assertEqual(context.integrations.list("example.games"), (GameInfo("game1", "Game One"),))
            context.integrations.launch("example.games", "game1").result(timeout=2)
            provider = "example.servers"
            context.server_providers.register(id=provider, title="Servers", create=lambda name, version: calls.append(("create", name)), list=lambda: [ServerInfo("test", provider, "1.21", False, None)], start=lambda name: calls.append(("start", name)), stop=lambda name: None, restart=lambda name: None, send_command=lambda name, command: calls.append(("command", command)), backup=lambda name: None)
            with patch("javbed.servers.server_snapshot", return_value=[]):
                self.assertEqual(context.servers.get("test", provider).provider, provider)
            context.servers.start("test", provider=provider).result(timeout=2)
            context.servers.send_command("test", "say hi", provider=provider).result(timeout=2)
            context.update_providers.register(id="example.updates", title="Updates", check=lambda: [UpdateInfo("u1", "Game One", "1.0", "1.1")], apply=lambda update: calls.append(("update", update)))
            self.assertEqual(context.update_providers.check("example.updates")[0].available_version, "1.1")
            context.update_providers.apply("example.updates", "u1").result(timeout=2)
            self.assertEqual(calls, [("launch", "game1"), ("start", "test"), ("command", "say hi"), ("update", "u1")])
            manager.disable("com.example.hello")
            self.assertEqual(manager.contributions.all("server_provider"), ())
            manager.shutdown()

    def test_file_handler_conflicts_require_explicit_choice(self):
        from javbed.plugins.registries import FileHandlerRegistry
        called = []
        registry = FileHandlerRegistry(lambda *_: None)
        registry.register("com.example.one", ".demo", lambda path: called.append("one"))
        registry.register("com.example.two", ".demo", lambda path: called.append("two"))
        self.assertEqual(registry.candidates(".demo"), ("com.example.one", "com.example.two"))
        with self.assertRaisesRegex(ValueError, "Choose"):
            registry.invoke(".demo", Path("test.demo"))
        self.assertTrue(registry.invoke(".demo", Path("test.demo"), owner="com.example.two"))
        self.assertEqual(called, ["two"])
        registry.remove_owner("com.example.two")
        self.assertTrue(registry.invoke(".demo", Path("test.demo")))
        self.assertEqual(called, ["two", "one"])

    def test_extended_contributions_permissions_and_reload_cleanup(self):
        code = "from javbed_plugin_api import JavbedPlugin, DiagnosticResult\nclass Plugin(JavbedPlugin):\n    def on_load(self, context):\n        context.integrations.register(id='example.game', title='Example game', callback=lambda: 'launched')\n        context.server_providers.register(id='example.server', title='Example server', callback=lambda name, version: name + version)\n        context.diagnostics.register(id='example.check', title='Example check', callback=lambda: DiagnosticResult('Ready', 'healthy', 'OK'))\n        context.java.register_tool(id='example.tool', title='Example tool', callback=lambda: 'done')\n        context.metadata.register(id='example.meta', title='Example metadata', callback=lambda instance: {'Name': instance.name})\n        context.update_providers.register(id='example.updates', title='Example updates', callback=lambda: 'current')\n        context.importers.register(id='example.import', title='Example import', extension='.example', callback=lambda path: path.name)\ndef create_plugin(): return Plugin()\n"
        permissions = ["integrations", "server_providers", "diagnostics", "java_tools", "metadata", "instances.read", "update_providers", "network", "importers", "files.read"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=permissions, code=code)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            self.assertEqual(len(manager.contributions.all("game")), 1)
            self.assertEqual(manager.contributions.invoke(manager.contributions.all("diagnostic")[0]), DiagnosticResult("Ready", "healthy", "OK"))
            self.assertEqual(manager.files.invoke(".example", root / "file.example"), True)
            manager.reload("com.example.hello")
            self.assertEqual(len(manager.contributions.all("game")), 1)
            manager.disable("com.example.hello")
            self.assertEqual(manager.contributions.all("game"), ())
            self.assertIsNone(manager.files.owners(".example"))
            manager.shutdown()

    def test_extended_permission_checks_and_collision(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["integrations"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            self.assertIn("integrations", context.permissions)
            with self.assertRaises(PermissionError):
                context.server_providers.register(id="example.provider", title="Provider", callback=lambda *_: None)
            with self.assertRaises(PermissionError):
                context.server_providers
            with self.assertRaises(PermissionError):
                context.process.launch(root / "missing")
            with self.assertRaises(PermissionError):
                context.events.subscribe("account.changed", lambda **data: None)
            context.integrations.register(id="example.game", title="Game", callback=lambda: None)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                context.integrations.register(id="example.game", title="Game", callback=lambda: None)
            manager.shutdown()

    def test_contribution_registry_can_be_read_during_worker_registration(self):
        from concurrent.futures import Future
        from javbed.plugins.registries import ContributionRegistry
        registry = ContributionRegistry(lambda *_: None)
        errors = []

        def register():
            try:
                for index in range(300):
                    registry.register("example", "game", id=f"example.game{index}", title="Game", callback=lambda: None)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=register)
        worker.start()
        while worker.is_alive():
            tuple(registry.all("game"))
        worker.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(registry.all("game")), 300)
        completed = Future()
        completed.set_result("launched")
        registry.register("example", "game", id="example.future", title="Future", callback=lambda: completed)
        self.assertEqual(registry.invoke_id("example.future"), "launched")

    def test_broken_provider_is_quarantined_without_affecting_other_plugins(self):
        broken = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): context.integrations.register(id='example.broken', title='Broken', callback=lambda: 1/0)\ndef create_plugin(): return Plugin()\n"
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, "com.example.broken", permissions=["integrations"], code=broken)
            make_plugin(root, "com.example.healthy", permissions=[], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.broken", approve=True)
            manager.enable("com.example.healthy", approve=True)
            self.assertIsNone(manager.contributions.invoke(manager.contributions.all("game")[0]))
            self.assertEqual(manager.records["com.example.broken"].status, "error")
            self.assertEqual(manager.records["com.example.healthy"].status, "enabled")
            self.assertEqual(manager.contributions.all("game"), ())
            manager.shutdown()

    def test_process_launch_uses_no_shell_and_returns_pid(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "tool.exe"
            executable.write_bytes(b"placeholder")
            make_plugin(root, permissions=["process.launch"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            with patch("javbed.plugins.context.subprocess.Popen") as popen:
                popen.return_value.pid = 123
                self.assertEqual(context.process.launch(executable, "--version").result(timeout=2), 123)
                self.assertEqual(popen.call_args.args[0], [str(executable.resolve()), "--version"])
                self.assertFalse(popen.call_args.kwargs["shell"])
            manager.shutdown()

    def test_mods_structured_read_and_safe_remove(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "instance" / "minecraft" / "mods"
            folder.mkdir(parents=True)
            (folder / "example.jar").write_bytes(b"jar")
            (folder / "disabled.jar.disabled").write_bytes(b"jar")
            make_plugin(root, permissions=["mods.read", "mods.modify"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            with patch("javbed.instances.get_instance", return_value={"path": str(root / "instance"), "version": "1.21.1", "loader": "fabric"}):
                mods = context.mods.list("survival")
                self.assertEqual([(item.name, item.enabled) for item in mods], [("disabled.jar", False), ("example.jar", True)])
                with self.assertRaises(ValueError):
                    context.mods.remove("survival", "../outside.jar")
                with patch("javbed.content_registry.remove"):
                    self.assertTrue(context.mods.remove("survival", "example.jar").result(timeout=2))
                self.assertFalse((folder / "example.jar").exists())
            manager.shutdown()

    def test_file_write_requires_permission_and_rejects_symlink(self):
        plain = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["files.read", "files.write"], code=plain)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            target = root / "result.txt"
            self.assertEqual(context.files.write_bytes(target, b"hello"), target.resolve())
            self.assertEqual(context.files.read_bytes(target), b"hello")
            if hasattr(Path, "symlink_to"):
                link = root / "link.txt"
                try:
                    link.symlink_to(target)
                except (OSError, NotImplementedError):
                    pass
                else:
                    with self.assertRaises(ValueError):
                        context.files.write_bytes(link, b"overwrite")
            manager.shutdown()

    def test_manifest_validation_and_api_independence(self):
        item = PluginManifest.from_data(manifest())
        self.assertEqual(item.api_version, 1)
        self.assertEqual(item.permissions.names, frozenset({"commands", "settings.read", "settings.write"}))
        for changes in (
            {"id": "../escape"}, {"entrypoint": "../plugin.py"}, {"api_version": 2},
            {"manifest_version": 2}, {"permissions": ["unknown"]}, {"version": "latest"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                PluginManifest.from_data(manifest(**changes))
        self.assertIn("network", HIGH_RISK)
        with self.assertRaises(PermissionError):
            PermissionSet.parse(["commands"]).require("network")

    def test_discovery_does_not_import_disabled_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed.txt"
            make_plugin(root, code=f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
            manager = PluginManager(root)
            manager.discover()
            manager.load_enabled()
            self.assertFalse(marker.exists())
            self.assertEqual(manager.records["com.example.hello"].status, "disabled")
            manager.shutdown()

    def test_enable_commands_events_reload_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context):\n        self.context=context\n        context.events.subscribe('javbed.started', lambda **data: context.settings.set('started', True))\n        context.commands.register(id='example.hello', title='Hello', callback=lambda: context.settings.set('command', True))\ndef create_plugin(): return Plugin()\n"
            make_plugin(root, code=code)
            manager = PluginManager(root)
            manager.discover()
            with self.assertRaises(PermissionError):
                manager.enable("com.example.hello")
            manager.enable("com.example.hello", approve=True)
            self.assertEqual(manager.records["com.example.hello"].status, "enabled")
            manager.events.emit("javbed.started")
            self.assertTrue(manager.commands.invoke("example.hello"))
            data = json.loads((root / "plugin-data" / "com.example.hello" / "settings.json").read_text())
            self.assertTrue(data["started"] and data["command"])
            manager.reload("com.example.hello")
            self.assertEqual(len(manager.commands.all()), 1)
            manager.disable("com.example.hello")
            self.assertEqual(manager.commands.all(), ())
            self.assertEqual(manager.events._subscriptions, {})
            manager.shutdown()

    def test_failure_quarantines_only_faulty_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): raise RuntimeError('broken load')\ndef create_plugin(): return Plugin()\n"
            make_plugin(root, "com.example.broken", code=broken)
            make_plugin(root, "com.example.healthy")
            manager = PluginManager(root)
            manager.discover()
            with self.assertRaises(RuntimeError):
                manager.enable("com.example.broken", approve=True)
            manager.enable("com.example.healthy", approve=True)
            self.assertEqual(manager.records["com.example.broken"].status, "error")
            self.assertEqual(manager.records["com.example.healthy"].status, "enabled")
            manager.shutdown()

    def test_event_and_command_failures_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context):\n        context.events.subscribe('test.event', lambda **data: 1/0)\n        context.commands.register(id='bad.command', title='Bad', callback=lambda: 1/0)\ndef create_plugin(): return Plugin()\n"
            make_plugin(root, "com.example.bad", code=bad)
            make_plugin(root, "com.example.good")
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.bad", approve=True)
            manager.enable("com.example.good", approve=True)
            manager.events.emit("test.event")
            self.assertEqual(manager.records["com.example.bad"].status, "error")
            self.assertEqual(manager.records["com.example.good"].status, "enabled")
            self.assertFalse(manager.commands.invoke("bad.command"))
            manager.shutdown()

    def test_dependencies_cycles_and_safe_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, "com.example.first", dependencies={"com.example.second": ">=1.0.0"})
            make_plugin(root, "com.example.second", dependencies={"com.example.first": ">=1.0.0"})
            manager = PluginManager(root)
            manager.discover()
            with self.assertRaisesRegex(ValueError, "requires enabled"):
                manager._dependency_order(["com.example.first"])
            manager.records["com.example.first"].enabled = True
            manager.records["com.example.second"].enabled = True
            with self.assertRaisesRegex(ValueError, "Circular"):
                manager._dependency_order(["com.example.first"])
            manager.shutdown()
            safe = PluginManager(root, safe_mode=True)
            safe.discover()
            with self.assertRaises(RuntimeError):
                safe.enable("com.example.first", approve=True)
            safe.shutdown()

    def test_settings_namespace_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, "com.example.one", permissions=["settings.read", "settings.write"], code="from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            make_plugin(root, "com.example.two", permissions=["settings.read", "settings.write"], code="from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.one", approve=True)
            manager.enable("com.example.two", approve=True)
            one = PluginContext(manager, "com.example.one", manager.records["com.example.one"].logger)
            two = PluginContext(manager, "com.example.two", manager.records["com.example.two"].logger)
            one.settings.set("value", 4)
            self.assertEqual(one.settings.get("value"), 4)
            self.assertIsNone(two.settings.get("value"))
            self.assertEqual(one.paths.data, root / "plugin-data" / "com.example.one")
            self.assertTrue(one.paths.data.is_dir())
            manager.shutdown()

    def test_zip_validation_and_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "example.javbedplugin"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("javbed-plugin.json", json.dumps(manifest()))
                archive.writestr("plugin.py", "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            self.assertEqual(inspect(package).id, "com.example.hello")
            installed = install(package, root / "plugins")
            self.assertEqual(installed.id, "com.example.hello")
            self.assertTrue((root / "plugins" / installed.id / "plugin.py").is_file())
            with self.assertRaises(FileExistsError):
                install(package, root / "plugins")
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as archive:
                archive.writestr("javbed-plugin.json", json.dumps(manifest()))
                archive.writestr("plugin.py", "pass")
                archive.writestr("../escape", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                install(bad, root / "plugins")
            self.assertFalse((root / "escape").exists())

    def test_update_comparison(self):
        self.assertGreater(compare("1.3.0", "1.2.9"), 0)
        self.assertEqual(compare("1.2", "1.2.0"), 0)
        self.assertLess(compare("1.2.0", "1.3.0"), 0)

    def test_duplicate_plugin_id_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root)
            duplicate = root / "plugins" / "another-directory"
            duplicate.mkdir()
            (duplicate / "javbed-plugin.json").write_text(json.dumps(manifest()), encoding="utf-8")
            (duplicate / "plugin.py").write_text("pass", encoding="utf-8")
            manager = PluginManager(root)
            manager.discover()
            self.assertEqual(manager.records["another-directory"].status, "invalid")
            self.assertIn("Duplicate plugin ID", manager.records["another-directory"].error)
            manager.shutdown()

    def test_zip_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "link.javbedplugin"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("javbed-plugin.json", json.dumps(manifest()))
                archive.writestr("plugin.py", "pass")
                link = zipfile.ZipInfo("assets/link")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(link, "../../escape")
            with self.assertRaisesRegex(ValueError, "link"):
                inspect(package)

    def test_account_facade_exposes_only_safe_metadata(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["accounts.read"], code="from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            with patch("javbed.accounts.accounts", return_value=("main", [{"alias": "main", "username": "Player", "uuid": "abc", "access_token": "secret"}])):
                self.assertEqual(context.accounts.list(), ({"alias": "main", "username": "Player", "uuid": "abc"},))
            manager.shutdown()

    def test_download_destination_requires_file_write_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["network"], code="from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            with self.assertRaises(PermissionError):
                context.downloads.download(url="https://example.invalid/file", destination=root / "outside.zip", title="Test")
            manager.shutdown()

    def test_persisted_enablement_and_new_permission_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = make_plugin(root)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            manager.shutdown()
            restarted = PluginManager(root)
            restarted.discover()
            restarted.load_enabled()
            self.assertEqual(restarted.records["com.example.hello"].status, "enabled")
            restarted.shutdown()
            data = json.loads((folder / "javbed-plugin.json").read_text())
            data["permissions"].append("network")
            (folder / "javbed-plugin.json").write_text(json.dumps(data), encoding="utf-8")
            changed = PluginManager(root)
            changed.discover()
            changed.load_enabled()
            self.assertEqual(changed.records["com.example.hello"].status, "approval required")
            self.assertEqual(changed.commands.all(), ())
            changed.shutdown()

    def test_bad_ui_factory_quarantines_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): context.ui.register_page(id='bad.page', title='Bad', widget_factory=lambda: 1/0)\ndef create_plugin(): return Plugin()\n"
            make_plugin(root, permissions=["ui"], code=code)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.hello", approve=True)
            extension = manager.ui.all("page")[0]
            self.assertIsNone(manager.ui.invoke(extension))
            self.assertEqual(manager.records["com.example.hello"].status, "error")
            self.assertEqual(manager.ui.all("page"), ())
            manager.shutdown()

    def test_instance_launch_uses_core_command_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_plugin(root, permissions=["instances.launch"], code="from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n")
            manager = PluginManager(root)
            manager.discover()
            calls = []
            manager.attach(run_command=lambda engine, args, finished: (calls.append((engine, args)), finished(True, "PID 123")))
            manager.enable("com.example.hello", approve=True)
            context = PluginContext(manager, "com.example.hello", manager.records["com.example.hello"].logger)
            self.assertIs(context.instances.launch("survival").result(timeout=1), True)
            self.assertEqual(calls, [("Java", ("instance", "launch", "survival"))])
            manager.shutdown()

    def test_incompatible_application_version_is_rejected_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            data = manifest()
            data["javbed"]["minimum_version"] = "2.0.0"
            (source / "javbed-plugin.json").write_text(json.dumps(data), encoding="utf-8")
            (source / "plugin.py").write_text("pass", encoding="utf-8")
            manager = PluginManager(root, app_version="1.0.0")
            with self.assertRaisesRegex(ValueError, "incompatible"):
                manager.install(source)
            self.assertFalse((root / "plugins" / "com.example.hello").exists())
            manager.shutdown()

    def test_factory_failure_during_load_cannot_reenable_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context): context.ui.register_page(id='bad.page', title='Bad', widget_factory=lambda: 1/0)\ndef create_plugin(): return Plugin()\n"
            make_plugin(root, permissions=["ui"], code=code)
            manager = PluginManager(root)
            manager.discover()
            manager.ui.changed = lambda: [manager.ui.invoke(item) for item in manager.ui.all("page")]
            with self.assertRaises(RuntimeError):
                manager.enable("com.example.hello", approve=True)
            record = manager.records["com.example.hello"]
            self.assertEqual(record.status, "error")
            self.assertIsNone(record.plugin)
            self.assertEqual(manager.ui.all("page"), ())
            manager.shutdown()

    def test_active_dependency_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = "from javbed_plugin_api import JavbedPlugin\ndef create_plugin(): return JavbedPlugin()\n"
            make_plugin(root, "com.example.base", permissions=[], code=code)
            make_plugin(root, "com.example.child", permissions=[], code=code, dependencies={"com.example.base": ">=1.0.0"})
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.base", approve=True)
            manager.enable("com.example.child", approve=True)
            with self.assertRaisesRegex(ValueError, "dependent"):
                manager.disable("com.example.base")
            with self.assertRaisesRegex(ValueError, "dependent"):
                manager.uninstall("com.example.base")
            manager.disable("com.example.child")
            manager.disable("com.example.base")
            manager.shutdown()

    def test_registration_conflicts_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = "from javbed_plugin_api import JavbedPlugin\nclass Plugin(JavbedPlugin):\n    def on_load(self, context):\n        context.commands.register(id='same.command', title='Same', callback=lambda: None)\n        context.ui.register_page(id='same.page', title='Same', widget_factory=lambda: None)\n        context.files.register_handler(extension='.foo', callback=lambda path: None)\ndef create_plugin(): return Plugin()\n"
            permissions = ["commands", "ui", "files.read"]
            make_plugin(root, "com.example.first", permissions=permissions, code=code)
            make_plugin(root, "com.example.second", permissions=permissions, code=code)
            manager = PluginManager(root)
            manager.discover()
            manager.enable("com.example.first", approve=True)
            with self.assertRaises(ValueError):
                manager.enable("com.example.second", approve=True)
            self.assertEqual(manager.records["com.example.second"].status, "error")
            self.assertEqual(len(manager.commands.all()), 1)
            self.assertEqual(len(manager.ui.all("page")), 1)
            manager.disable("com.example.first")
            self.assertEqual(manager.commands.all(), ())
            self.assertEqual(manager.ui.all("page"), ())
            self.assertIsNone(manager.files.owners(".foo"))
            manager.shutdown()

    def test_sample_plugin_registers_and_cleans_up_ui(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QWidget
        application = QApplication.instance() or QApplication([])
        source = Path(__file__).resolve().parents[1] / "examples" / "plugins" / "hello-javbed"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = PluginManager(root)
            manager.install(source)
            manager.enable("com.example.hello-javbed", approve=True)
            pages = manager.ui.all("page")
            self.assertEqual(len(pages), 1)
            widget = manager.ui.invoke(pages[0])
            self.assertIsInstance(widget, QWidget)
            self.assertTrue(manager.commands.invoke("example.hello"))
            self.assertEqual(len(manager.commands.all()), 1)
            manager.disable("com.example.hello-javbed")
            self.assertEqual(manager.ui.all("page"), ())
            self.assertEqual(manager.commands.all(), ())
            widget.deleteLater()
            application.processEvents()
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
