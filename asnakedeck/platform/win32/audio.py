import asyncio
import logging
from collections.abc import Coroutine
from typing import Callable

import attr
from windows_audio_control import AudioDevice, DeviceCollection, DeviceCollectionEventType, Role

log = logging.getLogger(__name__)


@attr.define(repr=False, kw_only=True, slots=False)
class WindowsVolumeWatcher:
    handler: Callable[[float], Coroutine]
    volume_task: asyncio.Task | None = None

    async def run(self):
        self.collection = DeviceCollection()
        self.playback_device = self.collection.get_default_output_device()

        await self.handler(0 if self.playback_device.muted else self.playback_device.volume)

        volume_task = None

        async with asyncio.TaskGroup() as tg:

            async def watch_for_default_change():
                nonlocal tg, volume_task
                log.info("Waiting for collection events")
                events = self.collection.events
                async for event in events:
                    if event.kind != DeviceCollectionEventType.DEFAULT_CHANGED:
                        continue
                    if event.role != Role.MULTIMEDIA:
                        continue
                    if event.device_id != self.playback_device.device_id:
                        if volume_task:
                            volume_task.cancel()
                        self.playback_device = self.collection.devices[event.device_id]
                        volume_task = tg.create_task(volume_change(self.playback_device))

            async def volume_change(device: AudioDevice):
                log.info("Watching %s for volume events", device.name)
                events = device.events
                async for event in events:
                    vol = 0 if event.mute else event.volume
                    await self.handler(vol)

            volume_task = tg.create_task(volume_change(self.playback_device))
            tg.create_task(watch_for_default_change())

    async def toggle_mute(self):
        self.playback_device.toggle_mute()
