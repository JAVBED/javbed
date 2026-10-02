"""Small, versioned objects intended for third-party plugins."""

from dataclasses import dataclass

JAVBED_PLUGIN_API = 1


class JavbedPlugin:
    def on_load(self, context):
        pass

    def on_enable(self):
        pass

    def on_disable(self):
        pass

    def on_unload(self):
        pass


@dataclass(frozen=True)
class InstanceInfo:
    name: str
    version: str
    loader: str
    era: str
    path: str


@dataclass(frozen=True)
class ServerInfo:
    name: str
    provider: str
    minecraft_version: str
    running: bool
    port: int | None


@dataclass(frozen=True)
class WorldInfo:
    name: str
    edition: str
    instance: str
    path: str
    version: str
