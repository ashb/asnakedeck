from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import  Callable, Coroutine



# Set a couple of directory paths for later use.
# This follows the spec at the following address:
# https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.environ["HOME"], ".config"))

XDG_STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or os.path.join(os.environ["HOME"], ".local", "state"))


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
