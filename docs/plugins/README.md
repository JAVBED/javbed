# JAVBED Plugin API 1

Plugins extend JAVBED without editing the launcher. API version `1` is independent of the JAVBED application version. Plugin code runs in the same Python process as JAVBED. **Plugins are third-party code and may execute code on your computer. Only install plugins you trust.** Manifest permissions control the supported JAVBED API; they are not an operating-system sandbox.

## Install and run

Open **Settings → Plugins**. Choose a plugin directory, `.zip`, or `.javbedplugin` package. JAVBED shows its metadata and requested permissions before installing and enabling it. A plugin placed manually in the plugin directory starts disabled until its permissions are approved. Disabled plugins are not imported. Plugin errors are shown in the manager and written to `logs/plugins/<id>.log`.

The plugin directory is `settings.ROOT / "plugins"`: `%LOCALAPPDATA%/JAVBED/plugins` on Windows, `~/.local/share/JAVBED/plugins` on Linux, and JAVBED's existing application-data directory on macOS. Portable mode uses `JAVBED-data/plugins` beside the launcher. Each installed plugin lives in `plugins/<plugin-id>/`. Data and settings live in `plugin-data/<plugin-id>/`, separate from the plugin's executable files.

Run `JAVBED.exe --safe-mode` or `python javbed_main.py --safe-mode` to start core without third-party plugins. Holding Shift during startup also requests Safe Mode. Safe Mode does not change persisted enablement. If startup stops while loading plugins, JAVBED offers to start without them on a later attempt.

## Layout and manifest

```text
com.example.hello/
  javbed-plugin.json
  plugin.py
  assets/
```

```json
{
  "manifest_version": 1,
  "api_version": 1,
  "id": "com.example.hello",
  "name": "Hello",
  "version": "1.0.0",
  "description": "An example plugin.",
  "author": "Example",
  "homepage": "https://example.com",
  "entrypoint": "plugin.py",
  "javbed": {"minimum_version": "0.1.0", "maximum_version": null},
  "permissions": ["commands", "ui", "instances.read", "settings.read", "settings.write"]
}
```

All shown fields except `homepage` are required. IDs are lowercase, dotted or hyphenated, and must contain at least one separator; a reverse-domain ID is recommended. The entrypoint must be a `.py` file directly in the plugin root. Manifest discovery never imports Python code. An unsupported API or application version prevents loading. Optional `dependencies` maps plugin IDs to version constraints such as `">=1.2.0"`; required plugins must already be installed and enabled. Circular dependencies are rejected. Optional `update` is `{"type":"github","repo":"owner/repository"}`. Updates are checked and installed only after user action and permission review.

`.javbedplugin` is a ZIP archive with `javbed-plugin.json` at its root. Path traversal, symlinks, duplicate paths, oversized entries, and excessive expansion are rejected. The plugin root directory is named after the manifest ID when installed.

## Lifecycle

```python
from javbed_plugin_api import JavbedPlugin

class HelloPlugin(JavbedPlugin):
    def on_load(self, context):
        self.context = context
        context.logger.info("Hello!")

    def on_enable(self):
        pass

    def on_disable(self):
        pass

    def on_unload(self):
        pass

def create_plugin():
    return HelloPlugin()
```

The module is imported only when an approved plugin is enabled. `create_plugin()` must return a `JavbedPlugin`. Relative imports from files in the plugin directory are supported. On disable or reload, JAVBED removes all event, command, UI, contribution, file, and URI registrations. A callback exception is logged and quarantines that plugin for the current session; other plugins and core remain active. Plugin startup duration is recorded, and loads over one second are logged. Initial plugin loading runs in a background worker after the window is created. UI factories run on the Qt main thread; they must return promptly. Python cannot safely terminate arbitrary code running in the launcher process, so a malicious or permanently blocking plugin still requires Safe Mode and manual removal.

## Capabilities and permissions

Permissions are declared in the manifest and reviewed on enable. New permissions require a fresh approval. The initial permission names are:

| Area | Permissions |
| --- | --- |
| UI and commands | `ui`, `commands` |
| Instances | `instances.read`, `instances.modify`, `instances.launch` |
| Mods and worlds | `mods.read`, `mods.modify`, `worlds.read`, `worlds.modify` |
| Servers | `servers.read`, `servers.modify`, `servers.console` |
| Accounts | `accounts.read` |
| Files and network | `files.read`, `files.write`, `network` |
| Settings and notices | `settings.read`, `settings.write`, `notifications` |
| Routes and processes | `deep_links`, `process.launch` |
| Extension providers | `integrations`, `server_providers`, `importers`, `diagnostics`, `java_tools`, `metadata`, `update_providers` |

`files.write`, `network`, `servers.console`, `process.launch`, and `accounts.read` are marked high risk in the review dialog. Plugin code itself is unsandboxed Python. `accounts.read` returns only alias, username, and UUID from JAVBED's safe account reader; tokens and passwords are never passed through `PluginContext`.

`context.api_version` is `1`, and `context.permissions` is a read-only set of granted permission names. A capability facade is accessible only when at least one of its matching permissions was granted; individual methods enforce the exact permission they need. `context.logger` prefixes entries with the plugin ID. `context.paths.data` is the plugin's private data directory. `context.settings.get(key, default)` requires `settings.read`; `context.settings.set(key, JSON_value)` requires `settings.write` and saves to that plugin's own `settings.json`. `context.notifications.show(title=..., message=...)` requires `notifications` and respects the launcher's Notifications setting.

`context.instances.list()` and `get(name)` return immutable `InstanceInfo` objects with name, version, loader, era, and path. They require `instances.read`. `launch`, `create`, `clone`, and `delete` require their corresponding launch or modify permission and return `Future[bool]` for backend success. Plugins do not need to parse JAVLI output. `open_folder(name)` opens the validated folder and returns its path. `context.servers.list(provider=None)` and `get(name, provider=None)` return immutable `ServerInfo` objects from SERVLI and enabled plugin providers. Pass a provider ID to select a plugin provider when names overlap. `start`, `stop`, `restart`, `backup`, and `send_command` accept `provider=...` and return futures. `servers.modify` or `servers.console` is required as appropriate. `context.worlds.list()` returns `WorldInfo`; `backup(name, instance="")` and `restore(name, archive, instance="")` return futures. Synchronous list/get calls should be made from a background task when the underlying scan may be slow.

`context.mods.list(instance)` returns immutable `ModInfo` entries with instance, filename, path and enabled state. `install(instance, project, provider="modrinth")` delegates to JAVLI and returns a future. `remove(instance, filename)` removes one validated mod file and returns a future. These require `mods.read` and `mods.modify` respectively. `context.java.install_runtime(major)` delegates to JAVLI for Java 8, 17, 21, or 25. `context.process.launch(executable, *args)` requires the high risk `process.launch` permission, uses no shell, and returns a `Future[int]` with the process ID. On Windows it accepts `.exe` files only. `context.files.read_bytes(path)` and `write_bytes(path, data)` are capped at 64 MiB and require `files.read` and `files.write`. Plugins should keep ordinary data under `context.paths.data`.

`context.tasks.run(callback, *args)` schedules blocking work on JAVBED's plugin worker pool and returns a future. Pending tasks are cancelled when the plugin disables; a running Python task cannot be forcibly stopped. In the running launcher, event, command, deep-link, instance/server/world action, and provider callbacks run in a plugin worker. Page and settings widget factories run on the Qt main thread; they must be fast and must not perform network requests. `javbed.closing` callbacks run synchronously before workers stop. Do not create or modify Qt widgets from a worker thread; use Qt signals to cross to the UI thread.

`context.downloads.download(url=..., destination=..., title=...)` requires `network`. A destination outside `context.paths.data` also requires `files.write`. HTTPS downloads appear in Downloads & Activity and return a `DownloadTask` with `.future` and `.cancel()`. Partial files are removed on failure or cancellation.

## Events and commands

```python
token = context.events.subscribe("game.started", lambda **data: context.logger.info("Started %s", data["game"]))
context.events.unsubscribe(token)

context.commands.register(
    id="example.hello", title="Say Hello", description="A greeting",
    keywords=("hello", "example"), callback=lambda: print("Hello")
)
```

Commands appear in Ctrl+K and are removed on disable. IDs must be unique. Event callback exceptions are isolated. Subscribing to `account.*`, `game.*` / `instance.*`, `mod.*`, `world.*`, or `server.*` requires the matching `accounts.read`, `instances.read`, `mods.read`, `worlds.read`, or `servers.read` permission. `download.*` requires `network` and `files.read` because event payloads contain destination paths. API 1 emits `javbed.started`, `javbed.closing`, `account.changed`, `game.launching`, `game.started`, `game.exited`, `game.crashed`, `instance.created`, `instance.updated`, `instance.deleted`, `instance.launching`, `instance.started`, `instance.exited`, `mod.installed`, `mod.removed`, `mod.updated`, `world.backed_up`, `world.restored`, `server.created`, `server.started`, `server.stopped`, `server.crashed`, `server.backup_completed`, `download.started`, `download.progress`, `download.completed`, and `download.failed` when the corresponding core workflow reports them. Event payloads are keyword arguments and contain no authentication secrets. Some events rely on a backend reporting a launch PID or a core operation completing successfully.

| Event family | Payload keys |
| --- | --- |
| `javbed.*` | none |
| `account.changed` | `alias` |
| `game.launching` | `game`, `instance` |
| `game.started` | `game`, `instance`, `pid` |
| `game.exited`, `game.crashed` | `game`, `instance`, `exit_code` |
| `instance.created`, `instance.updated`, `instance.deleted`, `instance.launching` | `name` |
| `instance.started` | `name`, `pid` |
| `instance.exited` | `name`, `exit_code` |
| `mod.installed`, `mod.removed`, `mod.updated` | `instance` |
| `world.backed_up`, `world.restored` | `result` (path string) |
| `server.*` | `name` |
| `download.started` | `title`, `destination` |
| `download.progress` | `title`, `received`, `total` |
| `download.completed`, `download.failed` | `title`, `destination`, `message` |

## UI and handlers

`ui` allows `context.ui.register_page(id=..., title=..., widget_factory=...)` and `register_settings_page(...)`. Factories must return a PySide6 `QWidget`. JAVBED applies its application stylesheet to child widgets automatically. Reusable `PluginCard`, `SectionTitle`, `JavbedButton`, `StatusBadge`, and `ProgressCard` are available from `javbed.plugins.ui`. Page IDs must be unique. A bad factory is quarantined and cannot prevent core navigation.

`register_instance_action`, `register_server_action`, and `register_world_action` add actions to their respective views. They receive immutable `InstanceInfo`, `ServerInfo`, or `WorldInfo` objects. These require `ui` plus the corresponding `.read` permission. Instance actions appear in the instance context menu.

`register_context_action(target="instance" | "server" | "world", id=..., title=..., callback=...)` is an equivalent way to register a typed action. Registration IDs are unique within the UI registry.

`context.files.register_handler(extension=".example", callback=...)` requires `files.read`. The callback receives a `Path` from a dropped local file. If multiple plugins or JAVBED itself handle an extension, JAVBED asks the user which handler to use. A plugin cannot register the same extension twice.

`context.deep_links.register(callback)` requires `deep_links`. Links have the form `javbed://plugin/<plugin-id>/<route>` and the callback receives the decoded route string. Core routes cannot be overridden; unsafe or oversized links are rejected.

## Integration and provider extensions

The **Extensions** sidebar page shows enabled plugin games, server providers, importers, Java tools, and update providers. The host runs their callbacks in a worker. The simple callback registrations remain available:

```python
from javbed_plugin_api import DiagnosticResult

context.integrations.register(id="example.game", title="Example game", callback=launch_game)
context.server_providers.register(id="example.server", title="Example server", callback=create_server)
context.java.register_tool(id="example.java", title="Inspect Java", callback=inspect_java)
context.diagnostics.register(id="example.health", title="Example", callback=lambda: DiagnosticResult("Health", "healthy", "Ready"))
context.metadata.register(id="example.metadata", title="Example metadata", callback=describe_instance)
context.update_providers.register(id="example.updates", title="Example updates", callback=check_updates)
context.importers.register(id="example.import", title="Example import", extension=".example", callback=import_file)
```

The `launch_game()` and Java tool callbacks take no arguments. `create_server(name: str, minecraft_version: str)` receives validated text. Diagnostic callbacks return `DiagnosticResult(name, state, detail)`, where state is `healthy`, `warning`, or `failed`; results appear in **Doctor**. Metadata callbacks receive `InstanceInfo` and return `dict[str, str]`; users find them in the instance menu. Simple update provider callbacks return a short status string on user action. Importer callbacks receive a local `Path` from drag and drop or the Extensions file picker. All registrations are removed when the owner disables or reloads.

For a browsable game integration, use the structured form. `GameInfo` is imported from `javbed_plugin_api`; `discover()` returns a list or tuple of these immutable entries and `launch(game_id)` receives the selected ID:

```python
from javbed_plugin_api import GameInfo

context.integrations.register(
    id="example.games", title="Example games",
    discover=lambda: [GameInfo("game-one", "Game One", "1.0")],
    launch=lambda game_id: launch_game(game_id),
)
```

`context.integrations.list("example.games")` returns the typed entries, and `context.integrations.launch("example.games", "game-one")` returns a future. Discover and launch callbacks run on a worker when invoked through the Extensions page.

A structured server provider registers seven operations: `create(name, version)`, `list()`, `start(name)`, `stop(name)`, `restart(name)`, `send_command(name, command)`, and `backup(name)`. `list()` returns `ServerInfo` entries whose `provider` equals the registered provider ID. JAVBED offers these actions in Extensions and exposes them through `context.servers` with an explicit provider ID. Providers must validate names and commands against their own service. Registration requires `server_providers`, `servers.read`, `servers.modify`, and `servers.console`, so users see the high-risk console permission during approval. Callers need the matching `servers.*` permission to use the wrapper.

For structured updates, `context.update_providers.register(id=..., title=..., check=..., apply=...)` takes a `check()` callback returning `UpdateInfo(id, title, installed_version, available_version, description="")` entries. `apply(update_id)` runs only after a user chooses an update and confirms it in Extensions. The wrapper also offers `check(provider_id)` and `apply(provider_id, update_id)`, with the latter returning a future. Both require `update_providers` and `network`. A plugin that applies updates to arbitrary files must also request `files.write` and use the file or download API accordingly. JAVBED never silently applies these updates.

Plugin Manager's GitHub Releases update flow stages the previous plugin and restores it if the new version fails to enable. Updates are never automatic.

Each registration requires its matching permission. Importers also require `files.read`; update providers also require `network`; metadata providers also require `instances.read`. Server providers appear in the Servers creation selector as well as Extensions. To create a server through SERVLI, a plugin can use `context.servers` with its corresponding permission, or implement its own provider in the registered callback. To launch an external game process, request `process.launch` and use `context.process.launch`. These callbacks must handle their own provider-specific validation. The extensions are intentional entry points; JAVBED does not grant plugins its `MainWindow` or mutable internal state.

## Debugging and development

Enable **Settings → Advanced → Developer Mode** to show paths, API version, load duration, and **RELOAD** in Plugin Manager. Reload removes registrations and imports a new module instance. Open per-plugin logs from the plugin card. To debug a broken startup, run with `--safe-mode`, inspect the log, then disable or remove the plugin. The example at [`examples/plugins/hello-javbed`](../../examples/plugins/hello-javbed) is never installed or enabled automatically.
