"""Application entry point for the PyQt6 application."""

from __future__ import annotations

import os
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")  # must be set before any h5py import

try:
    from PyQt6 import QtWidgets  # type: ignore
    from PyQt6 import QtCore  # type: ignore
except Exception as exc:  # pragma: no cover
    # The UI code in this package imports PyQt6 directly, so PyQt6 is required.
    raise ImportError(
        "PyQt6 is required to run maxiv_exact (UI modules import PyQt6)."
    ) from exc


def _set_windows_app_user_model_id() -> None:
    """Give Windows a stable identity for taskbar grouping and icon selection."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MAXIV.EXACT"
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
    app.setOrganizationName("MAX IV")
    app.setApplicationName("EXACT")
    app.setApplicationDisplayName("EXACT")

    from .icon import application_icon, apply_windows_native_window_icon
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Apply persistent appearance preferences before constructing widgets.
    # The baseline is captured first so "System" can restore the OS palette.
    from .appearance import capture_application_baseline, apply_appearance
    capture_application_baseline(app)
    apply_appearance(app)

    # Import the main UI only after a QApplication exists and styling is ready.
    from .ui import MainWindow

    win = MainWindow()
    win.show()

    # On Windows, set the native HWND icons explicitly.  This avoids Explorer
    # falling back to python.exe's generic icon for the active taskbar button.
    apply_windows_native_window_icon(win)
    try:
        QtCore.QTimer.singleShot(0, lambda: apply_windows_native_window_icon(win))
    except Exception:
        pass

    # Preload the decomposition UI and its heavy dependencies shortly after startup
    # so the first click on the PCA button feels responsive.
    def _preload_decomposition() -> None:
        try:
            # Heavy imports (NumPy is already imported elsewhere, but sklearn/pandas can take time).
            import pandas  # noqa: F401
            import sklearn  # noqa: F401

            # Import the decomposition UI module to warm up its import graph.
            from .decomposition import legacy  # noqa: F401
        except Exception:
            # Never fail startup due to preload.
            pass

    try:
        QtCore.QTimer.singleShot(200, _preload_decomposition)
    except Exception:
        pass

    return app.exec()


if __name__ == "__main__":
    import sys
    sys.exit(main())
