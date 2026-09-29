# JAVBED

PySide6 desktop GUI for the JAVBED family of Minecraft tools.

The user-facing app has exactly five sections: **Java, Bedrock, EDU, LCE, Servers**. Internally they map to javli, bedli, eduli, legli and servli.

## Run

    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .
    javbed

On macOS/Linux use `source .venv/bin/activate` instead.

## Engine discovery

The GUI checks for each engine on PATH, or you can point it directly at an executable with `JAVBED_JAVA`, `JAVBED_BEDROCK`, `JAVBED_EDU`, `JAVBED_LCE`, and `JAVBED_SERVERS`.
