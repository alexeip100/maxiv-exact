"""Live previews for the Processed Data spectrum operations."""

import numpy as np
from matplotlib.lines import Line2D
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ..processing import subtract_spectra


class _PreviewSpinBox(QDoubleSpinBox):
    def __init__(self, minimum_decimals):
        super().__init__()
        self._minimum_decimals = minimum_decimals

    def textFromValue(self, value):
        locale = self.locale()
        text = locale.toString(value, "f", self.decimals())
        whole, separator, fraction = text.partition(locale.decimalPoint())
        return whole + separator + fraction.rstrip(locale.zeroDigit()).ljust(
            self._minimum_decimals, locale.zeroDigit()
        )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.interpretText()
            event.accept()
            return
        super().keyPressEvent(event)


def _numeric_input(value, minimum_decimals, decimals, step, limit, suffix=""):
    spin = _PreviewSpinBox(minimum_decimals)
    spin.setDecimals(decimals)
    spin.setRange(-limit, limit)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setSuffix(suffix)
    return spin


def _buttons(dialog, layout, text):
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    accept = buttons.button(QDialogButtonBox.StandardButton.Ok)
    accept.setText(text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return accept


class EnergyCalibrationDialog(QDialog):
    def __init__(self, parent, spectra):
        super().__init__(parent)
        self.setWindowTitle("Calibrate E")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Photon-energy shift for each visible spectrum"))
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)
        self._preview = {}
        self._inputs = {}
        for key, (label, line, shift, has_energy) in spectra.items():
            spin = _numeric_input(shift, 2, 5, 0.05, 100000, " eV")
            spin.setEnabled(has_energy)
            if not has_energy:
                spin.setToolTip("This spectrum has no photon-energy axis.")
            form.addRow(label, spin)
            self._preview[key] = line, np.asarray(line.get_xdata(), dtype=float).copy(), shift
            if has_energy:
                self._inputs[key] = spin
                spin.valueChanged.connect(lambda value, k=key: self._shift_curve(k, value))
        _buttons(self, layout, "Apply").setEnabled(bool(self._inputs))
        self.resize(405, min(370, 100 + 32 * len(spectra)))

    def _shift_curve(self, key, shift):
        line, x, applied = self._preview[key]
        line.set_xdata(x + (shift - applied))
        self.parent().canvas_proc.draw_idle()

    def shifts(self):
        return {key: spin.value() for key, spin in self._inputs.items()}

    def done(self, result):
        for line, x, _ in self._preview.values():
            line.set_xdata(x)
        self.parent().canvas_proc.draw_idle()
        super().done(result)


class SpectrumSubtractionDialog(QDialog):
    def __init__(self, parent, spectra, input_state):
        super().__init__(parent)
        self.setWindowTitle("Subtract spectra")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.spectra = spectra
        self.results = {}
        self._preview = []
        self._ylim = parent.proc_ax.get_ylim()
        self._autoscale_y = parent.proc_ax.get_autoscaley_on()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(input_state))
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Single", "Series"])
        self.sample = QComboBox()
        self.reference = QComboBox()
        for key, (label, *_rest) in spectra.items():
            self.reference.addItem(label, key)
        self.multiplier = _numeric_input(1, 3, 6, 0.01, 1000000)
        form.addRow("Mode", self.mode)
        form.addRow("Sample", self.sample)
        form.addRow("Reference", self.reference)
        form.addRow("Reference multiplier", self.multiplier)
        layout.addLayout(form)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.create = _buttons(self, layout, "Create")
        self.reference.currentIndexChanged.connect(self._reference_changed)
        self.mode.currentIndexChanged.connect(self._update_preview)
        self.sample.currentIndexChanged.connect(self._update_preview)
        self.multiplier.valueChanged.connect(self._update_preview)
        self._reference_changed()

    def _reference_changed(self):
        current = self.sample.currentData()
        self.sample.blockSignals(True)
        self.sample.clear()
        for key, (label, *_rest) in self.spectra.items():
            if key != self.reference.currentData():
                self.sample.addItem(label, key)
        self.sample.setCurrentIndex(max(0, self.sample.findData(current)))
        self.sample.blockSignals(False)
        self._update_preview()

    def _clear_preview(self):
        for line in self._preview:
            if line in self.parent().proc_ax.lines:
                line.remove()
        self._preview.clear()

    def _update_preview(self):
        self._clear_preview()
        self.results = {}
        series = self.mode.currentText() == "Series"
        self.sample.setEnabled(not series)
        reference = self.reference.currentData()
        samples = [key for key in self.spectra if key != reference] if series else [self.sample.currentData()]
        _, reference_line, reference_energy = self.spectra[reference]
        failures = []
        ax = self.parent().proc_ax
        for key in samples:
            label, sample_line, sample_energy = self.spectra[key]
            try:
                if not (sample_energy and reference_energy):
                    raise ValueError("Both spectra need photon-energy axes.")
                x, y = subtract_spectra(sample_line.get_data(), reference_line.get_data(), self.multiplier.value())
            except ValueError as error:
                failures.append(f"{label}: {error}")
                continue
            self.results[key] = x, y
            line = Line2D(x, y, color=sample_line.get_color(), linestyle="--",
                          linewidth=2, zorder=5, label="_difference_preview")
            ax.add_artist(line)
            line.set_clip_path(ax.patch)
            self._preview.append(line)

        # Preserve the view unless a preview would be completely outside its y range.
        low, high = sorted(self._ylim)
        bottom, top = low, high
        xmin, xmax = sorted(ax.get_xlim())
        for x, y in self.results.values():
            shown = y[(x >= xmin) & (x <= xmax) & np.isfinite(y)]
            if shown.size:
                minimum, maximum = float(shown.min()), float(shown.max())
                margin = 0.04 * (high - low)
                if maximum < low:
                    bottom = min(bottom, minimum - margin)
                if minimum > high:
                    top = max(top, maximum + margin)
        limits = (bottom, top) if self._ylim[0] <= self._ylim[1] else (top, bottom)
        ax.set_ylim(limits)
        self.warning.setText(
            failures[0] + (f" ({len(failures)} skipped)" if len(failures) > 1 else "")
            if failures else "Dashed lines show the differences."
        )
        self.create.setEnabled(bool(self.results))
        self.parent().canvas_proc.draw_idle()

    def done(self, result):
        self._clear_preview()
        self.parent().proc_ax.set_ylim(self._ylim, auto=self._autoscale_y)
        self.parent().canvas_proc.draw_idle()
        super().done(result)
