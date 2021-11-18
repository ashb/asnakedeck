from __future__ import annotations

from asnakedeck.types import KeyHandler


class Label(KeyHandler):
    async def loop(self) -> None:
        self.key.update(label=self.config['label'])
