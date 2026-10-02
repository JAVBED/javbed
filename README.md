# JAVBED

## Plugin system

Extend JAVBED without modifying the launcher. Install a plugin directory, `.zip`, or `.javbedplugin` from **Settings → Plugins**. JAVBED reviews permissions before enabling third-party code, keeps plugin data separate, and supports `--safe-mode` to start without plugins. There is no public plugin marketplace. See the [Plugin API 1 developer guide](docs/plugins/README.md) and the [disabled example plugin](examples/plugins/hello-javbed).

PySide6 desktop launcher for Java, Bedrock, Education, Legacy Console and Minecraft servers.

JAVBED manages its own backend engines. It downloads compatible release binaries from the JAVBED GitHub organization into its private application-data directory. A path explicitly chosen in Settings takes priority; otherwise an executable on PATH is preferred over a managed copy.

## Run from source

Use the launcher for your system. It creates `.venv` and installs the project on first run:

- Windows: double-click `start.bat`.
- Linux: run `./start.sh`.
- macOS: double-click `start.command`.

Or set up the environment manually:

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .
    javbed

On macOS/Linux use `source .venv/bin/activate`.

## Finding games

If Dungeons, Dungeons II, or Legends is not detected, use **Locate Game** on its page to select the installed executable. Story Mode has a separate **Locate Installation** control for each season. Its ISO download can be paused and resumed by choosing the same save path again.

Engine updates run in the background and verify the SHA-256 digest supplied with each GitHub release asset before installing it.

The Home dashboard shows the active JAVLI account, recent play sessions, quick launch targets, detected games, and SERVLI status. JAVBED reads only public profile fields from JAVLI's account data and uses JAVLI for sign-in and account switching. Game sessions lasting at least ten seconds are saved to JAVBED's `history.json` when the launched process can be observed. A skin avatar is fetched from Crafatar when the account has a Minecraft UUID.

The launcher opens on Java Play by default, with a fixed game sidebar, an installation selector, and a central Play button. Bedrock, Education, Legacy Console, Dungeons, Dungeons II, Legends, and Story Mode use the same Play layout, with their installation, season, and engine controls still available. Java's Installations, Mods, and Modpacks tabs stay in the header; Resource Packs, Shaders, Accounts, version channels, and Java engine controls are in **More**. Activity and Doctor remain available from the button beside Settings and from Ctrl+K. Existing startup-page preferences are preserved.

The Java **Instances** tab lists JAVLI instances as cards with version, loader, mod count, play history, and launch controls. Create instances there; each card offers editing, cloning, folder access, icon changes, and confirmed deletion. Memory and window preferences are saved per instance in JAVBED and passed to current JAVLI versions at launch. JAVLI chooses and installs the appropriate Java runtime automatically, or JAVBED can request Java 8, 17, 21, or 25 for an instance.

The Java **Mods**, **Modpacks**, **Resource Packs**, and **Shaders** tabs browse compatible projects with graphical cards. Mods and modpacks support Modrinth and CurseForge search; CurseForge needs an API key in Settings. Install actions check the exact Minecraft version and loader before asking JAVLI to install. The Installed view can enable, disable, update, and remove tracked mods; updates keep a safety copy until the replacement succeeds. Modpacks create isolated JAVLI instances, and the Modpacks tab can open a local `.mrpack`. Current JAVLI source is required for local pack import and explicit pack-version selection. Shader installation explains when a shader loader is missing and can install compatible Iris through JAVLI for supported loaders.

The **Worlds** page finds vanilla Java and JAVLI worlds, plus accessible Bedrock and Education worlds. It can back up, restore, duplicate, export, open, launch, and move worlds to JAVBED's recoverable trash. Restore creates a fresh backup first. You can set Bedrock and Education world folders in Settings if automatic discovery cannot reach them.

Java instances can be exported as versioned `.javbed` manifests for reference. They contain metadata and provider references, never Minecraft binaries or local mod files. Instance import has been removed from JAVBED. Drag `.mrpack`, mod JARs, resource pack ZIPs, shader ZIPs, or Story Mode ISOs onto the window to open the corresponding installation flow.

The Java instance menu includes **Play in Safe Mode**. JAVBED temporarily renames that instance's mod JARs, then restores them after Minecraft exits; a recovery journal survives launcher restarts. When a Java instance exits abnormally or writes a new crash report, Crash Doctor checks recent evidence for common mod, loader, Java, memory, and library errors. Its dialog links to the log, crash report, mods folder, and Safe Mode. Diagnoses are suggestions when the evidence is ambiguous.

The **Servers → Dashboard** tab uses SERVLI's structured server and backup listings. Server cards show software, Minecraft version, status, PID, RAM, port, and uptime. Open a server's console or settings for live log output, commands, player moderation, common and advanced properties, backups, plugins, mods, and server folders. SERVLI owns server start, stop, restore, and backup operations. Backup schedules (30 minutes, hourly, every N hours, daily, or on stop) and retention run in SERVLI while the server is running, even after JAVBED closes. The current SERVLI source is needed for `--json` listings and scheduling.

The **Activity** page shows downloads and backend jobs, including real byte progress and speed for Story Mode ISOs and managed engine downloads. Jobs without byte reporting show their current stage without an invented percentage. **Updates → UPDATE ALL** checks JAVBED, updates managed engines and tracked Java mods, reports newer compatible modpacks, and updates stopped SERVLI servers where the backend supports an in-place software update. Running servers and BDS version changes are skipped. The **Doctor** page checks network access, account metadata, engines, Java runtimes, paths, bundled artwork, writable data directories, Gaming Services on Windows, and a configured CurseForge API key. Missing engines can be installed from Doctor.

On first run, JAVBED scans for editions, engines, runtimes, and existing JAVLI instances. You can continue into the launcher or open Settings.

Press **Ctrl+K** to search launcher actions, games, instances, servers, and mods. Windows packaged builds register the per-user `javbed://` protocol on first launch; links for Java versions, instances, servers, Modrinth searches, and Settings open the corresponding launcher view. Settings supports an accent color, compact navigation, artwork preference, startup page, server backup defaults, and launch behavior. Completion and crash notices appear quietly in the status bar.

Java settings can set an absolute Minecraft game directory for direct version launches, a default fullscreen launch preference, and an explicit Java executable. Instance game directories remain isolated. The optional startup update check reports new JAVBED releases without installing them automatically.

To use portable mode, create an empty `portable.txt` beside the packaged JAVBED executable before starting it. JAVBED settings, cache, managed engines, and launcher state then use `JAVBED-data` beside the executable. Existing data is left where it is; portable mode does not migrate it automatically. In a source checkout, place `portable.txt` next to `javbed_main.py`.

## Releases

Use the manually dispatched **Build and Release JAVBED** workflow to build and publish platform packages. Leave its version input blank to choose the next patch tag automatically. The Windows release includes `installer.msi`, which bundles the JAVBED build, Store helper, and the latest verified Windows x64 releases of JAVLI, BEDLI, EDULI, LEGLI, and SERVLI. It installs JAVBED in Program Files, adds the launcher and engine directories to the system PATH, and creates a JAVBED Launcher Start Menu shortcut. Pushes to `main` and pull requests run the test workflow; they do not publish releases.
