"""Small helpers for stable PyQt6 signal handling."""

from __future__ import annotations

from PyQt6.QtCore import Qt


def is_checked_state(state) -> bool:
    """Return True for a checked QCheckBox state from PyQt6 signals or APIs.

    ``QCheckBox.stateChanged`` emits an integer, while APIs such as
    ``QTreeWidgetItem.checkState`` return ``Qt.CheckState``.  PyQt6 no longer
    guarantees direct equality between those representations.
    """
    try:
        if state == Qt.CheckState.Checked:
            return True
    except Exception:
        pass
    try:
        return int(state) == int(Qt.CheckState.Checked.value)
    except Exception:
        return False
