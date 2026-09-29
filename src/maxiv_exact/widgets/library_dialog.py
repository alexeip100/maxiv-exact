from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QTextEdit,
    QFormLayout,
    QVBoxLayout,
    QMessageBox,
    QComboBox,
)

class AddToLibraryDialog(QDialog):
    """
    Dialog that collects metadata for adding a spectrum to the reference library.

    Required fields:
        - element
        - edge
        - compound
        - resolution_meV

    The following fields are auto-filled and read-only for now:
        - detector
        - source_file
        - source_entry
        - post_normalization

    Comment is optional.
    """

    def __init__(self, metadata: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add spectrum to the library")
        self.setModal(True)

        self._metadata = dict(metadata or {})

# --- Editable fields ---
        self.element_combo = QComboBox()
        elements = [
            'H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne',
            'Na', 'Mg', 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', 'K', 'Ca',
            'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',
            'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr', 'Rb', 'Sr', 'Y', 'Zr',
            'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn',
            'Sb', 'Te', 'I', 'Xe', 'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd',
            'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb',
            'Lu', 'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
            'Tl', 'Pb', 'Bi', 'Po', 'At', 'Rn', 'Fr', 'Ra', 'Ac', 'Th',
            'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm',
            'Md', 'No', 'Lr',
        ]
        self.element_combo.addItems(elements)
        current_element = str(self._metadata.get("element", "")).strip()
        if current_element and current_element in elements:
            self.element_combo.setCurrentIndex(elements.index(current_element))

        self.edge_combo = QComboBox()
        edges = [
            'K (1s)',
            'L1 (2s)',
            'L2,3 (2p)',
            'M1 (3s)',
            'M2,3 (3p)',
            'M4,5 (3d)',
            'N1 (4s)',
            'N2,3 (4p)',
            'N4,5 (4d)',
            'N6,7 (4f)',
        ]
        self.edge_combo.addItems(edges)
        current_edge = str(self._metadata.get("edge", "")).strip()
        if current_edge:
            for idx, txt in enumerate(edges):
                if current_edge.lower() == txt.lower():
                    self.edge_combo.setCurrentIndex(idx)
                    break

        self.compound_edit = QLineEdit(self._metadata.get("compound", ""))
        self.resolution_edit = QLineEdit(str(self._metadata.get("resolution_meV", "")))
        self.comment_edit = QTextEdit(self._metadata.get("comment", ""))

# --- Read-only / auto metadata ---
        raw_detector = str(self._metadata.get("detector", "") or "")
        source_entry = str(self._metadata.get("source_entry", "") or "")

# Compose a more informative detector string: "<mode> (<channel>)" / where <mode> is typically TEY / PEY / TFY / PFY and <channel>
        path = (source_entry or "").strip("/")
        tokens = path.split("/") if path else []
        last = tokens[-1] if tokens else raw_detector.strip()
        low = (last or "").lower()
        mode = ""
# Reuse the same heuristics as shorten_label in PlottingMixin:
        if "ch1" in low:
            mode = "TEY"
        elif "ch3" in low:
            mode = "PEY"
        elif "roi2_dtc" in low or "roi2" in low:
            mode = "TFY"
        elif "roi1_dtc" in low or "roi1" in low:
            mode = "PFY"

        channel = last or raw_detector.strip()
        display_detector = ""
        if mode and channel and channel != mode:
            display_detector = f"{mode} ({channel})"
        elif mode:
            display_detector = mode
        elif raw_detector:
            display_detector = raw_detector.strip()
        elif channel:
            display_detector = channel


        self.detector_edit = QLineEdit(display_detector)
        self.detector_edit.setReadOnly(True)
        src_file = self._metadata.get("source_file", "") or ""
        src_entry = self._metadata.get("source_entry", "") or ""
        src_display = f"{src_file} :: {src_entry}".strip()
        self.source_edit = QLineEdit(src_display)
        self.source_edit.setReadOnly(True)
        self.postnorm_edit = QLineEdit(self._metadata.get("post_normalization", "None"))
        self.postnorm_edit.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Element*:", self.element_combo)
        form.addRow("Absorption edge*:", self.edge_combo)
        form.addRow("Chemical compound*:", self.compound_edit)
        form.addRow("Resolution (meV)*:", self.resolution_edit)
        form.addRow("Detector:", self.detector_edit)
        form.addRow("Source:", self.source_edit)
        form.addRow("Post-normalization:", self.postnorm_edit)
        form.addRow("Comment:", self.comment_edit)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        self.resize(520, 360)

    def _on_accept(self):
        missing = []
        if not self.element_combo.currentText().strip():
            missing.append("Element")
        if not self.edge_combo.currentText().strip():
            missing.append("Absorption edge")
        if not self.compound_edit.text().strip():
            missing.append("Chemical compound")

        if missing:
            QMessageBox.warning(
                self,
                "Incomplete metadata",
                "Please fill in the following required fields before adding:\n- "
                + "\n- ".join(missing),
            )
            return

# Validate resolution as a number
        res_text = self.resolution_edit.text().strip()
        try:
            float(res_text)
        except Exception:
            QMessageBox.warning(
                self,
                "Invalid resolution",
                "Resolution (meV) must be a number.",
            )
            return

        self.accept()

    def get_metadata(self) -> dict:
        """Return a dictionary with all metadata fields filled from the dialog."""
        meta = dict(self._metadata)  # shallow copy

        meta["element"] = self.element_combo.currentText().strip()
        meta["edge"] = self.edge_combo.currentText().strip()
        meta["compound"] = self.compound_edit.text().strip()
        meta["resolution_meV"] = float(self.resolution_edit.text().strip())
        meta["comment"] = self.comment_edit.toPlainText().strip()

        # detector, source_file, source_entry, post_normalization stay unchanged.
        return meta
