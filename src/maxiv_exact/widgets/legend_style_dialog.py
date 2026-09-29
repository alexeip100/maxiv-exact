from __future__ import annotations

from typing import Dict

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class LegendStyleDialog(QDialog):
    """Dialog to edit Plotted Data legend style.

    Controls are intentionally minimal compared to the annotation dialog:
      1) Transparency
      2) Margin (legend border padding)
      3) Font size
      4) Font style (bold/italic/underline)

    The dialog returns a style dict.
    """

    def __init__(self, style: Dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit legend style")
        self.setModal(True)

        self._style_in = dict(style or {})

        layout = QVBoxLayout(self)

        info = QLabel("Adjust the legend appearance.\nRight click on the legend to open this dialog.")
        info.setWordWrap(True)
        layout.addWidget(info)

# --- Box group ---
        box_group = QGroupBox("Legend box")
        box_form = QFormLayout(box_group)

        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.0, 1.0)
        self.alpha_spin.setSingleStep(0.05)
        self.alpha_spin.setDecimals(2)
        self.alpha_spin.setValue(float(self._style_in.get("alpha", 1.0)))
        box_form.addRow("Transparency", self.alpha_spin)

        self.pad_spin = QDoubleSpinBox()
        self.pad_spin.setRange(0.0, 2.0)
        self.pad_spin.setSingleStep(0.05)
        self.pad_spin.setDecimals(2)
        self.pad_spin.setValue(float(self._style_in.get("borderpad", 0.4)))
        box_form.addRow("Margins", self.pad_spin)

        layout.addWidget(box_group)

# --- Font group ---
        font_group = QGroupBox("Legend font")
        font_form = QFormLayout(font_group)

        self.fontsize_spin = QSpinBox()
        self.fontsize_spin.setRange(6, 48)
        self.fontsize_spin.setValue(int(self._style_in.get("fontsize", 10)))
        font_form.addRow("Font size", self.fontsize_spin)

        self.bold_cb = QCheckBox("Bold")
        self.bold_cb.setChecked(bool(self._style_in.get("bold", False)))
        self.italic_cb = QCheckBox("Italic")
        self.italic_cb.setChecked(bool(self._style_in.get("italic", False)))
        self.underline_cb = QCheckBox("Underline")
        self.underline_cb.setChecked(bool(self._style_in.get("underline", False)))

        font_form.addRow("Style", self._row_widget([self.bold_cb, self.italic_cb, self.underline_cb]))
        layout.addWidget(font_group)

# Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _row_widget(widgets):
        from PyQt6.QtWidgets import QWidget, QHBoxLayout

        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for it in widgets:
            h.addWidget(it)
        h.addStretch(1)
        return w

    def get_style(self) -> Dict:
        """Return a style dict."""
        st = {
            "alpha": float(self.alpha_spin.value()),
            "borderpad": float(self.pad_spin.value()),
            "fontsize": int(self.fontsize_spin.value()),
            "bold": bool(self.bold_cb.isChecked()),
            "italic": bool(self.italic_cb.isChecked()),
            "underline": bool(self.underline_cb.isChecked()),
        }
        return st
