import sys
from typing import TYPE_CHECKING, Any

WINDOWS = sys.platform == "win32"

if TYPE_CHECKING:
    from pathlib import Path

    CONFIG_DIR: Path
    EMOJI_FONT: str

__all__ = ["WINDOWS", "CONFIG_DIR", "EMOJI_FONT"]

if WINDOWS:
    from . import win32 as impl
else:
    from . import linux as impl

def __getattr__(name) -> Any:
    match name:
        case "CONFIG_DIR":
            if WINDOWS:
                from .win32 import get_win_folder
                val = get_win_folder("CSIDL_LOCAL_APPDATA") / "snakedeck"
            else:
                from .linux import XDG_CONFIG_HOME
                val = XDG_CONFIG_HOME / "snakedeck"
            globals()[name] = val
            return val
        case _:
            return getattr(impl, name)
