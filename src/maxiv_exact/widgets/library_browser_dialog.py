from PyQt6.QtWidgets import (
    QDialog,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt

import h5py


class LibraryBrowserDialog(QDialog):
    """
    Dialog that lists reference spectra stored in the library and lets the user
    choose one or more to load into the plot.

    Includes an option to delete a selected reference from the library file.
    """

    def __init__(self, entries, library_path=None, parent=None):
        super().__init__(parent)
        self.entries = entries or []
        self.library_path = library_path

        self.setWindowTitle("Load reference")
        self.resize(520, 420)

        layout = QVBoxLayout(self)

        info = QLabel("Select one or more reference spectra to load:")
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)

# Populate list
        for entry in self.entries:
            label = entry.get("label", "") or ""
            meta = entry.get("meta") or {}
            element = (str(meta.get("element") or "")).strip()
            edge = (str(meta.get("edge") or "")).strip()
            compound = (str(meta.get("compound") or "")).strip()

            display = label
            if element or edge or compound:
                parts = [p for p in [element, edge, compound] if p]
# keep display as label, but show metadata in tooltip
                tip = " / ".join(parts)
                if tip:
                    display = f"{label}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, entry)
# Tooltip helps identify entries
            tooltip_lines = [f"Group: {entry.get('group_name','')}".strip()]
            if element or edge or compound:
                tooltip_lines.append(f"{element} {edge} {compound}".strip())
            comment = (str(meta.get("comment") or "")).strip()
            if comment:
                tooltip_lines.append(comment)
            item.setToolTip("\n".join([l for l in tooltip_lines if l]))
            self.list_widget.addItem(item)

# Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_delete = QPushButton("Delete reference")
        self.button_box.addButton(self.btn_delete, QDialogButtonBox.ButtonRole.ActionRole)

        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        self.btn_delete.clicked.connect(self._on_delete_reference)

    def _on_accept(self):
        selected = self.list_widget.selectedItems()
        if not selected:
# Allow OK with nothing selected, but treat as cancel.
            self.reject()
            return
        self.accept()

    def get_selected_entries(self):
        """Return list of entry dicts for selected items."""
        result = []
        for item in self.list_widget.selectedItems():
            entry = item.data(Qt.ItemDataRole.UserRole)
            if entry:
                result.append(entry)
        return result

    def _on_delete_reference(self):
        if not self.library_path:
            QMessageBox.information(
                self,
                "Delete reference",
                "Library file location is unknown. Cannot delete references.",
            )
            return

        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(
                self,
                "Delete reference",
                "Please select a reference spectrum to delete.",
            )
            return

        # For simplicity: delete the first selected item (matches user's selected spectrum)
        item = selected_items[0]
        entry = item.data(Qt.ItemDataRole.UserRole) or {}
        gname = entry.get("group_name")
        label = entry.get("label") or gname or "selected reference"

        resp = QMessageBox.warning(
            self,
            "Delete reference",
            f"You are about to permanently delete\n\n  {label}\n\nfrom the spectral library.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        try:
            with h5py.File(self.library_path, "r+") as f:
                if "spectra" not in f:
                    raise KeyError("spectra group not found")
                spectra = f["spectra"]
                if gname not in spectra:
                    raise KeyError(f"Reference '{gname}' not found")
                del spectra[gname]
        except Exception as ex:
            QMessageBox.critical(
                self,
                "Delete reference",
                f"Failed to delete reference from library.\n\n{ex}",
            )
            return

        # Remove from list widget and local entries
        row = self.list_widget.row(item)
        self.list_widget.takeItem(row)
        try:
            self.entries = [e for e in self.entries if e.get("group_name") != gname]
        except Exception:
            pass

        QMessageBox.information(
            self,
            "Delete reference",
            "Reference deleted from the library.",
        )
