from pathlib import Path
import sys
from typing import cast


# Code for the _get_win_folder taken from Poetry
def _get_win_folder_from_registry(csidl_name: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Method can only be called on Windows.")

    import winreg as _winreg

    shell_folder_name = {
        "CSIDL_APPDATA": "AppData",
        "CSIDL_COMMON_APPDATA": "Common AppData",
        "CSIDL_LOCAL_APPDATA": "Local AppData",
        "CSIDL_PROGRAM_FILES": "Program Files",
    }[csidl_name]

    key = _winreg.OpenKey(
        _winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    )
    dir, type = _winreg.QueryValueEx(key, shell_folder_name)

    return cast(str, dir)


def _get_win_folder_with_ctypes(csidl_name: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Method can only be called on Windows.")

    import ctypes

    csidl_const = {
        "CSIDL_APPDATA": 26,
        "CSIDL_COMMON_APPDATA": 35,
        "CSIDL_LOCAL_APPDATA": 28,
        "CSIDL_PROGRAM_FILES": 38,
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
        try:
            from ctypes import windll  # noqa: F401

            _get_win_folder = _get_win_folder_with_ctypes
        except ImportError:
            _get_win_folder = _get_win_folder_from_registry

        return Path(_get_win_folder(csidl_name))

    raise RuntimeError("Method can only be called on Windows.")
