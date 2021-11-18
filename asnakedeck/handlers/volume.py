from __future__ import annotations

import asyncio
import logging

import attr
import pulsectl
import pulsectl_asyncio
from pulsectl import PulseDisconnected, PulseError, PulseEventFacilityEnum, PulseEventTypeEnum

from asnakedeck.types import KeyHandler

# Can't be imported cos of how the c bindings are written.
PulseCallError = pulsectl.pulsectl.c.pa.CallError


@attr.define
class Volume(KeyHandler):
    impl: PulseVolumeWatcher = attr.ib()

    @impl.default
    def _impl_default(self):
        return PulseVolumeWatcher(handler=self)

    async def loop(self):
        await self.impl.run()

    async def on_volume_change(self, volume: float):
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
            self.key.update(label=f'{volume:.0%}')
            await asyncio.sleep(0.33)
        self.key.update(emoji=emoji)

    async def on_keyup(self):
        await self.impl.toggle_mute()


@attr.define(repr=False, kw_only=True)
class PulseVolumeWatcher:
    default_sink_idx: int | None = None
    handler: Volume
    pulse: pulsectl_asyncio.PulseAsync = attr.ib(init=False)
    sink_info: pulsectl.PulseSinkInfo = attr.ib(init=False, default=None)

    def __attrs_post_init__(self):
        self.pulse = pulsectl_asyncio.PulseAsync("snakedeck")

    async def connect(self):
        while not self.pulse.connected:
            try:
                await self.pulse.connect()
                logging.info("Reconnected to pulseaudio %s", self.pulse.connected)
            except (PulseCallError, PulseError):
                await asyncio.sleep(1)

    async def run(self) -> None:
        async with self.pulse:
            await self.load_default_sink()

            while True:
                try:
                    await self.connect()

                    await self.listen()
                except (PulseDisconnected, PulseCallError):
                    pass

    async def listen(self):
        async for event in self.pulse.subscribe_events("all"):
            if event.t != PulseEventTypeEnum.change:
                continue
            if event.facility == PulseEventFacilityEnum.sink and event.index == self.default_sink_idx:
                info = await self.pulse.sink_info(index=event.index)
                await self.handle_sink_volume(info)
            elif event.facility == PulseEventFacilityEnum.server:
                await self.load_default_sink()

    async def load_default_sink(self) -> None:
        server = await self.pulse.server_info()
        try:
            sink = await self.pulse.get_sink_by_name(server.default_sink_name)
            self.default_sink_idx = sink.index
            await self.handle_sink_volume(sink)
        except pulsectl.PulseIndexError:
            self.default_sink_idx = None

    async def handle_sink_volume(self, info: pulsectl.PulseSinkInfo) -> None:
        if self.sink_info and info.mute == self.sink_info.mute and info.volume.value_flat == self.sink_info.volume.value_flat:
            return
        self.sink_info = info
        simple_volume = 0 if info.mute else info.volume.value_flat
        await self.handler.on_volume_change(simple_volume)

    async def toggle_mute(self) -> None:
        if self.default_sink_idx is None:
            return
        await self.pulse.sink_mute(self.default_sink_idx, mute=not self.sink_info.mute)
