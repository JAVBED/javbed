#!/usr/bin/env bash
set -e

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi

if ! .venv/bin/python -c 'import PySide6, javbed' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -e .
fi

exec .venv/bin/python -m javbed.app
