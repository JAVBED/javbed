# JAVBED

PySide6 desktop launcher for Java, Bedrock, Education, Legacy Console and Minecraft servers.

JAVBED manages its own backend engines. It downloads compatible release binaries from the JAVBED GitHub organization into its private application-data directory instead of relying on similarly named executables on PATH.

## Run from source

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .
    javbed

On macOS/Linux use `source .venv/bin/activate`.

## Releases

The GitHub Actions release workflow runs only for version tags matching `v*`. Push a tag such as `v0.1.0` to build and publish the platform packages.
