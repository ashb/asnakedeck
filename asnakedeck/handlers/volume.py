from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

import attr

from ..types import KeyHandler
from .. import platform

log = logging.getLogger(__name__)

@attr.define
class Volume(KeyHandler):
    impl: Any = attr.ib(init=False)

    task: asyncio.Task | None = None

    @impl.default
    def _impl_default(self):
        if platform.WINDOWS:
            return platform.WindowsVolumeWatcher(handler=self.on_volume_change)
        else:
            return platform.PulseVolumeWatcher(handler=self.on_volume_change)

    async def loop(self):
        await self.impl.run()

    async def change_task(self, volume: float):
        if volume == 0:
            emoji = "🔇"
        elif volume <= 0.35:
            emoji = "🔈"
        elif volume <= 0.65:
            emoji = "🔉"
        else:
            emoji = "🔊"
        if volume:
            # Show the volume percentag for a split-second
            logging.debug(f'Showing level {volume}')
            self.key.update(label=f'{volume:.0%}')
            await asyncio.sleep(0.33)
            logging.debug(f'Showing level {volume} - Done')
        self.key.update(emoji=emoji)
        self.task = None

    async def on_volume_change(self, volume: float):
        if self.task:
            self.task.cancel()
        self.task = asyncio.create_task(self.change_task(volume))

    async def on_keyup(self):
        await self.impl.toggle_mute()


