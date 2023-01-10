from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Callable

import attr
from windows_fonts import FontCollection, Style, Weight

EMOJI_FONT = "Segoe UI Emoji"
DEFAULT_FONT = "Calibri"

log = logging.getLogger(__name__)


def _get_win_folder_with_ctypes(csidl_name: str) -> str:
    import ctypes

    if sys.platform != "win32":
        raise RuntimeError("Only works on win32 platform")

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
