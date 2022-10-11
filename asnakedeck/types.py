import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

import attr
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError

if TYPE_CHECKING:
    from .deck import Deck


@attr.define(slots=False)
class KeyHandler:
    deck: "Deck" = attr.ib(repr=False)
    key: "Key"
    config: dict[str, Any] = attr.ib()

    @config.default
    def _config_default(self):
        return self.key.config

    def loop(self) -> Awaitable[None]:
        """An awaitable that will continually update the key"""
        ...

    async def on_keydown(self):
        pass

    async def on_keyup(self):
        pass


@attr.define
class Key:
    number: int
    config: dict
    deck: "Deck" = attr.ib(repr=False)
    handlers: list[KeyHandler] = attr.ib(repr=False, factory=list)
    tasks: set[asyncio.Task] = attr.ib(repr=False, factory=set)

    def update(self, **key):
        text = None
        kwargs = {}
        font: ImageFont.FreeTypeFont = None

        if "label" in key:
            text = key["label"]
            font = self.deck.label_font
        if "emoji" in key:
            text = key["emoji"]
            font = self.deck.emoji_font
            kwargs = dict(embedded_color=True, fill="white")
        if text:
            text_size = font.getsize(text)
            image = Image.new("RGB", text_size)
            draw = ImageDraw.Draw(image)
            draw.text((0, 0), text, font=font, **kwargs)
            scaled_image = PILHelper.create_scaled_image(self.deck.hardware, image, margins=[4, 4, 4, 4])
            deck_image = PILHelper.to_native_format(self.deck.hardware, scaled_image)
            # TODO: cache images, store state, re-send on exception
            try:
                self.deck.hardware.set_key_image(self.number, deck_image)
            except TransportError:
                pass

    def add_task(self, task: asyncio.Task):
        task.add_done_callback(self.tasks.remove)
        self.tasks.add(task)

    def on_keydown(self):
        return asyncio.gather(*[handler.on_keydown() for handler in self.handlers])

    def on_keyup(self):
        return asyncio.gather(*[handler.on_keyup() for handler in self.handlers])
