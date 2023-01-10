from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Protocol, Type

WINDOWS = sys.platform == "win32"

if TYPE_CHECKING:
    from pathlib import Path

    CONFIG_DIR: Path
    EMOJI_FONT: str
    DEFAULT_FONT: str

    class AudioVolumeWatcherInterface(Protocol):
        def __init__(self, handler: Callable[[float], Coroutine[Any, Any, None]]): ...
        async def toggle_mute(self): ...
        async def run(self): ...

    AudioVolumeWatcher: Type[AudioVolumeWatcherInterface]

__all__ = ["WINDOWS", "CONFIG_DIR", "EMOJI_FONT"]

if WINDOWS:
    from . import win32 as impl
else:
    from . import linux as impl  # type: ignore[no-redef]


def __getattr__(name) -> Any:
    # # No `match` support, https://github.com/charliermarsh/ruff/issues/282
    match name:  # noqa: E999
        case "CONFIG_DIR":
            if WINDOWS:
                from .win32 import get_win_folder

                val = get_win_folder("CSIDL_LOCAL_APPDATA") / "snakedeck"
            else:
                from .linux import XDG_CONFIG_HOME

                val = XDG_CONFIG_HOME / "snakedeck"
            globals()[name] = val
            return val
        case "AudioVolumeWatcher":
            if WINDOWS:
                from .win32.audio import WindowsVolumeWatcher

                return WindowsVolumeWatcher
            else:
                from .linux.audio import PulseVolumeWatcher

                return PulseVolumeWatcher
        case _:
            return getattr(impl, name)

