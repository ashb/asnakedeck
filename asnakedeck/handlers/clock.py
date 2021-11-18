from __future__ import annotations

import asyncio
import time

from asnakedeck.types import KeyHandler


class Clock(KeyHandler):
    async def loop(self) -> None:
        format = self.config["clock"]
        while True:
            self.key.update(label=time.strftime(format))
            await asyncio.sleep(1)
