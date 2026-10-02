"""Owner-scoped extension points. Disabling an owner removes all its entries."""

import re
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

    def subscribe(self, owner, event, callback):
        if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_.]+", event) or not callable(callback):
            raise ValueError("Invalid event subscription")
        self._next += 1
        token = self._next
        self._subscriptions[token] = (owner, event, callback)
        return token

    def unsubscribe(self, token, owner=None):
        item = self._subscriptions.get(token)
        if item and (owner is None or item[0] == owner):
            self._subscriptions.pop(token, None)

    def remove_owner(self, owner):
        for token, item in list(self._subscriptions.items()):
            if item[0] == owner:
                self.unsubscribe(token)

    def emit(self, event, **data):
        for token, (owner, subscribed, callback) in list(self._subscriptions.items()):
            if token not in self._subscriptions:
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

    def register(self, owner, *, id, title, callback, description="", keywords=(), icon=""):
        if not isinstance(id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,120}", id) or not isinstance(title, str) or not title.strip() or not callable(callback):
            raise ValueError("Invalid command")
        if id in self._commands:
            raise ValueError("Duplicate command ID: " + id)
        if not isinstance(description, str) or not isinstance(icon, str) or not isinstance(keywords, (list, tuple)) or any(not isinstance(word, str) for word in keywords):
            raise ValueError("Invalid command metadata")
        self._commands[id] = Command(owner, id, title, description, tuple(keywords), icon, callback)
        return id

    def all(self):
        return tuple(self._commands.values())

    def invoke(self, id):
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
        for key, command in list(self._commands.items()):
            if command.owner == owner:
                del self._commands[key]


class UIRegistry:
    KINDS = frozenset({"page", "settings_page", "instance_action", "server_action", "world_action"})

    def __init__(self, on_error):
        self._items = {}
        self._on_error = on_error
        self.changed = lambda: None

    def register(self, owner, kind, *, id, title, callback):
        if kind not in self.KINDS or not isinstance(id, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,120}", id) or not isinstance(title, str) or not title.strip() or not callable(callback):
            raise ValueError("Invalid UI extension")
        if id in self._items:
            raise ValueError("Duplicate UI extension ID: " + id)
        self._items[id] = UIExtension(owner, id, title, callback, kind)
        self.changed()
        return id

    def all(self, kind):
        return tuple(item for item in self._items.values() if item.kind == kind)

    def invoke(self, item, *args):
        if self._items.get(item.id) is not item:
            return None
        try:
            return item.callback(*args)
        except Exception as exc:
            self._on_error(item.owner, "UI extension " + item.id, exc)
            return None

    def remove_owner(self, owner):
        changed = False
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

    def register(self, owner, route, callback):
        if route in self._items:
            raise ValueError("Conflicting handler: " + route)
        if not callable(callback):
            raise ValueError("Handler must be callable")
        self._items[route] = (owner, callback)

    def owners(self, route):
        return self._items.get(route)

    def invoke(self, route, *args):
        item = self._items.get(route)
        if not item:
            return False
        try:
            item[1](*args)
            return True
        except Exception as exc:
            self._on_error(item[0], "handler " + route, exc)
            return False

    def remove_owner(self, owner):
        for key, value in list(self._items.items()):
            if value[0] == owner:
                del self._items[key]
