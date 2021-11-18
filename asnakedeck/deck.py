from __future__ import annotations

import asyncio
import logging
import os
from asyncio.tasks import Task
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import attr
import yaml
from asyncinotify import Inotify, InotifyError, Mask
from PIL import ImageFont
from StreamDeck.Transport.Transport import TransportError

from asnakedeck.types import Key

from .config import CONFIG_DIR

if TYPE_CHECKING:
    from StreamDeck.Devices.StreamDeck import StreamDeck

    from .plugin_manager import PluginManager


log = logging.getLogger(__name__)


@attr.define(slots=False)
class Deck:
    hardware: StreamDeck
    plugin_manager: PluginManager
    keys: dict[int, Key] = attr.Factory(dict)
    key_tasks: dict[int, asyncio.Task] = attr.Factory(dict)
    image_size: tuple[int, int] = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.hardware.open()
        self.hardware.read_thread.setName(f"DeckThread-{self.serial_number}")
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
        self.task = asyncio.create_task(self.watch_config_for_changes())
        self.task.add_done_callback(self.on_task_complete)

    @property
    def tasks(self) -> list[Task]:
        return [
            self.task,
            *[task for key in self.keys.values() for task in key.tasks],
        ]

    def on_task_complete(self, task):
        log.info("Closing down")
        self.close()

    def __del__(self):
        if self.hardware.connected():
            self.close()

        for key in self.keys.values():
            for task in key.tasks:
                task.cancel("Deck going away")

    @cached_property
    def config_file_path(self) -> Path:
        return Path(CONFIG_DIR) / (self.serial_number + ".yaml")

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

    async def watch_config_for_changes(self):
        def _add_file_watch():
            try:
                inotify.add_watch(self.config_file_path, Mask.MODIFY)
            except InotifyError:
                pass

        try:
            inotify = Inotify()

            _add_file_watch()
            inotify.add_watch(CONFIG_DIR, Mask.MOVE | Mask.CREATE)

            async for event in inotify:
                if event.mask & (Mask.CREATE | Mask.MOVED_TO):
                    # File created/renamed in config directory
                    full_path = event.watch.path / event.name
                    if self.config_file_path == full_path:
                        self.load_config()
                        _add_file_watch()

                elif event.mask & Mask.MODIFY:
                    # File was modified
                    self.load_config()
        except asyncio.CancelledError:
            pass

    def close(self, reset=True):
        for task in self.key_tasks.values():
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

    def _get_font(self, face: str, size: int):
        return ImageFont.truetype(face, size)

    @cached_property
    def label_font(self) -> ImageFont.FreeTypeFont:
        font = self.config.get("label_font", {"face": "DroidSans", "size": 20})
        return self._get_font(font["face"], font["size"])

    @cached_property
    def emoji_font(self) -> ImageFont.FreeTypeFont:
        font = self.config.get("emoji_font", {"face": "NotoColorEmoji", "size": 109})
        return self._get_font(font["face"], font["size"])

    def load_config(self):
        if not os.path.isfile(self.config_file_path):
            log.warning(f"Deck {self.serial_number} has no configuration file ({self.config_file_path}).")
            return
        config = yaml.safe_load(open(self.config_file_path))

        # Support snakedeck format where config is just a list
        if isinstance(config, list):
            config = {"keys": config}

        if not config:
            log.warning(f"Deck {self.serial_number} has no configuration in {self.config_file_path!r}.")
            return

        self.config = config

        for task in self.key_tasks.values():
            task.cancel("Config reloaded")

        key_tasks = {}

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
                        task = asyncio.get_event_loop().create_task(plugin.loop())
                        key.tasks.append(task)
                    else:
                        logging.warn(f"Unknown display handler {name!r} for key {key_config['line']}-{key_config['column']}")

                if old_key := self.keys.get(key_number, None):
                    for task in old_key.tasks:
                        task.cancel("Config reload")
                self.keys[key_number] = key
            else:
                if "PATH" in key_config:
                    os.environ["PATH"] = key_config["PATH"] + ":" + os.environ["PATH"]

        self.key_tasks = key_tasks

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
