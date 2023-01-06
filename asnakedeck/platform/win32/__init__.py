from __future__ import annotations
import asyncio
import logging

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Coroutine

import attr
from windows_fonts import FontCollection, Weight, Style
from windows_audio_control import AudioDevice, DeviceCollection, DeviceCollectionEventType, VolumeChangeEvent, DeviceCollectionEvent, Role


EMOJI_FONT = "Segoe UI Emoji"
DEFAULT_FONT = "Calibri"

log = logging.getLogger(__name__)

def _get_win_folder_with_ctypes(csidl_name: str) -> str:
    import ctypes

    csidl_const = {
        "CSIDL_APPDATA": 0x1A,
        "CSIDL_COMMON_APPDATA": 0x23,
        "CSIDL_FONTS": 0x14,
        "CSIDL_LOCAL_APPDATA": 0x1C,
        "CSIDL_PROGRAM_FILES": 0x26,
        "CSIDL_WINDOWS": 0x24,
    }[csidl_name]

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl_const, None, 0, buf)

    # Downgrade to short path name if have highbit chars. See
    # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
    has_high_char = False
    for c in buf:
        if ord(c) > 255:
            has_high_char = True
            break
    if has_high_char:
        buf2 = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(buf.value, buf2, 1024):
            buf = buf2

    return buf.value


def get_win_folder(csidl_name: str) -> Path:
    if sys.platform == "win32":
        return Path(_get_win_folder_with_ctypes(csidl_name))

    raise RuntimeError("Method can only be called on Windows.")


def resolve_font(name: str) -> str:
    collection = FontCollection()
    face = collection["Segoe UI Emoji"]
    font = face.get_best_variant(weight=Weight.REGULAR, style=Style.NORMAL)
    return font.filename


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
