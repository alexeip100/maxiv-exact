from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.ticker import LogFormatter

from ..reference import EnergyOutOfRangeError, ReferenceDatabase, reference_database
from ..composition import (
    Composition,
    CompositionError,
    compound_mass_attenuation,
    compound_mass_attenuation_value,
    parse_formula,
)


class _CompactLogFormatter(LogFormatter):
    """Log formatter with one shared decade factor for compact labels."""

    def _shared_exponent(self) -> int:
        if self.axis is None:
            return 0
        lo, hi = self.axis.get_view_interval()
        positive = [abs(v) for v in (lo, hi) if np.isfinite(v) and v > 0]
        if not positive:
            return 0
        if len(positive) == 1:
            return int(round(np.log10(positive[0])))
        log_mid = 0.5 * (np.log10(min(positive)) + np.log10(max(positive)))
        return int(round(log_mid))

    @staticmethod
    def _compact_number(value: float) -> str:
        av = abs(value)
        if av >= 100 or (av and av < 0.01):
            return f"{value:.2g}"
        return f"{value:.3g}"

    def __call__(self, x, pos=None):
        # Let LogFormatter decide which major/minor ticks are worth labelling.
        if not super().__call__(x, pos):
            return ""
        exponent = self._shared_exponent()
        return self.fix_minus(self._compact_number(x / (10.0 ** exponent)))

    def get_offset(self):
        exponent = self._shared_exponent()
        if exponent == 0:
            return ""
        return rf"$\times 10^{{{exponent}}}$"


_NONMETALS = {"H", "C", "N", "O", "P", "S", "Se"}
_HALOGENS = {"F", "Cl", "Br", "I", "At"}
_NOBLE_GASES = {"He", "Ne", "Ar", "Kr", "Xe", "Rn"}
_ALKALI = {"Li", "Na", "K", "Rb", "Cs", "Fr"}
_ALKALINE_EARTH = {"Be", "Mg", "Ca", "Sr", "Ba", "Ra"}
_METALLOIDS = {"B", "Si", "Ge", "As", "Sb", "Te", "Po"}
_LANTHANIDES = {"La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"}
_ACTINIDES = {"Ac", "Th", "Pa", "U"}
_POST_TRANSITION = {"Al", "Ga", "In", "Sn", "Tl", "Pb", "Bi"}

_PERIODIC_POSITIONS = {
    "H": (0, 0), "He": (0, 17),
    "Li": (1, 0), "Be": (1, 1), "B": (1, 12), "C": (1, 13), "N": (1, 14), "O": (1, 15), "F": (1, 16), "Ne": (1, 17),
    "Na": (2, 0), "Mg": (2, 1), "Al": (2, 12), "Si": (2, 13), "P": (2, 14), "S": (2, 15), "Cl": (2, 16), "Ar": (2, 17),
    "K": (3, 0), "Ca": (3, 1), "Sc": (3, 2), "Ti": (3, 3), "V": (3, 4), "Cr": (3, 5), "Mn": (3, 6), "Fe": (3, 7), "Co": (3, 8), "Ni": (3, 9), "Cu": (3, 10), "Zn": (3, 11), "Ga": (3, 12), "Ge": (3, 13), "As": (3, 14), "Se": (3, 15), "Br": (3, 16), "Kr": (3, 17),
    "Rb": (4, 0), "Sr": (4, 1), "Y": (4, 2), "Zr": (4, 3), "Nb": (4, 4), "Mo": (4, 5), "Tc": (4, 6), "Ru": (4, 7), "Rh": (4, 8), "Pd": (4, 9), "Ag": (4, 10), "Cd": (4, 11), "In": (4, 12), "Sn": (4, 13), "Sb": (4, 14), "Te": (4, 15), "I": (4, 16), "Xe": (4, 17),
    "Cs": (5, 0), "Ba": (5, 1), "Hf": (5, 3), "Ta": (5, 4), "W": (5, 5), "Re": (5, 6), "Os": (5, 7), "Ir": (5, 8), "Pt": (5, 9), "Au": (5, 10), "Hg": (5, 11), "Tl": (5, 12), "Pb": (5, 13), "Bi": (5, 14), "Po": (5, 15), "At": (5, 16), "Rn": (5, 17),
    "Fr": (6, 0), "Ra": (6, 1),
    "La": (7, 3), "Ce": (7, 4), "Pr": (7, 5), "Nd": (7, 6), "Pm": (7, 7), "Sm": (7, 8), "Eu": (7, 9), "Gd": (7, 10), "Tb": (7, 11), "Dy": (7, 12), "Ho": (7, 13), "Er": (7, 14), "Tm": (7, 15), "Yb": (7, 16), "Lu": (7, 17),
    "Ac": (8, 3), "Th": (8, 4), "Pa": (8, 5), "U": (8, 6),
}


@dataclass(frozen=True)
class QuantityDefinition:
    key: str
    label: str
    axis_label: str
    tooltip: str


_QUANTITIES = {
    "f1": QuantityDefinition(
        "f1", "f₁", "f₁ (electrons)",
        "Full real atomic scattering factor. Henke/CXRO tabulates f₁ directly; "
        "Chantler/XrayDB stores the anomalous correction f′, so EXACT displays Z + f′ for direct comparison with Henke.",
    ),
    "f2": QuantityDefinition(
        "f2", "f₂", "f₂ (electrons)",
        "Imaginary part of the anomalous atomic scattering factor. It is directly related to X-ray absorption and rises strongly at absorption edges.",
    ),
    "mu_photo_cm2_g": QuantityDefinition(
        "mu_photo_cm2_g", "μ photo", "Mass attenuation (cm²/g)",
        "Photoelectric mass attenuation coefficient: attenuation caused by photoabsorption, expressed per unit mass density.",
    ),
    "mu_incoh_cm2_g": QuantityDefinition(
        "mu_incoh_cm2_g", "μ incoh", "Mass attenuation (cm²/g)",
        "Incoherent (Compton) scattering contribution to the mass attenuation coefficient, expressed in cm²/g.",
    ),
    "mu_total_cm2_g": QuantityDefinition(
        "mu_total_cm2_g", "μ total", "Mass attenuation (cm²/g)",
        "Total mass attenuation coefficient tabulated in the Chantler/XrayDB dataset, combining the included attenuation contributions.",
    ),
    "mu_compare": QuantityDefinition(
        "mu_compare", "μ compare", "Mass attenuation (cm²/g)",
        "Overlay μ photo, μ incoh and μ total for the same Chantler element or a single compound.",
    ),
}

_SOURCE_TOOLTIPS = {
    "henke": (
        "Henke / CXRO atomic scattering-factor tables. Henke tabulates the full real factor f₁ and the imaginary factor f₂; "
        "the original source points are preserved in the bundled reference database."
    ),
    "chantler": (
        "Chantler tabulations distributed through XrayDB. XrayDB stores the anomalous real correction f′; "
        "when f₁ is selected, EXACT displays Z + f′ so it is directly comparable with Henke. f₂ and the attenuation quantities are used as tabulated."
    ),
    "compare": (
        "Overlay Henke/CXRO and Chantler/XrayDB for the same element. For f₁, EXACT compares Henke's tabulated full f₁ with Z + f′ derived from Chantler/XrayDB; "
        "for f₂, both tabulations are shown directly."
    ),
}


def _element_category(symbol: str) -> str:
    if symbol in _NONMETALS:
        return "nonmetal"
    if symbol in _HALOGENS:
        return "halogen"
    if symbol in _NOBLE_GASES:
        return "noble"
    if symbol in _ALKALI:
        return "alkali"
    if symbol in _ALKALINE_EARTH:
        return "alkaline"
    if symbol in _METALLOIDS:
        return "metalloid"
    if symbol in _LANTHANIDES:
        return "lanthanide"
    if symbol in _ACTINIDES:
        return "actinide"
    if symbol in _POST_TRANSITION:
        return "posttransition"
    return "transition"


class ElementTileButton(QPushButton):
    """Compact PANDA-style checkable element tile."""

    def __init__(self, symbol: str, atomic_number: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.symbol = symbol
        self.atomic_number = int(atomic_number)
        self.setCheckable(True)
        self.setText("")
        self.setAccessibleName(f"{symbol}, atomic number {atomic_number}")
        self.setProperty("elementCategory", _element_category(symbol))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(42, 42)
        self.setMaximumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{symbol} (atomic number {atomic_number})")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(self.palette().buttonText().color())

        number_font = self.font()
        number_font.setPointSizeF(max(6.5, self.font().pointSizeF() * 0.70))
        number_font.setBold(False)
        painter.setFont(number_font)
        painter.drawText(
            QRectF(5.0, 3.0, self.width() - 9.0, 14.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            str(self.atomic_number),
        )

        symbol_font = self.font()
        symbol_font.setPointSizeF(max(11.0, self.font().pointSizeF() * 1.15))
        symbol_font.setBold(True)
        painter.setFont(symbol_font)
        painter.drawText(
            QRectF(2.0, 9.0, self.width() - 4.0, self.height() - 11.0),
            Qt.AlignmentFlag.AlignCenter,
            self.symbol,
        )


class ReferenceNavigationToolbar(NavigationToolbar):
    """Matplotlib toolbar whose Home action follows EXACT's Reference view policy."""

    def __init__(self, canvas, parent, reset_callback):
        self._reference_reset_callback = reset_callback
        super().__init__(canvas, parent)

    def home(self, *args) -> None:
        # Do not restore Matplotlib's initial navigation-stack entry here:
        # the Reference panel owns the default view and it depends on the
        # current "Full source range" setting.
        self._reference_reset_callback()


class ReferencePanel(QWidget):
    """Interactive browser for EXACT's frozen X-ray reference database."""

    SOFT_XRAY_MAX_EV = 2500.0

    def __init__(self, parent: QWidget | None = None, *, database: ReferenceDatabase | None = None):
        super().__init__(parent)
        self.database = database or reference_database()
        self._element_buttons: dict[str, ElementTileButton] = {}
        self._selected_element = "Fe"
        self._compounds: list[Composition] = []
        self._curve_artists: list[tuple[str, str, object]] = []
        self._intersection_markers: list[tuple[str, str, object]] = []
        self._photon_marker = None
        self._legend = None
        self._dragging_photon_marker = False
        self._photon_initialized = False
        self._default_view_limits = None
        self._build_ui()
        self._select_element(self._selected_element)

    def _build_ui(self) -> None:
        self.setObjectName("exactReferencePanel")
        self.setStyleSheet(
            """
            QWidget#exactReferencePanel { background: palette(window); }
            QLabel#referenceIntro { color: palette(window-text); padding: 2px 4px 5px 4px; }
            QLabel[paneHeading="true"] { font-weight: 600; color: palette(window-text); padding: 2px 2px 5px 2px; }
            QFrame[paneCard="true"] { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 6px; }
            QPushButton[elementCategory] {
                border: 1px solid palette(mid); border-top-width: 4px; border-radius: 5px;
                background: palette(base); color: palette(button-text); font-weight: 600;
                padding: 2px; text-align: center;
            }
            QPushButton[elementCategory]:hover { background: palette(midlight); border-color: palette(mid); }
            QPushButton[elementCategory]:checked { background: palette(highlight); border-color: palette(highlight); color: palette(highlighted-text); }
            QPushButton[elementCategory="nonmetal"] { border-top-color: #62a879; }
            QPushButton[elementCategory="halogen"] { border-top-color: #55a7a5; }
            QPushButton[elementCategory="noble"] { border-top-color: #8d83c6; }
            QPushButton[elementCategory="alkali"] { border-top-color: #d3945c; }
            QPushButton[elementCategory="alkaline"] { border-top-color: #d5b85e; }
            QPushButton[elementCategory="metalloid"] { border-top-color: #70a0a0; }
            QPushButton[elementCategory="lanthanide"] { border-top-color: #bf7ba0; }
            QPushButton[elementCategory="actinide"] { border-top-color: #a36f92; }
            QPushButton[elementCategory="posttransition"] { border-top-color: #8199ad; }
            QPushButton[elementCategory="transition"] { border-top-color: #7093b5; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(7)

        intro = QLabel(
            "Atomic scattering and attenuation reference data. "
            "Henke/CXRO and Chantler/XrayDB remain separate source datasets."
        )
        intro.setObjectName("referenceIntro")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)
        self.splitter = splitter

        left = QFrame(splitter)
        left.setProperty("paneCard", True)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(9, 7, 9, 8)
        left_layout.setSpacing(6)

        heading = QLabel("Elements", left)
        heading.setProperty("paneHeading", True)
        left_layout.addWidget(heading)

        scroll = QScrollArea(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget(scroll)
        grid = QGridLayout(host)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(4)

        for symbol in self.database.list_elements():
            info = self.database.element_info(symbol)
            button = ElementTileButton(symbol, info.atomic_number, host)
            button.toggled.connect(lambda checked, s=symbol: self._element_toggled(s, checked))
            self._element_buttons[symbol] = button
            row_col = _PERIODIC_POSITIONS.get(symbol)
            if row_col is not None:
                grid.addWidget(button, *row_col)

        for col in range(18):
            grid.setColumnStretch(col, 1)
        scroll.setWidget(host)
        left_layout.addWidget(scroll, 1)

        compound_heading = QLabel("Compound(s)", left)
        compound_heading.setProperty("paneHeading", True)
        left_layout.addWidget(compound_heading)
        self.compound_edit = QLineEdit(left)
        self.compound_edit.setPlaceholderText("e.g. Co2O3 or CoO, Co2O3, Co3O4")
        self.compound_edit.setClearButtonEnabled(True)
        self.compound_edit.setToolTip(
            "Enter one chemical formula, or several formulas separated by commas, and press Enter. "
            "EXACT plots Chantler/XrayDB compound mass attenuation coefficients for comparison. "
            "Supported now: element symbols, positive stoichiometric numbers and nested parentheses. "
            "Up to 8 compounds can be shown together."
        )
        self.compound_edit.returnPressed.connect(self._apply_compound_formula)
        left_layout.addWidget(self.compound_edit)
        self.compound_status = QLabel(
            "Compound mode: enter one formula or comma-separated formulas; Chantler mass attenuation only.", left
        )
        self.compound_status.setWordWrap(True)
        self.compound_status.setToolTip(
            "Density is not required for the mass attenuation coefficient μ/ρ. "
            "The formula is converted to elemental mass fractions."
        )
        left_layout.addWidget(self.compound_status)
        left.setMinimumWidth(430)

        right = QFrame(splitter)
        right.setProperty("paneCard", True)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 7, 8, 7)
        right_layout.setSpacing(6)

        top_controls = QHBoxLayout()
        top_controls.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox(right)
        self._add_combo_item(self.source_combo, "Henke / CXRO", "henke", _SOURCE_TOOLTIPS["henke"])
        self._add_combo_item(self.source_combo, "Chantler / XrayDB", "chantler", _SOURCE_TOOLTIPS["chantler"])
        self._add_combo_item(self.source_combo, "Henke + Chantler", "compare", _SOURCE_TOOLTIPS["compare"])
        self.source_combo.setCurrentIndex(1)
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        top_controls.addWidget(self.source_combo)

        top_controls.addWidget(QLabel("Quantity:"))
        self.quantity_combo = QComboBox(right)
        self.quantity_combo.currentIndexChanged.connect(self._quantity_changed)
        top_controls.addWidget(self.quantity_combo)
        top_controls.addStretch(1)
        right_layout.addLayout(top_controls)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.toolbar = ReferenceNavigationToolbar(self.canvas, right, self._reset_reference_view)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(QLabel("Photon energy:"))
        self.photon_energy_spin = QDoubleSpinBox(right)
        self.photon_energy_spin.setDecimals(2)
        self.photon_energy_spin.setSingleStep(1.0)
        self.photon_energy_spin.setSuffix(" eV")
        self.photon_energy_spin.setMinimumWidth(140)
        self.photon_energy_spin.setToolTip(
            "Photon energy selected by the dashed vertical line. Drag the line or edit this value; "
            "the intersection values update immediately."
        )
        self.photon_energy_spin.valueChanged.connect(self._on_photon_energy_changed)
        bottom.addWidget(self.photon_energy_spin)

        self.full_range_check = QCheckBox("Full source range", right)
        self.full_range_check.setChecked(False)
        self.full_range_check.setToolTip(
            "Unchecked: display the soft-X-ray region up to 2500 eV. Checked: display the full tabulated source range."
        )
        self.full_range_check.toggled.connect(self._range_changed)
        bottom.addWidget(self.full_range_check)

        self.legend_check = QCheckBox("Legend", right)
        self.legend_check.setChecked(True)
        self.legend_check.setToolTip("Show or hide the draggable legend.")
        self.legend_check.toggled.connect(self._set_legend_visible)
        bottom.addWidget(self.legend_check)
        bottom.addStretch(1)
        right_layout.addLayout(bottom)

        self.values_table = QTableWidget(0, 2, right)
        self.values_table.setHorizontalHeaderLabels(["Curve", "Value at photon energy"])
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.values_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.values_table.setAlternatingRowColors(True)
        self.values_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.values_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.values_table.setMaximumHeight(118)
        self.values_table.setToolTip(
            "Interpolated database value at the selected photon energy for each visible curve."
        )
        right_layout.addWidget(self.values_table, 0)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 1000])

        self.canvas.mpl_connect("button_press_event", self._on_plot_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_plot_motion)
        self.canvas.mpl_connect("button_release_event", self._on_plot_release)

    @staticmethod
    def _add_combo_item(combo: QComboBox, text: str, data: str, tooltip: str) -> None:
        combo.addItem(text, data)
        idx = combo.count() - 1
        combo.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)

    def _update_combo_tooltips(self) -> None:
        source = self.source_combo.currentData()
        self.source_combo.setToolTip(_SOURCE_TOOLTIPS.get(source, "Select reference source"))
        quantity = self.quantity_combo.currentData()
        definition = _QUANTITIES.get(quantity)
        self.quantity_combo.setToolTip(definition.tooltip if definition else "Select reference quantity")

    def _element_toggled(self, symbol: str, checked: bool) -> None:
        if not checked:
            if not self._compounds and self._selected_element == symbol:
                self._element_buttons[symbol].setChecked(True)
            return
        self._compounds = []
        if hasattr(self, "compound_edit"):
            self.compound_edit.clear()
        if hasattr(self, "compound_status"):
            self.compound_status.setText(
                "Compound mode: enter one formula or comma-separated formulas; Chantler mass attenuation only."
            )
        self._select_element(symbol)

    def _select_element(self, symbol: str) -> None:
        if symbol not in self._element_buttons:
            return
        self._selected_element = symbol
        for other, button in self._element_buttons.items():
            if button.isChecked() != (other == symbol):
                old = button.blockSignals(True)
                button.setChecked(other == symbol)
                button.blockSignals(old)
        self._refresh_sources()

    def _apply_compound_formula(self) -> None:
        text = self.compound_edit.text().strip()
        formula_texts = [part.strip() for part in text.split(",") if part.strip()]
        if not formula_texts:
            self.compound_status.setText("Enter at least one chemical formula.")
            self.compound_edit.setFocus()
            return

        unique_formula_texts = list(dict.fromkeys(formula_texts))
        if len(unique_formula_texts) > 8:
            self.compound_status.setText("Too many compounds: enter at most 8 formulas at once.")
            self.compound_edit.setFocus()
            return

        compounds: list[Composition] = []
        for formula_text in unique_formula_texts:
            try:
                compounds.append(parse_formula(formula_text, self.database))
            except CompositionError as exc:
                self.compound_status.setText(f"Invalid formula {formula_text!r}: {exc}")
                self.compound_edit.setFocus()
                return

        self._compounds = compounds
        self.compound_edit.setText(", ".join(compound.formula for compound in compounds))
        for button in self._element_buttons.values():
            old = button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(old)

        if len(compounds) == 1:
            compound = compounds[0]
            self.compound_status.setText(
                f"{compound.formula}  |  molar mass {compound.molar_mass_g_mol:.4g} g/mol  |  "
                f"mass fractions: {compound.mass_fraction_summary()}"
            )
        else:
            self.compound_status.setText(
                f"{len(compounds)} compounds active: "
                + ", ".join(compound.formula for compound in compounds)
            )
        self.compound_status.setToolTip(
            "\n\n".join(
                f"{compound.formula}: molar mass {compound.molar_mass_g_mol:.6g} g/mol\n"
                f"Parsed stoichiometry: {compound.summary()}\n"
                f"Elemental mass fractions: {compound.mass_fraction_summary()}"
                for compound in compounds
            )
        )
        self._photon_initialized = False
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        if self._compounds:
            available = ("chantler",)
        else:
            available = self.database.sources_for(self._selected_element)
        for i in range(self.source_combo.count()):
            source = self.source_combo.itemData(i)
            enabled = source in available or (
                not self._compounds
                and source == "compare"
                and {"henke", "chantler"}.issubset(set(available))
            )
            model = self.source_combo.model()
            item = model.item(i) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(enabled)
        if self._compounds:
            self.source_combo.setCurrentIndex(self.source_combo.findData("chantler"))
        elif self.source_combo.currentData() == "compare" and not {"henke", "chantler"}.issubset(set(available)):
            self.source_combo.setCurrentIndex(self.source_combo.findData("chantler" if "chantler" in available else available[0]))
        elif self.source_combo.currentData() not in available and self.source_combo.currentData() != "compare":
            self.source_combo.setCurrentIndex(self.source_combo.findData("chantler" if "chantler" in available else available[0]))
        self._refresh_quantities()

    def _source_changed(self, *_args) -> None:
        self._refresh_quantities()

    def _quantity_changed(self, *_args) -> None:
        self._update_combo_tooltips()
        self._plot_selected()

    def _refresh_quantities(self) -> None:
        source = self.source_combo.currentData()
        if not source:
            return
        if self._compounds:
            base = ("mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g")
            available = base + (("mu_compare",) if len(self._compounds) == 1 else ())
        elif source == "compare":
            available = ("f1", "f2")
        else:
            available = self.database.quantities(self._selected_element, source)
            if source == "chantler" and all(q in available for q in ("mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g")):
                available = tuple(available) + ("mu_compare",)
        previous = self.quantity_combo.currentData()
        self.quantity_combo.blockSignals(True)
        self.quantity_combo.clear()
        for key in available:
            definition = _QUANTITIES.get(key, QuantityDefinition(key, key, key, key))
            self._add_combo_item(self.quantity_combo, definition.label, key, definition.tooltip)
        if self._compounds:
            preferred = previous if previous in available else "mu_total_cm2_g"
        else:
            preferred = previous if previous in available else ("f2" if "f2" in available else available[0])
        self.quantity_combo.setCurrentIndex(max(0, self.quantity_combo.findData(preferred)))
        self.quantity_combo.blockSignals(False)
        self._update_combo_tooltips()
        self._plot_selected()

    def _selected_sources(self) -> tuple[str, ...]:
        if self._compounds:
            return ("chantler",)
        source = self.source_combo.currentData()
        return ("henke", "chantler") if source == "compare" else (source,)

    def _display_curves(self):
        quantity = self.quantity_combo.currentData()
        max_e = None if self.full_range_check.isChecked() else self.SOFT_XRAY_MAX_EV
        curves = []
        quantities = (
            ("mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g")
            if quantity == "mu_compare"
            else (quantity,)
        )

        if self._compounds:
            for index, compound in enumerate(self._compounds):
                for q in quantities:
                    curve = compound_mass_attenuation(
                        self.database, compound, q, energy_max_eV=max_e
                    )
                    finite = np.isfinite(curve.energy_eV) & np.isfinite(curve.values)
                    source_key = f"compound:{index}:{q}"
                    curves.append((source_key, curve, curve.energy_eV[finite], curve.values[finite], q))
            return curves

        element = self._selected_element
        for source in self._selected_sources():
            if not source:
                continue
            for q in quantities:
                curve = self.database.curve(element, source, q, energy_max_eV=max_e)
                finite = np.isfinite(curve.energy_eV) & np.isfinite(curve.values)
                curves.append((source, curve, curve.energy_eV[finite], curve.values[finite], q))
        return curves

    def _plot_selected(self, *_args) -> None:
        element = self._selected_element
        quantity = self.quantity_combo.currentData()
        if not quantity:
            return
        curves = self._display_curves()
        self.ax.clear()
        self._curve_artists.clear()
        self._intersection_markers.clear()
        self._legend = None

        y_all = []
        x_all = []
        attenuation_quantity = quantity.startswith("mu_")
        mu_comparison = quantity == "mu_compare"
        for source, curve, x, y, curve_quantity in curves:
            if not x.size:
                continue
            curve_definition = _QUANTITIES.get(curve_quantity, QuantityDefinition(curve_quantity, curve_quantity, curve_quantity, curve_quantity))
            if source.startswith("compound:"):
                label = curve_definition.label if mu_comparison else f"{curve.formula} / Chantler"
            elif mu_comparison:
                label = curve_definition.label
            else:
                label = "Henke / CXRO" if source == "henke" else "Chantler / XrayDB"

            # Attenuation quantities are best viewed on a logarithmic axis.
            # Exact zero values below a photoionization threshold are valid
            # source data, but cannot be represented on a log scale.  Mask
            # them only in the plotted copy; the backend and live value readout
            # retain the exact zeros.
            y_plot = np.asarray(y, dtype=float).copy()
            if attenuation_quantity:
                y_plot[y_plot <= 0] = np.nan

            (line,) = self.ax.plot(x, y_plot, linewidth=1.25, label=label)
            (marker,) = self.ax.plot([], [], "o", markersize=4.5, markerfacecolor=line.get_color(), markeredgewidth=1.5,
                                     markeredgecolor=line.get_color(), zorder=6, label="_nolegend_")
            marker_key = f"{source}|{curve_quantity}"
            self._curve_artists.append((marker_key, label, line))
            self._intersection_markers.append((marker_key, label, marker))
            x_all.append(x)
            y_all.append(y)

        definition = _QUANTITIES.get(quantity, QuantityDefinition(quantity, quantity, quantity, quantity))
        source_mode = self.source_combo.currentData()
        if self._compounds:
            title_target = self._compounds[0].formula if len(self._compounds) == 1 else f"{len(self._compounds)} compounds"
            title_source = "Chantler / XrayDB compound mixture"
        else:
            title_target = element
            title_source = "Henke + Chantler" if source_mode == "compare" else ("Henke / CXRO" if source_mode == "henke" else "Chantler / XrayDB")
        title_quantity = "attenuation comparison" if mu_comparison else definition.label
        self.ax.set_title(f"{title_target} — {title_quantity} — {title_source}")
        self.ax.set_xlabel("Photon energy (eV)")
        self.ax.set_ylabel(definition.axis_label)
        self.ax.minorticks_on()
        self.ax.grid(which="major", linewidth=1.0, alpha=0.50)
        self.ax.grid(which="minor", linewidth=0.6, alpha=0.24)

        if attenuation_quantity:
            self.ax.set_yscale("log")
            self.ax.yaxis.set_major_formatter(_CompactLogFormatter(base=10.0))
            self.ax.yaxis.set_minor_formatter(_CompactLogFormatter(base=10.0))
        else:
            self.ax.set_yscale("linear")

        if x_all:
            data_min = min(float(np.nanmin(x)) for x in x_all if x.size)
            data_max = max(float(np.nanmax(x)) for x in x_all if x.size)
            visible_min = max(0.0, data_min)
            visible_max = data_max if self.full_range_check.isChecked() else min(self.SOFT_XRAY_MAX_EV, data_max)
            if visible_max <= visible_min:
                visible_max = visible_min + 1.0
            self.ax.set_xlim(visible_min, visible_max)
            self._configure_photon_energy(visible_min, visible_max)

        if self._curve_artists:
            self._legend = self.ax.legend(loc="best")
            self._legend.set_draggable(True)
            self._legend.set_visible(self.legend_check.isChecked())

        photon = float(self.photon_energy_spin.value())
        self._photon_marker = self.ax.axvline(photon, linestyle="--", linewidth=1.2, color="0.45", picker=6, label="_nolegend_")
        # Keep the normal compact Reference layout.  Attenuation plots use a
        # compact log formatter with a shared decade factor, so zooming does
        # not create very wide scientific-notation tick labels.
        self.figure.subplots_adjust(left=0.105, right=0.98, bottom=0.13, top=0.92)
        self._default_view_limits = (self.ax.get_xlim(), self.ax.get_ylim())
        self._update_intersections_and_values()
        self.canvas.draw_idle()

    def _reset_reference_view(self) -> None:
        """Restore the intended default view for the current Reference settings."""
        if self._default_view_limits is None:
            return
        xlim, ylim = self._default_view_limits
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        self._dragging_photon_marker = False
        self.canvas.draw_idle()

    def _configure_photon_energy(self, lo: float, hi: float) -> None:
        old = self.photon_energy_spin.blockSignals(True)
        self.photon_energy_spin.setRange(lo, hi)
        if not self._photon_initialized:
            self.photon_energy_spin.setValue(0.5 * (lo + hi))
            self._photon_initialized = True
        else:
            self.photon_energy_spin.setValue(min(max(self.photon_energy_spin.value(), lo), hi))
        self.photon_energy_spin.blockSignals(old)

    def _range_changed(self, *_args) -> None:
        self._photon_initialized = False
        self._plot_selected()

    def _on_photon_energy_changed(self, _value: float | None = None) -> None:
        if self._photon_marker is not None:
            photon = float(self.photon_energy_spin.value())
            self._photon_marker.set_xdata([photon, photon])
            self._update_intersections_and_values()
            self.canvas.draw_idle()

    def _update_intersections_and_values(self) -> None:
        element = self._selected_element
        quantity = self.quantity_combo.currentData()
        photon = float(self.photon_energy_spin.value())
        rows = []
        for marker_key, label, marker in self._intersection_markers:
            try:
                source_key, curve_quantity = marker_key.rsplit("|", 1)
                if source_key.startswith("compound:") and self._compounds:
                    compound_index = int(source_key.split(":", 2)[1])
                    value = compound_mass_attenuation_value(
                        self.database, self._compounds[compound_index], curve_quantity, photon
                    )
                else:
                    value = self.database.interpolate(element, source_key, curve_quantity, photon)
                if np.isfinite(value):
                    numeric_value = float(value)
                    rows.append((label, numeric_value))
                    if curve_quantity.startswith("mu_") and numeric_value <= 0:
                        # A true zero is meaningful in the tabulation/readout,
                        # but it cannot be drawn on a logarithmic Y axis.
                        marker.set_visible(False)
                    else:
                        marker.set_data([photon], [numeric_value])
                        marker.set_visible(True)
                else:
                    marker.set_visible(False)
                    rows.append((label, None))
            except (EnergyOutOfRangeError, ValueError, RuntimeError):
                marker.set_visible(False)
                rows.append((label, None))
        self._populate_values(rows)

    def _populate_values(self, rows: list[tuple[str, float | None]]) -> None:
        self.values_table.setRowCount(len(rows))
        quantity = self.quantity_combo.currentData()
        units = _QUANTITIES.get(quantity, QuantityDefinition(quantity, quantity, "", "")).axis_label
        if "(" in units and ")" in units:
            units = units.split("(", 1)[1].rsplit(")", 1)[0]
        else:
            units = ""
        for row, (label, value) in enumerate(rows):
            vtext = "N/A" if value is None else self._format_value(value)
            if units and value is not None:
                vtext = f"{vtext} {units}"
            self.values_table.setItem(row, 0, QTableWidgetItem(label))
            self.values_table.setItem(row, 1, QTableWidgetItem(vtext))

    @staticmethod
    def _format_value(value: float) -> str:
        magnitude = abs(float(value))
        if magnitude != 0 and (magnitude < 1e-4 or magnitude >= 1e4):
            return f"{float(value):.5e}"
        return f"{float(value):.7g}"

    def _set_legend_visible(self, visible: bool) -> None:
        if self._legend is not None:
            self._legend.set_visible(bool(visible))
            self.canvas.draw_idle()

    def _toolbar_is_active(self) -> bool:
        return bool(getattr(self.toolbar, "mode", ""))

    def _near_photon_marker(self, event) -> bool:
        if self._photon_marker is None or event.inaxes is not self.ax or event.x is None:
            return False
        photon = float(self.photon_energy_spin.value())
        try:
            marker_x = self.ax.transData.transform((photon, 1.0))[0]
        except Exception:
            return False
        return abs(float(event.x) - float(marker_x)) <= 8.0

    def _on_plot_press(self, event) -> None:
        if event.button != 1 or self._toolbar_is_active():
            return
        if self._near_photon_marker(event):
            self._dragging_photon_marker = True

    def _on_plot_motion(self, event) -> None:
        if not self._dragging_photon_marker or event.inaxes is not self.ax or event.xdata is None:
            return
        value = min(max(float(event.xdata), self.photon_energy_spin.minimum()), self.photon_energy_spin.maximum())
        self.photon_energy_spin.setValue(value)

    def _on_plot_release(self, _event) -> None:
        self._dragging_photon_marker = False
