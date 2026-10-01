# JAVBED

PySide6 desktop launcher for Java, Bedrock, Education, Legacy Console and Minecraft servers.

JAVBED manages its own backend engines. It downloads compatible release binaries from the JAVBED GitHub organization into its private application-data directory instead of relying on similarly named executables on PATH.

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

## Releases

The GitHub Actions release workflow runs only for version tags matching `v*`. Push a tag such as `v0.1.0` to build and publish the platform packages.
