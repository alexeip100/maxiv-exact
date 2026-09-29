# -*- coding: utf-8 -*- / ---

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QCheckBox, QComboBox, QSpinBox,
    QLabel, QHBoxLayout, QSizePolicy, QColorDialog
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor


from ..qt_helpers import is_checked_state

class CurveListItemWidget(QWidget):
    """Small row widget for controlling visibility, color, style, and library actions of one plotted curve."""

    colorChanged = pyqtSignal(str, object)
    visibilityChanged = pyqtSignal(str, bool)
    styleChanged = pyqtSignal(str, str, float)
    removeRequested = pyqtSignal(str)
    addToLibraryRequested = pyqtSignal(str)

    def __init__(self, label_text, color, key, parent=None):
        super().__init__(parent)
        self.key = str(key)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        # Remove button (small "x")
        self.remove_button = QPushButton("✕")
        self.remove_button.setFixedSize(20, 20)
        self.remove_button.setToolTip("Remove this curve from the plot")
        self.remove_button.clicked.connect(self.on_remove_clicked)
        layout.addWidget(self.remove_button)

        # Add to library button (bookmark symbol)
        self.add_button = QPushButton("🔖")
        self.add_button.setFixedSize(20, 20)
        self.add_button.setToolTip("Add this curve to the reference library")
        self.add_button.clicked.connect(self.on_add_clicked)
        layout.addWidget(self.add_button)

        # Visibility checkbox
        self.visible_check = QCheckBox()
        self.visible_check.setChecked(True)
        self.visible_check.setToolTip("Show / hide this curve")
        self.visible_check.stateChanged.connect(self.on_visibility_changed)
        layout.addWidget(self.visible_check)

        # Color button
        self.color_button = QPushButton()
        self.color_button.setFixedSize(20, 20)
        self.color_button.setToolTip("Change curve color")
        self._set_button_color(color)
        self.color_button.clicked.connect(self.on_color_clicked)
        layout.addWidget(self.color_button)

        # Style combo
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Solid", "Dashed", "Scatter"])
        self.style_combo.setCurrentText("Solid")
        self.style_combo.currentIndexChanged.connect(self.on_style_changed)
        layout.addWidget(self.style_combo)

        # Size spinbox (line width or marker size)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 10)
        # Matplotlib's default line width is often 1.5, but our UI exposes only integers.
        # Use an integer default so users can always return to the initial look easily.
        self.size_spin.setValue(2)
        self.size_spin.setToolTip("Line width / marker size")
        self.size_spin.valueChanged.connect(self.on_style_changed)
        layout.addWidget(self.size_spin)

        # Text label showing the curve origin / name
        self.label = QLabel(str(label_text))
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.label)

        self.setLayout(layout)

# ---
    # Helpers
    # ------------------------------------------------------------------
    def _set_button_color(self, color):
        """Set the background color of the color button from various formats."""
        qcolor = None
        if isinstance(color, QColor):
            qcolor = color
        elif isinstance(color, str):
            try:
                qcolor = QColor(color)
            except Exception:
                qcolor = None
        elif isinstance(color, (tuple, list)) and len(color) in (3, 4):
            try:
                r, g, b = [int(255 * float(c)) if float(c) <= 1 else int(c) for c in color[:3]]
                qcolor = QColor(r, g, b)
            except Exception:
                qcolor = None
        if qcolor is None:
            qcolor = QColor("black")
        self._current_color = qcolor
        self.color_button.setStyleSheet("background-color: %s;" % qcolor.name())

    def set_add_to_library_enabled(self, enabled: bool):
        """Enable or disable the 'Add to library' button (for reference curves we disable it)."""
        try:
            self.add_button.setEnabled(bool(enabled))
        except Exception:
            pass

# ---
    # Slots
    # ------------------------------------------------------------------
    def on_color_clicked(self):
        """Open a color dialog and emit colorChanged if accepted."""
        initial = getattr(self, "_current_color", QColor("black"))
        color = QColorDialog.getColor(initial, self, "Select curve color")
        if color.isValid():
            self._current_color = color
            self.color_button.setStyleSheet("background-color: %s;" % color.name())
            self.colorChanged.emit(self.key, color.name())

    def on_remove_clicked(self):
        """Request removal of this curve via signal."""
        self.removeRequested.emit(self.key)

    def on_add_clicked(self):
        """Request adding this curve to the reference library via signal."""
        self.addToLibraryRequested.emit(self.key)

    def on_visibility_changed(self, state):
        """Emit signal when visibility toggled."""
        self.visibilityChanged.emit(self.key, is_checked_state(state))

    def on_style_changed(self):
        """Emit signal when style or size changed."""
        self.styleChanged.emit(
            self.key,
            self.style_combo.currentText(),
            float(self.size_spin.value())
        )
