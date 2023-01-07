from __future__ import annotations

import asyncio
import functools
import itertools
import logging
import operator
import os
from asyncio.tasks import Task
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import attr
import yaml
from PIL import ImageFont
from StreamDeck.Transport.Transport import TransportError

from asnakedeck.types import Key

from . import platform

if TYPE_CHECKING:
    from StreamDeck.Devices.StreamDeck import StreamDeck

    from .plugin_manager import PluginManager


log = logging.getLogger(__name__)


@attr.define(slots=False)
class Deck:
    hardware: StreamDeck
    plugin_manager: PluginManager
    keys: dict[int, Key] = attr.Factory(dict)
    image_size: tuple[int, int] = attr.ib(init=False)

    def __attrs_post_init__(self):
        platform.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # But don't start the read thread just yet!
        self.hardware.device.open()
        self.hardware.set_key_callback_async(self.on_keypress)
        self.image_size = self.hardware.key_image_format()["size"]

        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "Deck %s is a %s, serial number %s.",
                self.hardware.id(),
                self.hardware.DECK_TYPE,
                self.serial_number,
            )

        self.load_config()

        if not platform.WINDOWS:
            from .platform.linux import watch_file_for_changes

            async def file_change(_):
                self.load_config()

            self.config_watcher_task = asyncio.create_task(watch_file_for_changes(self.config_file_path, file_change), name="config-watcher")
            self.config_watcher_task.add_done_callback(self.on_task_complete)
        else:
            self.config_watcher_task = None

    def open(self):
        self.hardware.open()
        assert self.hardware.read_thread
        self.hardware.read_thread.setName(f"DeckThread-{self.serial_number}")

    def __hash__(self):
        return hash(self.serial_number)

    @property
    def tasks(self) -> Iterable[Task]:
        if self.config_watcher_task and not self.config_watcher_task.done():
            yield self.config_watcher_task
        yield from self.key_tasks

    def on_task_complete(self, task):
        log.info("Closing down")
        self.close()
        self.config_watcher_task = None

    def __del__(self):
        if self.hardware.connected():
            self.close()

        for key in self.keys.values():
            for task in key.tasks:
                task.cancel("Deck going away")

    @cached_property
    def config_file_path(self) -> Path:
        return platform.CONFIG_DIR / (self.serial_number + ".yaml")

    @cached_property
    def serial_number(self) -> str:
        return self.hardware.get_serial_number()  # type: ignore

    def clear(self):
        # Clear all keys
        self.hardware.reset()
        for key in range(self.hardware.KEY_COUNT):
            self.hardware.set_key_image(key, self.hardware.BLANK_KEY_IMAGE)
        self.hardware.set_brightness(80)
        self.keys.clear()

    @property
    def key_tasks(self) -> Iterable[Task]:
        tasks = operator.attrgetter('tasks')
        return itertools.chain.from_iterable(map(tasks, self.keys.values()))

    def close(self, reset=True):
        for task in self.key_tasks:
            log.debug("Cancelling task %r: %s/%s", task.get_name(), task.cancelled(), task.done())
            task.cancel("Deck going away")

        # Work around issue where the deck doesn't close proplery and segfaults in usbi_mutex_destroy
        if self.hardware.read_thread:
            self.hardware.run_read_thread = False
            self.hardware.read_thread.join()
            self.hardware.read_thread = None
        if self.hardware.connected():
            if reset:
                try:
                    self.hardware.reset()
                except TransportError:
                    pass
            self.hardware.close()

    @functools.lru_cache
    def _get_font(self, face: str, size: int):
        return ImageFont.truetype(platform.resolve_font(face), size)

    @cached_property
    def label_font(self) -> ImageFont.FreeTypeFont:
        font = self.config.get("label_font", {"face": platform.DEFAULT_FONT, "size": 20})
        return self._get_font(font["face"], font["size"])

    @cached_property
    def emoji_font(self) -> ImageFont.FreeTypeFont:
        font = self.config.get("emoji_font", {"face": platform.EMOJI_FONT, "size": 109})
        return self._get_font(font["face"], font["size"])

    def load_config(self):
        if not self.config_file_path.is_file():
            log.warning(f"Deck {self.serial_number} has no configuration file ({self.config_file_path}).")
            return
        log.debug(f"Deck {self.serial_number} loaded config from {self.config_file_path}.")
        config = yaml.safe_load(self.config_file_path.read_text())

        # Support snakedeck format where config is just a list
        if isinstance(config, list):
            config = {"keys": config}

        if not config:
            log.warning(f"Deck {self.serial_number} has no configuration in {self.config_file_path!r}.")
            return

        self.config = config

        for key in self.keys.values():
            for task in key.tasks:
                task.cancel("Config reloaded")

        for key_config in self.config["keys"]:
            if "line" in key_config and "column" in key_config:
                # FIXME validate line/column
                key_number = (key_config["line"] - 1) * self.hardware.KEY_COLS + key_config["column"] - 1
                key = Key(number=key_number, config=key_config, deck=self)
                for name in key_config.keys():
                    if name in {"line", "column"}:
                        continue
                    if callback := self.plugin_manager.key_handlers.get(name):
                        plugin = callback(self, key)
                        key.handlers.append(plugin)
                        task = asyncio.get_event_loop().create_task(plugin.loop(), name=f"Key-{key_number}-{name}-handler")
                        key.add_task(task)
                    else:
                        log.warn(f"Unknown display handler {name!r} for key {key_config['line']}-{key_config['column']}")
                        if log.isEnabledFor(logging.DEBUG):
                            log.debug("Valid display handlers: %r", list(self.plugin_manager.key_handlers.keys()))

                if old_key := self.keys.get(key_number, None):
                    for task in old_key.tasks:
                        task.cancel("Config reload")
                self.keys[key_number] = key
            else:
                if "PATH" in key_config:
                    os.environ["PATH"] = key_config["PATH"] + ":" + os.environ["PATH"]

        log.debug("Reconfigured %s", self.serial_number)

    async def on_keypress(self, hardware, key_number: int, state: bool):
        if key_number not in self.keys:
            return
        pressed_or_released = "pressed" if state else "released"
        func_name = "on_keyup" if state else "on_keydown"
        log.debug(f"Deck {self.serial_number} key {key_number} is now {pressed_or_released}.")
        try:
            key = self.keys[key_number]
            await getattr(key, func_name)()
        except Exception as e:
            log.exception(f"Deck {self.serial_number} key {key_number} caused exception {e}:")
