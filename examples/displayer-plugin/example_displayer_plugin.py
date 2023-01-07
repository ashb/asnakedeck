from __future__ import annotations

import asyncio
import time

from asnakedeck.types import KeyHandler


class Foo(KeyHandler):
    async def loop(self) -> None:
        format = self.config["clock"]
        while True:
            self.key.update(label="Foo\n" + time.strftime(format))
            await asyncio.sleep(1)
