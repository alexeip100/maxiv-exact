"""Application entry point.

Important: the rest of this package currently uses **PyQt5** (including the
Matplotlib Qt backend import in ``ui.py``). If both PyQt6 and PyQt5 are
installed, importing PyQt6 here would create a *PyQt6* QApplication, while the
UI constructs *PyQt5* widgets. That mismatch triggers the classic runtime
crash:

    QWidget: Must construct a QApplication before a QWidget

So we deliberately prefer PyQt5 here.
"""

from __future__ import annotations

import os
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")  # must be set before any h5py import

try:
    from PyQt5 import QtWidgets  # type: ignore
    from PyQt5 import QtCore  # type: ignore
    from PyQt5 import QtGui  # type: ignore
except Exception as exc:  # pragma: no cover
# The UI code in this package imports PyQt5 directly, so PyQt5 is required.
    raise ImportError(
        "PyQt5 is required to run flexpes_nexafs (UI modules import PyQt5)."
    ) from exc


def _set_windows_app_user_model_id() -> None:
    """Give Windows a stable identity for taskbar grouping and icon selection."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MAXIV.FlexPES.NEXAFS"
        )
    except Exception:
        # Icon setup should never prevent the application from starting.
        pass


def main():
    import sys

    # Windows must receive the application identity before QApplication/window
    # creation; otherwise the taskbar can inherit python.exe's generic icon.
    _set_windows_app_user_model_id()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    from .icon import application_icon, apply_windows_native_window_icon
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

# Import the main UI only after a QApplication exists.
    from .ui import MainWindow

# Force a consistent cross-platform Qt style. / (Fusion exists in both Qt5 and Qt6.)
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

# Use the style's standard palette as the default (light) palette.
    try:
        app.setPalette(app.style().standardPalette())
    except Exception:
        pass

# Match the GUI font sizing used in flexpes_pes.
# Preserve the system-selected font family and increase the default Qt
# application font by two points, with a pixel-size fallback.
    try:
        f = app.font()
        ps = int(f.pointSize())
        if ps > 0:
            f.setPointSize(ps + 2)
        else:
            px = int(f.pixelSize())
            if px > 0:
                f.setPixelSize(px + 2)
        app.setFont(f)
    except Exception:
        pass

    win = MainWindow()
    win.show()

    # On Windows, set the native HWND icons explicitly.  This avoids Explorer
    # falling back to python.exe's generic icon for the active taskbar button.
    apply_windows_native_window_icon(win)
    try:
        QtCore.QTimer.singleShot(0, lambda: apply_windows_native_window_icon(win))
    except Exception:
        pass

# Preload the decomposition UI and its heavy dependencies shortly after startup / so the first click on the "PCA" button feels responsive. This runs...
    def _preload_decomposition() -> None:
        try:
# Heavy imports (NumPy wheels already present, but sklearn/pandas can take time)
            import pandas  # noqa: F401
            import sklearn  # noqa: F401

# Import the decomposition UI module to warm up its import graph
            from .decomposition import legacy  # noqa: F401
        except Exception:
# Never fail startup due to preload
            pass

    try:
        QtCore.QTimer.singleShot(200, _preload_decomposition)
    except Exception:
        pass

# Qt5 uses exec_(), Qt6 uses exec()
    try:
        sys.exit(app.exec())
    except Exception:
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
