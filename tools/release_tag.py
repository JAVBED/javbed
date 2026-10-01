"""Choose the next release tag for the manually dispatched workflow."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


VERSION = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


def version_parts(value: str) -> tuple[int, int, int] | None:
    match = VERSION.fullmatch(value)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def choose_tag(requested: str, existing: set[str]) -> str:
    requested = requested.strip()
    if requested:
        candidate = requested if requested.startswith("v") else "v" + requested
        if candidate in existing:
            raise ValueError(f"Release tag {candidate} already exists.")
        parts = version_parts(candidate)
        if parts is None:
            raise ValueError(
                f"Invalid version {requested!r}. Enter a version such as 1.2.3 "
                "(or leave it blank to select the next patch)."
            )
        tag = "v" + ".".join(map(str, parts))
    else:
        versions = [version_parts(tag) for tag in existing if tag.startswith("v")]
        valid = [parts for parts in versions if parts is not None]
        if valid:
            major, minor, patch = max(valid)
            tag = f"v{major}.{minor}.{patch + 1}"
        else:
            tag = "v0.1.0"
    if tag in existing:
        raise ValueError(f"Release tag {tag} already exists.")
    if any(version_parts(old) == version_parts(tag) for old in existing if old.startswith("v")):
        raise ValueError(f"Version {tag} already exists under a shorter legacy tag.")
    return tag


def main() -> None:
    subprocess.run(["git", "fetch", "--tags", "--force"], check=True)
    tags = subprocess.check_output(["git", "tag", "--list"], text=True).splitlines()
    try:
        tag = choose_tag(os.environ.get("REQUESTED", ""), set(tags))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"Release tag: {tag}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"tag={tag}\n")


if __name__ == "__main__":
    main()
