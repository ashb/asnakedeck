from __future__ import annotations

import asyncio

from asnakedeck.types import KeyHandler


class Cycle(KeyHandler):
    current: int = 0

    restarter: asyncio.Future
    NEXT_CYCLE = object()

    async def loop(self) -> None:
        while True:
            self.restarter = asyncio.get_event_loop().create_future()
            current_config = self.key.config['cycle'][self.current]
            tasks = []
            for name in current_config.keys():
                callback = self.deck.plugin_manager.key_handlers[name]
                plugin = callback(deck=self.deck, key=self.key, config=current_config)
                tasks.append(asyncio.create_task(plugin.loop()))
            for coro in asyncio.as_completed([self.restarter] + tasks):  # type: ignore
                await coro
                if coro is self.restarter:
                    # Cancel any tasks from the previous key handler
                    for task in tasks:
                        task.cancel()
                    break

    async def on_keydown(self):
        self.current = (self.current + 1) % len(self.config['cycle'])
        self.restarter.set_result(self.NEXT_CYCLE)
