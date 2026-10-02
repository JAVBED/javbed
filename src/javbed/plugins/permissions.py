"""API capabilities; these do not form an operating-system sandbox."""

from dataclasses import dataclass

KNOWN = frozenset({
    "ui", "commands", "instances.read", "instances.modify", "instances.launch",
    "mods.read", "mods.modify", "worlds.read", "worlds.modify", "servers.read",
    "servers.modify", "servers.console", "accounts.read", "files.read",
    "files.write", "network", "settings.read", "settings.write", "notifications",
    "deep_links", "process.launch",
    "integrations", "server_providers", "importers", "diagnostics",
    "java_tools", "metadata", "update_providers",
})
HIGH_RISK = frozenset({"files.write", "network", "servers.console", "process.launch", "accounts.read"})


@dataclass(frozen=True)
class PermissionSet:
    names: frozenset[str]

    @classmethod
    def parse(cls, value):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("permissions must be a list of strings")
        if len(value) != len(set(value)):
            raise ValueError("duplicate permission")
        unknown = set(value) - KNOWN
        if unknown:
            raise ValueError("Unknown plugin permission: " + ", ".join(sorted(unknown)))
        return cls(frozenset(value))

    def require(self, name: str):
        if name not in self.names:
            raise PermissionError(f"Plugin permission required: {name}")

    def __contains__(self, name):
        return name in self.names
