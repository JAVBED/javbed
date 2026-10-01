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

## Releases

Use the manually dispatched **Build and Release JAVBED** workflow to build and publish platform packages. Leave its version input blank to choose the next patch tag automatically. Pushes to `main` and pull requests run the test workflow; they do not publish releases.
