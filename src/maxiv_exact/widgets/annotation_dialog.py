from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QComboBox, QColorDialog, QDialogButtonBox, QWidget
)
from PyQt6.QtGui import QColor


def _qcolor_to_hex(c: QColor) -> str:
    """Return #RRGGBB (no alpha)."""
    if not isinstance(c, QColor):
        return "#000000"
    c2 = QColor(c)
    c2.setAlpha(255)
    return c2.name()  # #RRGGBB


def _hex_to_qcolor(s: str, fallback: str = "#000000") -> QColor:
    try:
        c = QColor(str(s))
        if not c.isValid():
            c = QColor(fallback)
    except Exception:
        c = QColor(fallback)
    c.setAlpha(255)
    return c


@dataclass
class AnnotationStyle:
    fontsize: int = 12
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_color: str = "#000000"
    bg_enabled: bool = True
    bg_color: str = "#FFFFFF"
    border_enabled: bool = True
    border_color: str = "#000000"
    border_width: float = 0.8
    pad: float = 0.30  # matplotlib boxstyle pad (fraction of fontsize)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "AnnotationStyle":
        d = d or {}
        s = cls()
        try:
            s.fontsize = int(d.get("fontsize", s.fontsize))
        except Exception:
            pass
        for k in ("bold", "italic", "underline", "bg_enabled", "border_enabled"):
            try:
                setattr(s, k, bool(d.get(k, getattr(s, k))))
            except Exception:
                pass
        try:
            s.font_color = str(d.get("font_color", s.font_color)) or s.font_color
        except Exception:
            pass
        try:
            s.bg_color = str(d.get("bg_color", s.bg_color)) or s.bg_color
        except Exception:
            pass
        try:
            s.border_color = str(d.get("border_color", s.border_color)) or s.border_color
        except Exception:
            pass
        try:
            s.border_width = float(d.get("border_width", s.border_width))
        except Exception:
            pass
        try:
            s.pad = float(d.get("pad", s.pad))
        except Exception:
            pass
        return s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fontsize": int(self.fontsize),
            "bold": bool(self.bold),
            "italic": bool(self.italic),
            "underline": bool(self.underline),
            "font_color": str(self.font_color),
            "bg_enabled": bool(self.bg_enabled),
            "bg_color": str(self.bg_color),
            "border_enabled": bool(self.border_enabled),
            "border_color": str(self.border_color),
            "border_width": float(self.border_width),
            "pad": float(self.pad),
        }


class AnnotationEditDialog(QDialog):
    """
    Edit a Matplotlib text annotation with basic styling:
      - font size
      - bold/italic/underline
      - font color
      - background color or no background
      - box padding (margin)
      - insert common symbols
    """

    SYMBOLS: List[Tuple[str, str]] = [
        ("°", "degree"),
        ("±", "plus/minus"),
        ("µ", "micro"),
        ("Å", "angstrom"),
        ("α", "alpha"),
        ("β", "beta"),
        ("γ", "gamma"),
        ("Δ", "delta"),
        ("×", "multiply"),
        ("·", "dot"),
        ("→", "arrow right"),
        ("←", "arrow left"),
        ("↔", "arrow both"),
        ("≤", "less or equal"),
        ("≥", "greater or equal"),
        ("≈", "approximately"),
        ("≠", "not equal"),
        ("Ω", "omega"),
        ("π", "pi"),
        ("₀", "subscript 0"),
        ("₁", "subscript 1"),
        ("₂", "subscript 2"),
        ("₃", "subscript 3"),
        ("⁻¹", "superscript -1"),
        ("⁻²", "superscript -2"),
    ]

    def __init__(self, text: str, style: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit annotation")

        self._style = AnnotationStyle.from_dict(style)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Annotation text:"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text or "")
        layout.addWidget(self.text_edit)

        # Font controls
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Font size:"))
        self.fontsize = QSpinBox()
        self.fontsize.setRange(6, 96)
        self.fontsize.setValue(int(self._style.fontsize))
        row1.addWidget(self.fontsize)

        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.setChecked(bool(self._style.bold))
        row1.addWidget(self.chk_bold)

        self.chk_italic = QCheckBox("Italic")
        self.chk_italic.setChecked(bool(self._style.italic))
        row1.addWidget(self.chk_italic)

        self.chk_underline = QCheckBox("Underline")
        self.chk_underline.setChecked(bool(self._style.underline))
        row1.addWidget(self.chk_underline)

        row1.addStretch(1)
        layout.addLayout(row1)

        # Colors + background
        row2 = QHBoxLayout()

        row2.addWidget(QLabel("Font color:"))
        self.btn_font_color = QPushButton("Select…")
        self._font_qcolor = _hex_to_qcolor(self._style.font_color, "#000000")
        self._apply_button_color(self.btn_font_color, self._font_qcolor)
        self.btn_font_color.clicked.connect(self._choose_font_color)
        row2.addWidget(self.btn_font_color)

        self.chk_bg = QCheckBox("Background")
        self.chk_bg.setChecked(bool(self._style.bg_enabled))
        row2.addWidget(self.chk_bg)

        self.btn_bg_color = QPushButton("Select…")
        self._bg_qcolor = _hex_to_qcolor(self._style.bg_color, "#FFFFFF")
        self._apply_button_color(self.btn_bg_color, self._bg_qcolor)
        self.btn_bg_color.clicked.connect(self._choose_bg_color)
        row2.addWidget(self.btn_bg_color)

        row2.addWidget(QLabel("Margin:"))
        self.pad = QDoubleSpinBox()
        self.pad.setRange(0.0, 2.0)
        self.pad.setSingleStep(0.05)
        self.pad.setDecimals(2)
        self.pad.setValue(float(self._style.pad))
        self.pad.setToolTip("Padding inside the annotation frame (Matplotlib boxstyle pad).")
        row2.addWidget(self.pad)

        row2.addStretch(1)
        layout.addLayout(row2)

        # Border (frame)
        row2b = QHBoxLayout()

        self.chk_border = QCheckBox("Border")
        self.chk_border.setChecked(bool(self._style.border_enabled))
        row2b.addWidget(self.chk_border)

        row2b.addWidget(QLabel("Border color:"))
        self.btn_border_color = QPushButton("Select…")
        self._border_qcolor = _hex_to_qcolor(self._style.border_color, "#000000")
        self._apply_button_color(self.btn_border_color, self._border_qcolor)
        self.btn_border_color.clicked.connect(self._choose_border_color)
        row2b.addWidget(self.btn_border_color)

        row2b.addWidget(QLabel("Thickness:"))
        self.border_width = QDoubleSpinBox()
        self.border_width.setRange(0.1, 10.0)
        self.border_width.setSingleStep(0.1)
        self.border_width.setDecimals(1)
        self.border_width.setValue(float(self._style.border_width))
        row2b.addWidget(self.border_width)

        row2b.addStretch(1)
        layout.addLayout(row2b)

        # Symbols
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Insert symbol:"))
        self.symbol_combo = QComboBox()
        for sym, name in self.SYMBOLS:
            self.symbol_combo.addItem(f"{sym}   ({name})", sym)
        row3.addWidget(self.symbol_combo)
        btn_insert = QPushButton("Insert")
        btn_insert.clicked.connect(self._insert_symbol)
        row3.addWidget(btn_insert)
        row3.addStretch(1)
        layout.addLayout(row3)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_bg_enabled()

        self.chk_bg.toggled.connect(self._update_bg_enabled)
        self.chk_border.toggled.connect(self._update_bg_enabled)

    def _apply_button_color(self, btn: QPushButton, color: QColor) -> None:
        try:
            btn.setStyleSheet(f"background-color: {color.name()};")
        except Exception:
            pass

    def _choose_font_color(self) -> None:
        c = QColorDialog.getColor(self._font_qcolor, self, "Select font color")
        if c.isValid():
            c.setAlpha(255)
            self._font_qcolor = c
            self._apply_button_color(self.btn_font_color, c)

    def _choose_bg_color(self) -> None:
        c = QColorDialog.getColor(self._bg_qcolor, self, "Select background color")
        if c.isValid():
            c.setAlpha(255)
            self._bg_qcolor = c
            self._apply_button_color(self.btn_bg_color, c)

    def _choose_border_color(self) -> None:
        c = QColorDialog.getColor(self._border_qcolor, self, "Select border color")
        if c.isValid():
            c.setAlpha(255)
            self._border_qcolor = c
            self._apply_button_color(self.btn_border_color, c)

    def _update_bg_enabled(self) -> None:
        enabled = self.chk_bg.isChecked()
        self.btn_bg_color.setEnabled(enabled)
        self.pad.setEnabled(enabled)
        # Border controls are only meaningful when background is enabled
        try:
            self.chk_border.setEnabled(enabled)
            border_on = enabled and self.chk_border.isChecked()
            self.btn_border_color.setEnabled(border_on)
            self.border_width.setEnabled(border_on)
        except Exception:
            pass

    def _insert_symbol(self) -> None:
        sym = self.symbol_combo.currentData()
        if not sym:
            return
        cursor = self.text_edit.textCursor()
        if not cursor:
            return
        cursor.insertText(str(sym))
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    def get_text_and_style(self) -> Tuple[str, Dict[str, Any]]:
        txt = self.text_edit.toPlainText()
        st = AnnotationStyle(
            fontsize=int(self.fontsize.value()),
            bold=bool(self.chk_bold.isChecked()),
            italic=bool(self.chk_italic.isChecked()),
            underline=bool(self.chk_underline.isChecked()),
            font_color=_qcolor_to_hex(self._font_qcolor),
            bg_enabled=bool(self.chk_bg.isChecked()),
            bg_color=_qcolor_to_hex(self._bg_qcolor),
            border_enabled=bool(self.chk_border.isChecked()),
            border_color=_qcolor_to_hex(self._border_qcolor),
            border_width=float(self.border_width.value()),
            pad=float(self.pad.value()),
        )
        return txt, st.to_dict()
