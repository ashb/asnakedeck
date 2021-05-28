import asyncio
import logging
import os
import subprocess  # nosec
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import attr
import yaml
from asyncinotify import Inotify, InotifyError, Mask
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError

from .config import CONFIG_DIR, PluginManager

if TYPE_CHECKING:
    from StreamDeck.Devices.StreamDeck import StreamDeck


log = logging.getLogger(__name__)


@attr.s(auto_attribs=True)
class Deck:
    deck: "StreamDeck"
    plugin_manager: PluginManager
    keys: dict[int, dict] = attr.Factory(dict)
    key_tasks: dict[int, asyncio.Task] = attr.Factory(dict)
    image_size: tuple[int, int] = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.deck.open()
        self.deck.read_thread.setName(f"DeckThread-{self.serial_number}")
        self.deck.set_key_callback_async(self.on_keypress)
        self.image_size = self.deck.key_image_format()["size"]

        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "Deck %s is a %s, serial number %s.",
                self.deck.id(),
                self.deck.DECK_TYPE,
                self.serial_number,
            )

        self.load_config()
        self.task = asyncio.get_event_loop().create_task(self.watch_config_for_changes())
        self.task.add_done_callback(self.on_task_complete)

    def on_task_complete(self, task):
        self.close()

    def __del__(self):
        if self.deck.connected():
            self.close()

        for task in self.key_tasks.values():
            task.cancel("Deck going away")

    @cached_property
    def config_file_path(self) -> Path:
        return Path(CONFIG_DIR) / (self.serial_number + ".yaml")

    @cached_property
    def serial_number(self) -> str:
        return self.deck.get_serial_number()  # type: ignore

    @cached_property
    def label_font(self) -> "ImageFont.FreeTypeFont":
        font = self.config.get("label_font", {"face": "DroidSans", "size": 20})
        log.debug("label_font %r", font)
        return ImageFont.truetype(font["face"], font["size"])

    @cached_property
    def emoji_font(self) -> "ImageFont.FreeTypeFont":
        font = self.config.get("emoji_font", {"face": "NotoColorEmoji", "size": 109})
        log.debug("emoji_font %r", font)
        return ImageFont.truetype(font["face"], font["size"])

    def clear(self):
        # Clear all keys
        self.deck.reset()
        for key in range(self.deck.KEY_COUNT):
            self.deck.set_key_image(key, self.deck.BLANK_KEY_IMAGE)
        self.deck.set_brightness(80)
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
        if self.deck.read_thread:
            self.deck.run_read_thread = False
            self.deck.read_thread.join()
            self.deck.read_thread = None
        if self.deck.connected():
            if reset:
                try:
                    self.deck.reset()
                except TransportError:
                    pass
            self.deck.close()

    def load_config(self):
        if not os.path.isfile(self.config_file_path):
            log.warning(f"Deck {self.serial_number} has no configuration file ({self.config_file_path}).")
            return
        config = yaml.safe_load(open(self.config_file_path))

        # Support snakedeck format where config is just a list
        if isinstance(config, list):
            config = {"keys": self.config}

        if not config:
            log.warning(f"Deck {self.serial_number} has no configuration in {self.config_file_path!r}.")
            return

        self.config = config

        for task in self.key_tasks.values():
            task.cancel("Config reloaded")

        key_tasks = {}

        for key in self.config["keys"]:
            if "line" in key and "column" in key:
                # FIXME validate line/column
                key_number = (key["line"] - 1) * self.deck.KEY_COLS + key["column"] - 1
                for name in key.keys():
                    if name in {"line", "column", "emoji", "label"}:
                        continue
                    if callback := self.plugin_manager.key_displayers.get(name):
                        task = asyncio.get_event_loop().create_task(callback(self, key, key_number))
                        key_tasks[key_number] = task

                self.update_key(key_number, key)
            else:
                if "PATH" in key:
                    os.environ["PATH"] = key["PATH"] + ":" + os.environ["PATH"]

        self.key_tasks = key_tasks

        log.debug("Recondigured %s", self.serial_number)

    def update_key(self, key_number: int, key: dict):
        self.keys[key_number] = key
        if "cycle" in key:
            key.update(key["cycle"][0])
        text = None
        kwargs = {}
        font: ImageFont.FreeTypeFont = None

        if "label" in key:
            text = key["label"]
            font = self.label_font
        if "emoji" in key:
            text = key["emoji"]
            font = self.emoji_font
            kwargs = dict(embedded_color=True, fill="white")
        if text:
            text_size = font.getsize(text)
            image = Image.new("RGB", text_size)
            draw = ImageDraw.Draw(image)
            draw.text((0, 0), text, font=font, **kwargs)
            scaled_image = PILHelper.create_scaled_image(self.deck, image, margins=[4, 4, 4, 4])
            deck_image = PILHelper.to_native_format(self.deck, scaled_image)
            # TODO: cache images, store state, re-send on exception
            try:
                self.deck.set_key_image(key_number, deck_image)
            except TransportError:
                pass

    async def on_keypress(self, deck, key_number, state):
        pressed_or_released = "pressed" if state else "released"
        log.debug(f"Deck {self.serial_number} key {key_number} is now {pressed_or_released}.")
        try:
            key = self.keys[key_number]
            if state and "shell" in key:
                command = key["shell"]
                kwargs = {"shell": True}
                if "cd" in key:
                    kwargs["cwd"] = key["cd"]
                ret = subprocess.call(command, **kwargs)  # nosec
                if ret != 0:
                    log.warning(f"Command {command!r} exited with non-zero status code.")
            if state and "eval" in key:
                retval = eval(key["eval"])  # nosec
                if retval is not None:
                    key.update(retval)
                    self.update_key(key_number, key)
            if state and "cycle" in key:
                key["cycle"].append(key["cycle"].pop(0))
                key["actor"] = self.serial_number
                key["serial"] = key.get("serial", 0) + 1
                self.update_key(key_number, key)
        except Exception as e:
            log.exception(f"Deck {self.serial_number} key {key_number} caused exception {e}:")
