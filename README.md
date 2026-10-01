# JAVBED

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

The Java **Instances** tab lists JAVLI instances as cards with version, loader, mod count, play history, and launch controls. Create and import instances there; each card offers editing, cloning, folder access, icon changes, and confirmed deletion. Memory and window preferences are saved per instance in JAVBED and passed to current JAVLI versions at launch. JAVLI chooses and installs the appropriate Java runtime automatically, or JAVBED can request Java 8, 17, 21, or 25 for an instance.

The Java **Mods**, **Modpacks**, **Resource Packs**, and **Shaders** tabs browse compatible projects with graphical cards. Mods and modpacks support Modrinth and CurseForge search; CurseForge needs an API key in Settings. Install actions check the exact Minecraft version and loader before asking JAVLI to install. The Installed view can enable, disable, update, and remove tracked mods; updates keep a safety copy until the replacement succeeds. Modpacks create isolated JAVLI instances, and the Modpacks tab can open a local `.mrpack`. Current JAVLI source is required for local pack import and explicit pack-version selection. Shader installation explains when a shader loader is missing and can install compatible Iris through JAVLI for supported loaders.

The **Worlds** page finds vanilla Java and JAVLI worlds, plus accessible Bedrock and Education worlds. It can back up, restore, duplicate, export, import, open, launch, and move worlds to JAVBED's recoverable trash. Restore creates a fresh backup first. You can set Bedrock and Education world folders in Settings if automatic discovery cannot reach them.

Java instances can be exported as versioned `.javbed` packages and reconstructed through JAVLI. Packages contain metadata and provider references, never Minecraft binaries or local mod files. The manifest lists local files that need manual reinstallation. Drag `.javbed`, `.mrpack`, mod JARs, resource pack ZIPs, shader ZIPs, world ZIPs, or Story Mode ISOs onto the window to open the corresponding import flow.

The Java instance menu includes **Play in Safe Mode**. JAVBED temporarily renames that instance's mod JARs, then restores them after Minecraft exits; a recovery journal survives launcher restarts. When a Java instance exits abnormally or writes a new crash report, Crash Doctor checks recent evidence for common mod, loader, Java, memory, and library errors. Its dialog links to the log, crash report, mods folder, and Safe Mode. Diagnoses are suggestions when the evidence is ambiguous.

## Releases

Use the manually dispatched **Build and Release JAVBED** workflow to build and publish platform packages. Leave its version input blank to choose the next patch tag automatically. Pushes to `main` and pull requests run the test workflow; they do not publish releases.
