"""JAVBED Plugin API 1 runtime. Python plugins are trusted executable code."""

JAVBED_PLUGIN_API = 1

from .manager import PluginManager

__all__ = ["JAVBED_PLUGIN_API", "PluginManager"]
