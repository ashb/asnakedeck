import sys
from typing import TYPE_CHECKING

WINDOWS = sys.platform == "win32"

if TYPE_CHECKING:
    from pathlib import Path

    CONFIG_DIR: Path

__all__ = ['WINDOWS', 'CONFIG_DIR']

def __getattr__(name):
    match name:
        case 'CONFIG_DIR':
            if WINDOWS:
                from .win32 import get_win_folder
                val = get_win_folder('CSIDL_LOCAL_APPDATA') / "snakedeck"
            else:
                from .linux import XDG_CONFIG_HOME
                val = XDG_CONFIG_HOME / "snakedeck"
            globals()[name] = val
            return val
