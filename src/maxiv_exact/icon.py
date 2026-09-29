from __future__ import annotations

"""Application icon resource helpers."""

from importlib import resources
from pathlib import Path

from PyQt6.QtGui import QIcon  # type: ignore


_ICON_PACKAGE = "maxiv_exact.assets"
_ICO_NAME = "exact_icon.ico"
_ICNS_NAME = "exact_icon.icns"
_PNG_NAMES_BY_SIZE = {
    64: "exact_icon_64.png",
    128: "exact_icon_128.png",
    256: "exact_icon_256.png",
    512: "exact_icon_512.png",
}


def _resource_path(name: str) -> Path:
    return resources.files(_ICON_PACKAGE).joinpath(name)


def application_icon() -> QIcon:
    """Return the bundled EXACT application icon.

    The icon is loaded from package data so installed applications do not depend
    on the source tree or the user's original icon-file location.
    """
    try:
        icon = QIcon(str(_resource_path(_ICO_NAME)))
        if not icon.isNull():
            return icon
    except Exception:
        pass
    return QIcon()


def windows_icon_path() -> Path:
    """Return the packaged multi-resolution Windows icon (.ico) path."""
    return _resource_path(_ICO_NAME)


def macos_icon_path() -> Path:
    """Return the packaged macOS icon-bundle file (.icns) path."""
    return _resource_path(_ICNS_NAME)


def linux_icon_png_path(preferred_size: int = 256) -> Path:
    """Return the packaged Linux-friendly PNG icon path.

    Parameters
    ----------
    preferred_size:
        Preferred square icon size in pixels. The nearest available packaged
        size is returned.
    """
    size = min(_PNG_NAMES_BY_SIZE, key=lambda s: abs(s - int(preferred_size)))
    return _resource_path(_PNG_NAMES_BY_SIZE[size])



def apply_windows_native_window_icon(window) -> bool:
    """Apply the packaged .ico directly to a native Windows HWND.

    Qt normally propagates ``QWidget.setWindowIcon`` to Windows, but when a Qt
    GUI is hosted by ``python.exe`` Windows 11 can still fall back to the host
    executable's generic icon for the taskbar button.  Sending ``WM_SETICON``
    explicitly supplies the native large and small icons that Explorer asks the
    window for.

    Returns ``True`` when the native calls were made successfully.  On
    non-Windows platforms this is a no-op and returns ``False``.
    """
    import sys

    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window.winId())
        if not hwnd:
            return False

        user32 = ctypes.windll.user32
        icon_path = str(windows_icon_path())

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTCOLOR = 0x0000
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        SM_CXICON = 11
        SM_CYICON = 12
        SM_CXSMICON = 49
        SM_CYSMICON = 50

        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]

        big_w = int(user32.GetSystemMetrics(SM_CXICON)) or 32
        big_h = int(user32.GetSystemMetrics(SM_CYICON)) or 32
        small_w = int(user32.GetSystemMetrics(SM_CXSMICON)) or 16
        small_h = int(user32.GetSystemMetrics(SM_CYSMICON)) or 16

        big_icon = user32.LoadImageW(
            None, icon_path, IMAGE_ICON, big_w, big_h,
            LR_LOADFROMFILE | LR_DEFAULTCOLOR,
        )
        small_icon = user32.LoadImageW(
            None, icon_path, IMAGE_ICON, small_w, small_h,
            LR_LOADFROMFILE | LR_DEFAULTCOLOR,
        )
        if not big_icon or not small_icon:
            return False

        user32.SendMessageW.restype = wintypes.LPARAM
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.SendMessageW(
            wintypes.HWND(hwnd), WM_SETICON, ICON_BIG,
            wintypes.LPARAM(int(big_icon)),
        )
        user32.SendMessageW(
            wintypes.HWND(hwnd), WM_SETICON, ICON_SMALL,
            wintypes.LPARAM(int(small_icon)),
        )

        # Keep the HICON handles alive for the lifetime of the window.  Windows
        # does not make independent copies when WM_SETICON is sent.
        window._exact_native_hicons = (big_icon, small_icon)
        return True
    except Exception:
        # Native icon setup must never prevent the application from starting.
        return False
