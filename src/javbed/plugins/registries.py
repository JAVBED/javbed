"""Owner-scoped extension points. Disabling an owner removes all its entries."""

import re
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Command:
    owner: str
    id: str
    title: str
    description: str
    keywords: tuple[str, ...]
    icon: str
    callback: Callable


@dataclass(frozen=True)
class UIExtension:
    owner: str
    id: str
    title: str
    callback: Callable
    kind: str


class EventBus:
    def __init__(self, on_error):
        self._subscriptions = {}
        self._on_error = on_error
        self._next = 0
        self._lock = threading.RLock()

    def subscribe(self, owner, event, callback):
        if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_.]+", event) or not callable(callback):
            raise ValueError("Invalid event subscription")
        with self._lock:
            self._next += 1
            token = self._next
            self._subscriptions[token] = (owner, event, callback)
        return token

    def unsubscribe(self, token, owner=None):
        with self._lock:
            item = self._subscriptions.get(token)
            if item and (owner is None or item[0] == owner):
                self._subscriptions.pop(token, None)

    def remove_owner(self, owner):
        with self._lock:
            items = tuple(self._subscriptions.items())
        for token, item in items:
            if item[0] == owner:
                self.unsubscribe(token)

    def emit(self, event, **data):
        with self._lock:
            items = tuple(self._subscriptions.items())
        for token, (owner, subscribed, callback) in items:
            with self._lock:
                active = token in self._subscriptions
            if not active:
                continue
            if subscribed == event:
                try:
                    callback(**data)
                except Exception as exc:
                    self._on_error(owner, "event " + event, exc)


class CommandRegistry:
    def __init__(self, on_error):
        self._commands = {}
        self._on_error = on_error
        self._lock = threading.RLock()

    def register(self, owner, *, id, title, callback, description="", keywords=(), icon=""):
        if not isinstance(id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,120}", id) or not isinstance(title, str) or not title.strip() or not callable(callback):
            raise ValueError("Invalid command")
        if not isinstance(description, str) or not isinstance(icon, str) or not isinstance(keywords, (list, tuple)) or any(not isinstance(word, str) for word in keywords):
            raise ValueError("Invalid command metadata")
        with self._lock:
            if id in self._commands:
                raise ValueError("Duplicate command ID: " + id)
            self._commands[id] = Command(owner, id, title, description, tuple(keywords), icon, callback)
        return id

    def all(self):
        with self._lock:
            return tuple(self._commands.values())

    def invoke(self, id):
        with self._lock:
            command = self._commands.get(id)
        if not command:
            return False
        try:
            command.callback()
            return True
        except Exception as exc:
            self._on_error(command.owner, "command " + id, exc)
            return False

    def remove_owner(self, owner):
        with self._lock:
            for key, command in list(self._commands.items()):
                if command.owner == owner:
                    del self._commands[key]


class UIRegistry:
    KINDS = frozenset({"page", "settings_page", "instance_action", "server_action", "world_action"})

    def __init__(self, on_error):
        self._items = {}
        self._on_error = on_error
        self.changed = lambda: None
        self._lock = threading.RLock()

    def register(self, owner, kind, *, id, title, callback):
        if kind not in self.KINDS or not isinstance(id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,120}", id) or not isinstance(title, str) or not title.strip() or not callable(callback):
            raise ValueError("Invalid UI extension")
        with self._lock:
            if id in self._items:
                raise ValueError("Duplicate UI extension ID: " + id)
            self._items[id] = UIExtension(owner, id, title, callback, kind)
        self.changed()
        return id

    def all(self, kind):
        with self._lock:
            return tuple(item for item in self._items.values() if item.kind == kind)

    def invoke(self, item, *args):
        with self._lock:
            if self._items.get(item.id) is not item:
                return None
        try:
            return item.callback(*args)
        except Exception as exc:
            self._on_error(item.owner, "UI extension " + item.id, exc)
            return None

    def remove_owner(self, owner):
        changed = False
        with self._lock:
            for key, item in list(self._items.items()):
                if item.owner == owner:
                    del self._items[key]
                    changed = True
        if changed:
            self.changed()


class RouteRegistry:
    def __init__(self, on_error):
        self._items = {}
        self._on_error = on_error
        self._lock = threading.RLock()

    def register(self, owner, route, callback):
        if not callable(callback):
            raise ValueError("Handler must be callable")
        with self._lock:
            if route in self._items:
                raise ValueError("Conflicting handler: " + route)
            self._items[route] = (owner, callback)

    def owners(self, route):
        with self._lock:
            return self._items.get(route)

    def routes(self):
        with self._lock:
            return tuple(self._items)

    def unregister(self, owner, route):
        with self._lock:
            if route in self._items and self._items[route][0] == owner:
                del self._items[route]

    def invoke(self, route, *args):
        item = self.owners(route)
        if not item:
            return False
        try:
            item[1](*args)
            return True
        except Exception as exc:
            self._on_error(item[0], "handler " + route, exc)
            return False

    def remove_owner(self, owner):
        with self._lock:
            for key, value in list(self._items.items()):
                if value[0] == owner:
                    del self._items[key]


@dataclass(frozen=True)
class Contribution:
    owner: str
    kind: str
    id: str
    title: str
    callback: Callable


class ContributionRegistry:
    """Named, owner-scoped service hooks; never passes core objects to plugins."""

    KINDS = frozenset({"game", "server_provider", "importer", "diagnostic", "java_tool", "metadata", "update_provider"})

    def __init__(self, on_error):
        self._items = {}
        self._on_error = on_error
        self.changed = lambda: None
        self._lock = threading.RLock()

    def register(self, owner, kind, *, id, title, callback):
        if kind not in self.KINDS or not isinstance(id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,120}", id) or not isinstance(title, str) or not title.strip() or not callable(callback):
            raise ValueError("Invalid plugin contribution")
        item = Contribution(owner, kind, id, title, callback)
        with self._lock:
            if id in self._items:
                raise ValueError("Duplicate contribution ID: " + id)
            self._items[id] = item
        self.changed()
        return id

    def all(self, kind):
        if kind not in self.KINDS:
            raise ValueError("Unknown contribution kind")
        with self._lock:
            return tuple(item for item in self._items.values() if item.kind == kind)

    def get(self, id):
        with self._lock:
            return self._items.get(id)

    def invoke_id(self, id, *args):
        item = self.get(id)
        return self.invoke(item, *args) if item else None

    def unregister(self, owner, id):
        with self._lock:
            found = id in self._items and self._items[id].owner == owner
            if found:
                del self._items[id]
        if found:
            self.changed()

    def invoke(self, item, *args):
        with self._lock:
            if self._items.get(item.id) is not item:
                return None
        try:
            result = item.callback(*args)
            return result.result(timeout=300) if isinstance(result, Future) else result
        except Exception as exc:
            self._on_error(item.owner, item.kind + " " + item.id, exc)
            return None

    def remove_owner(self, owner):
        removed = False
        with self._lock:
            for key, item in list(self._items.items()):
                if item.owner == owner:
                    del self._items[key]
                    removed = True
        if removed:
            self.changed()
