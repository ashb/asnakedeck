from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import  Callable, Coroutine

import attr
import pulsectl
import pulsectl_asyncio
from pulsectl import PulseDisconnected, PulseError, PulseEventFacilityEnum, PulseEventTypeEnum


# Set a couple of directory paths for later use.
# This follows the spec at the following address:
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.environ["HOME"], ".config"))

XDG_STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or os.path.join(os.environ["HOME"], ".local", "state"))

EMOJI_FONT = "NotoColorEmoji"
DEFAULT_FONT = "DroidSans"

def resolve_font(name: str) -> str:
    return name

async def watch_file_for_changes(path: Path, cb: Callable[[os.PathLike], Coroutine]):
    """
    Watch a file for changes, and call the async callback when detected.

    This will also watch the parent directory to catch the case where editors move a new file in to place over
    the top. (Which is how many editors save changes so that the update is "atomic")
    """
    from asyncinotify import Inotify, InotifyError, Mask

    def _add_file_watch():
        try:
            inotify.add_watch(path, Mask.MODIFY)
        except InotifyError:
            pass

    try:
        inotify = Inotify()

        _add_file_watch()
        # Watch the dir for files for file being moved in place (which is what editors usually do)
        inotify.add_watch(path.parent, Mask.MOVE | Mask.CREATE)

        async for event in inotify:
            if event.mask & (Mask.CREATE | Mask.MOVED_TO):
                assert event.name
                assert event.watch
                # File created/renamed in config directory
                full_path = event.watch.path / event.name
                if full_path == path:
                    await cb(path)
                    _add_file_watch()

            elif event.mask & Mask.MODIFY:
                # File was modified
                await cb(path)
    except asyncio.CancelledError:
        pass


# Can't be imported cos of how the c bindings are written.
PulseCallError = pulsectl.pulsectl.c.pa.CallError


@attr.define(repr=False, kw_only=True)
class PulseVolumeWatcher:
    default_sink_idx: int | None = None
    handler: Callable[[float], Coroutine]
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
        await self.handler(simple_volume)

    async def toggle_mute(self) -> None:
        if self.default_sink_idx is None:
            return
        await self.pulse.sink_mute(self.default_sink_idx, mute=not self.sink_info.mute)
