from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


POPULAR_COLORMAPS = [
    'viridis', 'plasma', 'inferno', 'magma', 'cividis',
    'turbo', 'cubehelix', 'gray', 'Greys',
    'hot', 'cool',
    # Diverging palettes suited to signed difference maps (including reversals).
    'RdBu_r', 'RdBu', 'coolwarm', 'coolwarm_r',
    'seismic', 'seismic_r', 'bwr', 'bwr_r',
    'PiYG', 'PiYG_r', 'BrBG', 'BrBG_r', 'Spectral', 'Spectral_r',
    'terrain', 'gist_earth',
    'YlOrRd', 'YlGnBu', 'PuBuGn',
]


def available_colormaps(names: Iterable[str] | None = None) -> list[str]:
    """Return the curated colormap list filtered to installed Matplotlib maps."""
    requested = list(names or POPULAR_COLORMAPS)
    try:
        import matplotlib  # type: ignore
        registered = matplotlib.colormaps
        return [name for name in requested if name in registered]
    except Exception:
        return requested


def _colormap_icon(name: str, width: int = 180, height: int = 18) -> QIcon:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        import matplotlib  # type: ignore
        cmap = matplotlib.colormaps[name]
        for x in range(width):
            value = 0.0 if width <= 1 else x / float(width - 1)
            r, g, b, a = cmap(value)
            painter.setPen(QColor.fromRgbF(float(r), float(g), float(b), float(a)))
            painter.drawLine(x, 0, x, height - 1)
    except Exception:
        painter.fillRect(0, 0, width, height, QColor(220, 220, 220))
    finally:
        painter.end()
    return QIcon(pixmap)


class ColormapDialog(QDialog):
    """Compact palette chooser with a gradient preview beside every name."""

    def __init__(self, current: str = 'terrain', parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle('Color palette')
        self.setModal(True)
        self.resize(350, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        label = QLabel('Choose color palette:', self)
        layout.addWidget(label)

        self.list_widget = QListWidget(self)
        self.list_widget.setIconSize(QSize(180, 18))
        self.list_widget.setSpacing(2)
        layout.addWidget(self.list_widget, 1)

        options = available_colormaps()
        current_item = None
        for name in options:
            item = QListWidgetItem(_colormap_icon(name), name)
            item.setSizeHint(QSize(300, 27))
            self.list_widget.addItem(item)
            if name == current:
                current_item = item

        if current_item is None and self.list_widget.count():
            current_item = self.list_widget.item(0)
        if current_item is not None:
            self.list_widget.setCurrentItem(current_item)
            self.list_widget.scrollToItem(current_item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())

    def selected_colormap(self) -> str | None:
        item = self.list_widget.currentItem()
        return str(item.text()) if item is not None else None


def choose_colormap(parent: QWidget | None, current: str = 'terrain') -> str | None:
    """Open the preview palette dialog and return the chosen Matplotlib cmap name."""
    dialog = ColormapDialog(current=current, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.selected_colormap()


def open_colormap(parent: QWidget, current: str, on_selected) -> None:
    """Show a modal palette chooser without entering a nested Qt event loop.

    Retain the dialog until its finished signal, including on Cancel/close.
    """
    dialogs = getattr(parent, "_open_colormap_dialogs", None)
    if dialogs is None:
        dialogs = []
        parent._open_colormap_dialogs = dialogs
    # Ignore repeated requests while a chooser is already displayed.
    if dialogs:
        dialogs[-1].raise_()
        dialogs[-1].activateWindow()
        return
    dialog = ColormapDialog(current=current, parent=parent)
    dialogs.append(dialog)

    def _finished(result: int) -> None:
        # Finish dismissing the native macOS dialog before refreshing Matplotlib.
        selected = (dialog.selected_colormap()
                    if result == int(QDialog.DialogCode.Accepted) else None)
        if dialog in dialogs:
            dialogs.remove(dialog)
        dialog.deleteLater()
        if selected is not None:
            QTimer.singleShot(0, lambda name=selected: on_selected(name))

    dialog.finished.connect(_finished)
    dialog.open()
