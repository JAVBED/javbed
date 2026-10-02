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
  "permissions": ["commands", "ui", "settings.read", "settings.write"]
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

The module is imported only when an approved plugin is enabled. `create_plugin()` must return a `JavbedPlugin`. Relative imports from files in the plugin directory are supported. On disable or reload, JAVBED removes all event, command, UI, file, and URI registrations. A callback exception is logged and quarantines that plugin for the current session; other plugins and core remain active. Plugin startup duration is recorded, and loads over one second are logged. Python cannot safely terminate arbitrary code running in the launcher process, so a malicious or permanently blocking plugin still requires Safe Mode and manual removal.

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

`files.write`, `network`, `servers.console`, `process.launch`, and `accounts.read` are marked high risk in the review dialog. Some permission names reserve future API surface; declaration alone does not grant a method that is not documented below. Plugin code itself is unsandboxed Python. `accounts.read` returns only alias, username, and UUID from JAVBED's safe account reader; tokens and passwords are never passed through `PluginContext`.

`context.api_version` is `1`. `context.logger` prefixes entries with the plugin ID. `context.paths.data` is the plugin's private data directory. `context.settings.get(key, default)` requires `settings.read`; `context.settings.set(key, JSON_value)` requires `settings.write` and saves to that plugin's own `settings.json`. `context.notifications.show(title=..., message=...)` requires `notifications`.

`context.instances.list()` and `get(name)` return immutable `InstanceInfo` objects with name, version, loader, era, and path. They require `instances.read`. `launch`, `create`, `clone`, and `delete` require their corresponding launch or modify permission and return `Future[bool]` for backend success. Plugins do not need to parse JAVLI output. `open_folder(name)` returns the validated instance path. `context.servers.list()` and `get(name)` return immutable `ServerInfo` objects. `start`, `stop`, `restart`, `backup`, and `send_command` use SERVLI through JAVBED and return `Future[bool]`. `send_command` requires `servers.console`. `context.worlds.list()` returns `WorldInfo`; `backup(name, instance="")` returns a `Future[Path]`. Synchronous list/get calls should be made from a background task when the underlying scan may be slow.

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

Commands appear in Ctrl+K and are removed on disable. IDs must be unique. Event callback exceptions are isolated. API 1 emits `javbed.started`, `javbed.closing`, `account.changed`, `game.launching`, `game.started`, `game.exited`, `game.crashed`, `instance.created`, `instance.updated`, `instance.deleted`, `instance.launching`, `instance.started`, `instance.exited`, `mod.installed`, `mod.removed`, `mod.updated`, `world.backed_up`, `world.restored`, `server.created`, `server.started`, `server.stopped`, `server.crashed`, `server.backup_completed`, `download.started`, `download.progress`, `download.completed`, and `download.failed` when the corresponding core workflow reports them. Event payloads are keyword arguments and contain no authentication secrets. Some events rely on a backend reporting a launch PID or a core operation completing successfully.

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

`context.files.register_handler(extension=".example", callback=...)` requires `files.read`. The callback receives a `Path` from a dropped local file. Extension conflicts between plugins are rejected. If a plugin handles a built-in extension, JAVBED asks the user which handler to use.

`context.deep_links.register(callback)` requires `deep_links`. Links have the form `javbed://plugin/<plugin-id>/<route>` and the callback receives the decoded route string. Core routes cannot be overridden; unsafe or oversized links are rejected.

## Debugging and development

Enable **Settings → Advanced → Developer Mode** to show paths, API version, load duration, and **RELOAD** in Plugin Manager. Reload removes registrations and imports a new module instance. Open per-plugin logs from the plugin card. To debug a broken startup, run with `--safe-mode`, inspect the log, then disable or remove the plugin. The example at [`examples/plugins/hello-javbed`](../../examples/plugins/hello-javbed) is never installed or enabled automatically.
