"""Strict, import-free plugin metadata validation."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .permissions import PermissionSet

ID = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+\Z")
VERSION = re.compile(r"\d+(?:\.\d+){1,3}\Z")
ENTRY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.py\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SPEC = re.compile(r"(>=|==|<=|>|<)\s*(\d+(?:\.\d+){1,3})\Z")
REQUIRED = {"manifest_version", "api_version", "id", "name", "version", "description", "author", "entrypoint", "javbed", "permissions"}
OPTIONAL = {"homepage", "dependencies", "update", "icon"}


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Invalid version: " + str(value))
    return tuple(map(int, value.split(".")))


def compare(left: str, right: str) -> int:
    a, b = version_tuple(left), version_tuple(right)
    width = max(len(a), len(b))
    return (a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))) - (a + (0,) * (width - len(a)) < b + (0,) * (width - len(b)))


def satisfies(version: str, requirement: str) -> bool:
    match = SPEC.fullmatch(requirement) if isinstance(requirement, str) else None
    if not match:
        raise ValueError("Invalid dependency version requirement")
    result = compare(version, match.group(2))
    return {">=": result >= 0, "==": result == 0, "<=": result <= 0, ">": result > 0, "<": result < 0}[match.group(1)]


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    author: str
    entrypoint: str
    minimum_version: str
    maximum_version: str | None
    permissions: PermissionSet
    dependencies: dict[str, str]
    homepage: str = ""
    icon: str = ""
    update_repo: str = ""
    api_version: int = 1

    @classmethod
    def from_data(cls, data):
        if not isinstance(data, dict) or REQUIRED - data.keys() or data.keys() - REQUIRED - OPTIONAL:
            raise ValueError("Manifest has missing or unsupported fields")
        if type(data["manifest_version"]) is not int or data["manifest_version"] != 1:
            raise ValueError("Unsupported manifest version")
        if type(data["api_version"]) is not int or data["api_version"] != 1:
            raise ValueError("Unsupported plugin API version")
        identifier = data["id"]
        if not isinstance(identifier, str) or len(identifier) > 120 or not ID.fullmatch(identifier):
            raise ValueError("Invalid plugin ID")
        strings = ("name", "version", "description", "author", "entrypoint")
        if any(not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 500 for key in strings):
            raise ValueError("Invalid plugin metadata")
        if any(any(ord(char) < 32 or char in "<>" for char in data[key]) for key in strings):
            raise ValueError("Plugin metadata contains unsafe text")
        version_tuple(data["version"])
        if not ENTRY.fullmatch(data["entrypoint"]):
            raise ValueError("Entrypoint must be a Python file in the plugin root")
        for key in ("homepage", "icon"):
            if key in data and (not isinstance(data[key], str) or len(data[key]) > 500):
                raise ValueError("Invalid " + key)
        if data.get("homepage") and not data["homepage"].startswith("https://"):
            raise ValueError("Plugin homepage must use HTTPS")
        if data.get("icon") and ("/" in data["icon"] or "\\" in data["icon"] or data["icon"] in (".", "..")):
            raise ValueError("Icon must be in the plugin root")
        javbed = data["javbed"]
        if not isinstance(javbed, dict) or set(javbed) != {"minimum_version", "maximum_version"}:
            raise ValueError("Invalid JAVBED version bounds")
        minimum = javbed["minimum_version"]
        maximum = javbed["maximum_version"]
        version_tuple(minimum)
        if maximum is not None:
            version_tuple(maximum)
            if compare(maximum, minimum) < 0:
                raise ValueError("Maximum JAVBED version precedes minimum")
        dependencies = data.get("dependencies", {})
        if not isinstance(dependencies, dict) or any(not isinstance(key, str) or not ID.fullmatch(key) or not isinstance(value, str) or not SPEC.fullmatch(value) for key, value in dependencies.items()):
            raise ValueError("Invalid plugin dependencies")
        update = data.get("update", {})
        if not isinstance(update, dict) or (update and (set(update) != {"type", "repo"} or update["type"] != "github" or not isinstance(update["repo"], str) or not REPO.fullmatch(update["repo"]))):
            raise ValueError("Invalid plugin update source")
        return cls(identifier, data["name"], data["version"], data["description"], data["author"], data["entrypoint"], minimum, maximum, PermissionSet.parse(data["permissions"]), dict(dependencies), data.get("homepage", ""), data.get("icon", ""), update.get("repo", ""), data["api_version"])

    @classmethod
    def read(cls, directory: Path):
        path = directory / "javbed-plugin.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
            raise ValueError("Missing or oversized javbed-plugin.json")
        manifest = cls.from_data(json.loads(path.read_text(encoding="utf-8")))
        entry = directory / manifest.entrypoint
        if entry.is_symlink() or not entry.is_file() or entry.resolve().parent != directory.resolve():
            raise ValueError("Missing or unsafe plugin entrypoint")
        return manifest
