from __future__ import annotations

from asnakedeck.types import KeyHandler


class Emoji(KeyHandler):
    async def loop(self) -> None:
        self.key.update(emoji=self.config['emoji'])
