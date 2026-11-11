"""Experimental metadata and fit results dialogs for NEXAFS Trends."""

from math import isfinite

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..nexafs_fit.model import Gaussian
from ..nexafs_fit.trends import Experiment, PASSES, fit_status


def _item(text):
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class FitNumberDelegate(QStyledItemDelegate):
    """Edit the underlying number while keeping a rounded table display."""

    number_edited = pyqtSignal(int, int, str)

    def setEditorData(self, editor, index):  # noqa: N802
        value = index.data(Qt.ItemDataRole.UserRole)
        editor.setText("" if value is None else value if isinstance(value, str) else repr(float(value)))
        editor.selectAll()

    def setModelData(self, editor, model, index):  # noqa: N802
        self.number_edited.emit(index.row(), index.column(), editor.text())


class ExperimentalParametersDialog(QDialog):
    def __init__(self, group, experiment, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experimental parameters")
        self._spectra = group.spectra
        self._values = dict(experiment.values)
        self._invalid = set()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(experiment.name)
        self.name.setPlaceholderText("e.g. Temperature")
        self.unit = QLineEdit(experiment.unit)
        self.unit.setPlaceholderText("e.g. K")
        form.addRow("Parameter", self.name)
        form.addRow("Unit", self.unit)
        layout.addLayout(form)
        self.table = QTableWidget(len(self._spectra), 3)
        self.table.setHorizontalHeaderLabels(["Spectrum", "Value", "Status"])
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        delegate = FitNumberDelegate(self.table)
        delegate.number_edited.connect(self._edit_value)
        self.table.setItemDelegateForColumn(1, delegate)
        for i, spectrum in enumerate(self._spectra):
            item = _item(spectrum.label)
            item.setToolTip(spectrum.key)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem())
            self._display(i, self._values.get(spectrum.key))
        layout.addWidget(self.table)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.table.cellChanged.connect(self._edit_value)
        self._update_note()
        self.resize(520, 400)

    @property
    def experiment(self):
        return Experiment(self.name.text().strip(), self.unit.text().strip(), dict(self._values))

    def _display(self, row, value):
        with QSignalBlocker(self.table):
            item = self.table.item(row, 1)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setText("" if value is None else value if isinstance(value, str) else f"{value:.8g}")
            state = "Invalid" if row in self._invalid else "Missing" if value is None else ""
            self.table.setItem(row, 2, _item(state))

    def _edit_value(self, row, column, entered=None):
        if column != 1:
            return
        text = (self.table.item(row, column).text() if entered is None else entered).strip()
        key = self._spectra[row].key
        try:
            value = float(text) if text else None
            if value is not None and not isfinite(value):
                raise ValueError()
        except ValueError:
            self._invalid.add(row)
            self._display(row, text)
        else:
            self._invalid.discard(row)
            if value is None:
                self._values.pop(key, None)
            else:
                self._values[key] = value
            self._display(row, value)
        self._update_note()

    def _update_note(self):
        self.ok_button.setEnabled(not self._invalid)
        if self._invalid:
            self.note.setText("Correct invalid values or clear their cells.")
        else:
            self.note.setText("Blank values are omitted when plotting against the experimental parameter.")

    def accept(self):
        if not self._invalid:
            super().accept()


class TrendResultsDialog(QDialog):
    def __init__(self, group, results, names, experiment, outdated, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NEXAFS fit results")
        self.spectrum_key = None
        self._diagnostics = []
        layout = QVBoxLayout(self)
        headings = ("Spectrum", "Identifier", experiment.axis_label, "Pass", "Component", "Status",
                    "Center / position (eV)", "FWHM (eV)", "Area / height", "Residual RMS")
        self.table = QTableWidget(0, len(headings))
        self.table.setHorizontalHeaderLabels(headings)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(105)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for stage, label in PASSES.items():
            result = results.get(stage)
            fits = {} if result is None else {row.key: row for row in result.spectra}
            for spectrum in group.spectra:
                row = fits.get(spectrum.key)
                status = fit_status(row)
                if stage in outdated:
                    status += " · Outdated"
                values = row.components if row is not None and row.usable else ()
                specs = (None,) if result is None else result.model.components
                for index, spec in enumerate(specs):
                    fit = values[index] if index < len(values) else None
                    component = "" if spec is None else names.get(spec.key, spec.key)
                    center, width, amp = "", "", ""
                    amplitude_help = ""
                    if isinstance(fit, Gaussian):
                        center, width, amp = f"{fit.center:.2f}", f"{fit.fwhm:.2f}", f"{fit.area:.4g}"
                        amplitude_help = "Integrated area (processed intensity × eV)"
                    elif fit is not None:
                        center, width, amp = f"{fit.position:.2f}", f"{fit.fwhm:.2f}", f"{fit.height:.4g}"
                        amplitude_help = "IP height (processed intensity); FWHM of the step derivative"
                    value = experiment.values.get(spectrum.key)
                    diagnostic = None if row is None else row.diagnostics
                    rms = "" if diagnostic is None or diagnostic.rms is None else f"{diagnostic.rms:.4g}"
                    self._append((spectrum.label, spectrum.key, "" if value is None else f"{value:.8g}",
                                  label, component, status, center, width, amp, rms), amplitude_help)
                    self._diagnostics.append((diagnostic, None if result is None else result.global_diagnostics))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 155)
        self.table.currentCellChanged.connect(self._show_diagnostics)
        self.table.cellDoubleClicked.connect(self._choose_spectrum)
        self.table.selectRow(0)
        self.resize(1120, 545)

    def _append(self, fields, amplitude_help):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, field in enumerate(fields):
            item = _item(field)
            if col == 1:
                item.setToolTip(field)
            elif col == 8:
                item.setToolTip(amplitude_help)
            self.table.setItem(row, col, item)

    def _show_diagnostics(self, row):
        if row < 0:
            return
        local, global_fit = self._diagnostics[row]
        lines = []
        for diag, prefix in ((local, "Spectrum"), (global_fit, "Global")):
            if diag is None:
                continue
            lines.append(f"{prefix} · {diag.message}")
            for key, value in (("Solver", diag.solver), ("Status", diag.status), ("Evaluations", diag.nfev),
                               ("Iterations", diag.nit), ("Optimality", diag.optimality),
                               ("RMS", diag.rms), ("Condition number", diag.condition_number)):
                if value is not None:
                    lines.append(f"{key}: {value:.4g}" if isinstance(value, float) else f"{key}: {value}")
            lines.extend(diag.bounds_reached)
            lines.extend(diag.warnings)
        self.details.setPlainText("\n".join(lines) if lines else "No diagnostics are available.")

    def _choose_spectrum(self, row, _column):
        self.spectrum_key = self.table.item(row, 1).text()
        self.accept()
