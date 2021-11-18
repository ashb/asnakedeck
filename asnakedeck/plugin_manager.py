from __future__ import annotations

import importlib.metadata
import logging
import os
from collections import defaultdict
from functools import cached_property
from types import FunctionType
from typing import TYPE_CHECKING, Callable, Generic, Mapping, TypeVar

import attr

if TYPE_CHECKING:
    from .types import KeyHandler

# Set a couple of directory paths for later use.
# This follows the spec at the following address:
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME")
if not XDG_CONFIG_HOME:
    XDG_CONFIG_HOME = os.path.join(os.environ["HOME"], ".config")
CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, "snakedeck")

XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME")
if not XDG_STATE_HOME:
    XDG_STATE_HOME = os.path.join(os.environ["HOME"], ".local", "state")
STATE_DIR = os.path.join(XDG_STATE_HOME, "snakedeck")

T = TypeVar("T", Callable, FunctionType)


class PluginManager:
    @attr.define(init=False, repr=False)
    class LazyPluginDict(Generic[T], Mapping[str, T]):
        """
        Helper class to load plugins by name on demand.

        This dict-like class looks at the name of the entrypoint and only loads the specific plugin when it is
        asked for.

        For example, this entry_point specification::

            asnakedeck.key_handler =
                foo = example_displayer_plugin

        Would only be imported when ``plugin["foo"]`` was accessed.
        """

        entrypoint_name: str
        pm: PluginManager
        store: dict[str, T] = attr.Factory(dict)
        entrypoints: dict[str, importlib.metadata.EntryPoint] | None = None

        def register(self, name: str, handler: T):
            if name in self.store:
                raise ValueError(f"{name!r} already registered")
            self.store[name] = handler

        def __init__(self, pm: PluginManager, entrypoint_name: str):
            self.__attrs_init__(pm=pm, entrypoint_name=entrypoint_name)

        def __get(self, name) -> T | None:
            if val := self.store.get(name, None):
                return val
            # Not already registered, not already loaded, look in entrypoints

            if not self.entrypoints:
                self.entrypoints = self.pm.setuptools_entrypoints[self.entrypoint_name]

            ep: importlib.metadata.EntryPoint
            if ep := self.entrypoints.get(name, None):
                logging.info("Loading %r", ep.name)
                handler: T = ep.load()  # type: ignore
                self.register(name, handler)
                return handler
            return None

        def __getattr__(self, name: str) -> T:
            if val := self.__get(name):
                return val
            raise AttributeError(f"{self} has no plugin {name!r}")

        def __getitem__(self, name: str) -> T:
            if val := self.__get(name):
                return val
            raise KeyError(f"{self} has no plugin {name!r}")

        def __iter__(self):
            yield from self._store

        def __len__(self):
            return len(self._store)

        def __repr__(self) -> str:
            return f"<{type(self).__name__} entrypoint_name={self.entrypoint_name!r}>"

    @cached_property
    def key_handlers(self) -> Mapping[str, type[KeyHandler]]:
        # Only load entrypoints on demand.
        return self.LazyPluginDict(self, "key_handler")  # type: ignore

    @cached_property
    def setuptools_entrypoints(self) -> dict[str, dict[str, importlib.metadata.EntryPoint]]:
        eps: dict[str, dict[str, importlib.metadata.EntryPoint]] = defaultdict(dict)
        for dist in list(importlib.metadata.distributions()):
            for ep in dist.entry_points:
                if not ep.group.startswith("asnakedeck."):
                    continue
                _, kind = ep.group.split(".", 1)
                eps[kind][ep.name] = ep
        return eps
