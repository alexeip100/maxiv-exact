"""Optional bounds for NEXAFS component centers and FWHMs."""

from dataclasses import replace

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QVBoxLayout, QWidget,
)

def _choice(values):
    combo = QComboBox()
    for text, value in values:
        combo.addItem(text, value)
    return combo


class AdvancedConstraintsDialog(QDialog):
    def __init__(self, components, names, parent=None, *, selected_row=0):
        super().__init__(parent)
        self.setWindowTitle("NEXAFS Advanced Constraints")
        self._drafts = list(components)
        self._row = selected_row
        layout = QVBoxLayout(self)
        message = QLabel(
            "Set optional bounds for free centers and widths. Leave a bound blank to use the solver default."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        form = QFormLayout()
        layout.addLayout(form)
        labels = [names[spec.key] for spec in components]
        self.component = _choice([
            (f"{label} ({spec.key})" if labels.count(label) > 1 else label, row)
            for row, (label, spec) in enumerate(zip(labels, components))
        ])
        self.component.setCurrentIndex(selected_row)
        form.addRow("Component", self.component)
        self.position_limits = self._bounds_row(form, "Position bounds (eV)")
        self.width_limits = self._bounds_row(form, "FWHM bounds (eV)")
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.component.currentIndexChanged.connect(self._select)
        self._load()
        self.resize(505, self.sizeHint().height())

    @staticmethod
    def _bounds_row(form, label):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        lower, upper = QLineEdit(), QLineEdit()
        lower.setPlaceholderText("Auto minimum")
        upper.setPlaceholderText("Auto maximum")
        row.addWidget(lower)
        row.addWidget(upper)
        form.addRow(label, container)
        return lower, upper

    @property
    def components(self):
        return tuple(self._drafts)

    def _load(self):
        spec = self._drafts[self._row]
        for edits, bounds in ((self.position_limits, spec.position_bounds), (self.width_limits, spec.width_bounds)):
            for edit, bound in zip(edits, bounds):
                edit.setText("" if bound is None else str(bound))
        self.error.clear()

    def _save(self):
        spec = self._drafts[self._row]
        try:
            position_bounds = tuple(float(edit.text()) if edit.text().strip() else None for edit in self.position_limits)
            width_bounds = tuple(float(edit.text()) if edit.text().strip() else None for edit in self.width_limits)
            self._drafts[self._row] = replace(
                spec,
                position_bounds=position_bounds,
                width_bounds=width_bounds,
            )
        except ValueError as error:
            self.error.setText(f"{self.component.itemText(self._row)}: {error}")
            return False
        return True

    def _select(self, row):
        if self._save():
            self._row = row
            self._load()
        else:
            with QSignalBlocker(self.component):
                self.component.setCurrentIndex(self._row)

    def accept(self):
        if self._save():
            super().accept()
