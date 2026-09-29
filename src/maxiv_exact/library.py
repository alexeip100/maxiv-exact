import os
from datetime import datetime

import h5py
import numpy as np
from PyQt6.QtWidgets import QMessageBox, QDialog

from .widgets.library_dialog import AddToLibraryDialog
from .widgets.library_browser_dialog import LibraryBrowserDialog


class LibraryMixin:
    """
    Mixin that manages the reference spectra library stored in an HDF5 file.

    Responsibilities:
    - Determine the location of the library file (in the repo folder).
    - Initialize the HDF5 structure on first use.
    - Append new spectra to the library (from plotted curves).
    - Load existing reference spectra from the library into the Plotted Data plot.
    - Prevent duplicate entries based on (source_file, source_entry,
      detector, post_normalization).
    """

# --- / HDF5 helpers
    def _get_library_path(self) -> str:
        """
        Return the path of the reference spectra library file.

        For now, this lives alongside the Python modules in the
        maxiv_exact package directory (i.e. the repo folder with
        all *.py files).
        """
        try:
            from pathlib import Path
            root = Path(__file__).resolve().parent
            return str(root / "library.h5")
        except Exception:
# Conservative fallback: current working directory
            return os.path.join(os.getcwd(), "library.h5")

    def _ensure_library_file(self) -> str:
        """
        Make sure the library file exists and has at least the /spectra group.
        Returns the path to the library file.
        """
        path = self._get_library_path()
        if not os.path.exists(path):
            try:
                with h5py.File(path, "w") as f:
                    f.attrs["library_version"] = "1.0"
                    f.attrs["created_with"] = "maxiv_exact"
                    f.attrs["created"] = datetime.utcnow().isoformat()
                    f.require_group("spectra")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Library error",
                    f"Could not create the library file:\n{path}\n\n{exc}",
                )
                raise
        else:
            try:
                with h5py.File(path, "a") as f:
                    f.require_group("spectra")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Library error",
                    f"Could not open the library file:\n{path}\n\n{exc}",
                )
                raise
        return path

    def _is_duplicate_entry(self, f: h5py.File, source_file: str, source_entry: str,
                            detector: str, post_normalization: str) -> bool:
        """
        Check if an entry with the given key metadata already exists in the library.
        """
        try:
            spectra = f.get("spectra")
            if spectra is None:
                return False
            for name, grp in spectra.items():
                try:
                    if not isinstance(grp, h5py.Group):
                        continue
                    sf = str(grp.attrs.get("source_file", ""))
                    se = str(grp.attrs.get("source_entry", ""))
                    det = str(grp.attrs.get("detector", ""))
                    norm = str(grp.attrs.get("post_normalization", ""))
                    if (
                        sf == source_file
                        and se == source_entry
                        and det == detector
                        and norm == post_normalization
                    ):
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _create_new_spectrum_group(self, f: h5py.File):
        """
        Create a new numbered subgroup under /spectra, using zero-padded integers.
        """
        spectra_grp = f.require_group("spectra")
        existing_indices = []
        for name in spectra_grp.keys():
            try:
                existing_indices.append(int(name))
            except ValueError:
                continue
        next_index = (max(existing_indices) + 1) if existing_indices else 1
        name = f"{next_index:06d}"
        return spectra_grp.create_group(name)

# --- / "Add to library" from plotted list
    def on_add_to_library_requested(self, storage_key: str):
        QMessageBox.warning(
            self,
            "Reference library (experimental)",
            "The reference-data library functionality is in an early, experimental state. "
            "The current library content is only a demonstration and may include placeholder, "
            "test or otherwise unverified spectra. Please treat any reference spectra with caution."
        )

        """
        Slot connected to CurveListItemWidget.addToLibraryRequested.

        storage_key is the internal key used for this plotted curve.
        """
        if not storage_key:
            return

# Reference curves that came from the library itself should not be re-added.
        meta_src = getattr(self, "plotted_metadata", {})
        if isinstance(meta_src, dict):
            pm = meta_src.get(storage_key) or {}
            if pm.get("is_reference"):
                QMessageBox.information(
                    self,
                    "Library",
                    "This curve is already a reference from the library and cannot be added again.",
                )
                return

# Prepare automatic metadata from the plotted curve context.
        auto_meta = {}
        try:
            if isinstance(meta_src, dict) and storage_key in meta_src:
                auto_meta.update(meta_src.get(storage_key) or {})
        except Exception:
            auto_meta = {}

        auto_meta.setdefault("detector", "")
        auto_meta.setdefault("source_file", "")
        auto_meta.setdefault("source_entry", "")
        auto_meta.setdefault("post_normalization", "None")

        dialog_meta = {
            "element": "",
            "edge": "",
            "compound": "",
            "resolution_meV": "",
            "comment": "",
            **auto_meta,
        }

        dlg = AddToLibraryDialog(dialog_meta, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        meta = dlg.get_metadata()

# Collect the curve data (x, y)
        x = None
        y = None
        try:
            if hasattr(self, "original_line_data") and storage_key in getattr(self, "original_line_data", {}):
                x, y = self.original_line_data[storage_key]
            elif hasattr(self, "plotted_lines") and storage_key in getattr(self, "plotted_lines", {}):
                line = self.plotted_lines[storage_key]
                x = np.asarray(line.get_xdata())
                y = np.asarray(line.get_ydata())
        except Exception:
            x = None
            y = None

        if x is None or y is None:
            QMessageBox.warning(
                self,
                "Library",
                "Could not retrieve curve data for this spectrum.",
            )
            return

        if getattr(x, "size", 0) == 0 or getattr(y, "size", 0) == 0:
            QMessageBox.warning(
                self,
                "Library",
                "Curve data is empty; cannot add to library.",
            )
            return

        if x.shape != y.shape:
            try:
                n = min(int(x.size), int(y.size))
                x = np.asarray(x).ravel()[:n]
                y = np.asarray(y).ravel()[:n]
            except Exception:
                QMessageBox.warning(
                    self,
                    "Library",
                    "X and Y data lengths are inconsistent; cannot add to library.",
                )
                return

        path = self._ensure_library_file()

        source_file = str(meta.get("source_file", "") or "")
        source_entry = str(meta.get("source_entry", "") or "")
        detector = str(meta.get("detector", "") or "")
        post_norm = str(meta.get("post_normalization", "") or "None")

        try:
            with h5py.File(path, "a") as f:
                if self._is_duplicate_entry(f, source_file, source_entry, detector, post_norm):
                    QMessageBox.information(
                        self,
                        "Library",
                        "This spectrum (same source, detector and normalization) "
                        "is already present in the library.",
                    )
                    return
# Check for existing references with same (element, edge, compound)
                element_label = str(meta.get("element", "") or "").strip()
                edge_label = str(meta.get("edge", "") or "").strip()
                compound_label = str(meta.get("compound", "") or "").strip()
                label_value = None
                if element_label and edge_label and compound_label:
                    base_label = f"{element_label} {edge_label} in {compound_label}"
                    same_count = 0
                    try:
                        spectra_grp = f.get("spectra")
                    except Exception:
                        spectra_grp = None
                    if isinstance(spectra_grp, h5py.Group):
                        for gname, grp_existing in spectra_grp.items():
                            if not isinstance(grp_existing, h5py.Group):
                                continue
                            try:
                                e2 = str(grp_existing.attrs.get("element", "") or "").strip()
                                edge2 = str(grp_existing.attrs.get("edge", "") or "").strip()
                                comp2 = str(grp_existing.attrs.get("compound", "") or "").strip()
                            except Exception:
                                continue
                            if e2 == element_label and edge2 == edge_label and comp2 == compound_label:
                                same_count += 1

                    if same_count >= 1:
                        reply = QMessageBox.question(
                            self,
                            "Library",
                            "A spectrum with the same element, absorption edge and compound\n"
                            f"({base_label}) is already present in the library.\n\n"
                            "Do you want to add another version? It will be stored with a suffix (-2, -3, ...).",
                            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                            QMessageBox.StandardButton.Cancel,
                        )
                        if reply != QMessageBox.StandardButton.Ok:
                            return
                        suffix = same_count + 1
                        label_value = f"{base_label}-{suffix}"
                    else:
                        label_value = base_label
                else:
                    label_value = None


                grp = self._create_new_spectrum_group(f)

                grp.create_dataset("x", data=np.asarray(x))
                grp.create_dataset("y", data=np.asarray(y))

                grp.attrs["element"] = str(meta.get("element", ""))
                grp.attrs["edge"] = str(meta.get("edge", ""))
                grp.attrs["compound"] = str(meta.get("compound", ""))
                if label_value:
                    grp.attrs["label"] = label_value

                res_val = meta.get("resolution_meV", "")
                try:
                    grp.attrs["resolution_meV"] = float(res_val)
                except Exception:
                    grp.attrs["resolution_meV"] = str(res_val)

                grp.attrs["detector"] = detector
                grp.attrs["source_file"] = source_file
                grp.attrs["source_entry"] = source_entry
                grp.attrs["post_normalization"] = post_norm
                grp.attrs["comment"] = str(meta.get("comment", ""))
                grp.attrs["created"] = datetime.utcnow().isoformat()
                grp.attrs["storage_key"] = storage_key

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Library error",
                f"Could not write to the library file:\n{path}\n\n{exc}",
            )
            raise

        QMessageBox.information(
            self,
            "Library",
            "Spectrum has been added to the library.",
        )

# --- / "Load reference" button: load from library into Plotted Data
    def on_load_reference_clicked(self):
        QMessageBox.warning(
            self,
            "Reference library (experimental)",
            "The reference-data library functionality is in an early, experimental state. "
            "The current library content is only a demonstration and may include placeholder, "
            "test or otherwise unverified spectra. Please treat any reference spectra with caution."
        )

        """
        Invoked by the 'Load reference' button in the Plotted Data panel.

        Opens the library, lets the user choose entries, and then adds the
        selected reference curves to the Plotted Data plot and list.
        """
        path = self._ensure_library_file()

        entries = []
        try:
            with h5py.File(path, "r") as f:
                spectra = f.get("spectra")
                if spectra is None or not len(spectra):
                    QMessageBox.information(
                        self,
                        "Library",
                        "The reference library is empty.",
                    )
                    return

                for name, grp in spectra.items():
                    if not isinstance(grp, h5py.Group):
                        continue
                    meta = {}
                    try:
                        for key in grp.attrs.keys():
                            meta[key] = grp.attrs.get(key)
                    except Exception:
                        meta = {}

                    custom_label = (str(meta.get("label") or "")).strip()
                    element = (str(meta.get("element") or "")).strip()
                    edge = (str(meta.get("edge") or "")).strip()
                    compound = (str(meta.get("compound") or "")).strip()

                    if custom_label:
                        label = custom_label
                    elif element and edge and compound:
                        label = f"{element} {edge} in {compound}"
                    elif element and edge:
                        label = f"{element} {edge}"
                    elif element and compound:
                        label = f"{element} in {compound}"
                    else:
                        label = name
                        label = name

                    meta["source_file"] = path
                    meta["source_entry"] = f"spectra/{name}/y"
                    meta["detector"] = str(meta.get("detector") or "")

                    entries.append(
                        {
                            "group_name": name,
                            "label": label,
                            "meta": meta,
                        }
                    )
        except FileNotFoundError:
            QMessageBox.information(
                self,
                "Library",
                "The reference library file was not found.",
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Library error",
                f"Could not read the library file:\n{path}\n\n{exc}",
            )
            return

        if not entries:
            QMessageBox.information(
                self,
                "Library",
                "No reference spectra were found in the library.",
            )
            return

        dlg = LibraryBrowserDialog(entries, library_path=path, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dlg.get_selected_entries()
        if not selected:
            return

# Re-open file for reading x/y datasets
        try:
            with h5py.File(path, "r") as f:
                spectra = f.get("spectra")
                if spectra is None:
                    return

                for entry in selected:
                    gname = entry.get("group_name")
                    if not gname or gname not in spectra:
                        continue
                    grp = spectra[gname]
                    try:
                        x = grp["x"][...]
                        y = grp["y"][...]
                    except Exception:
                        continue

                    label = entry.get("label") or gname
                    meta = entry.get("meta") or {}
                    meta["is_reference"] = True
                    meta["source_file"] = path
                    meta["source_entry"] = f"spectra/{gname}/y"

                    base_key = f"LIBRARY#{gname}"
                    storage_key = base_key
                    serial = 1
                    existing = getattr(self, "plotted_curves", set())
                    while storage_key in existing:
                        serial += 1
                        storage_key = f"{base_key}#{serial}"

                    try:
                        self._add_reference_curve_to_plotted(storage_key, x, y, label, meta)
                    except Exception:
                        continue

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Library error",
                f"Could not read reference spectra from the library:\n{path}\n\n{exc}",
            )
            return
