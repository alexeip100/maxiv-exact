"""Small bridge between Processed Data and the isolated self-absorption dialog."""
from __future__ import annotations

import numpy as np

from .data import lookup_energy
from .processing import apply_normalization
from PyQt6.QtCore import Qt


class SelfAbsorptionMixin:
    """Eligibility and launcher logic only; no correction physics lives here."""

    def _self_absorption_visible_keys(self):
        plot_data = getattr(self, "plot_data", {}) or {}
        vis = getattr(self, "raw_visibility", {}) or {}
        return [k for k in plot_data.keys() if bool(vis.get(k, False))]

    def _self_absorption_is_pfy_key(self, key: str) -> bool:
        try:
            parts = str(key).split("##", 1)
            dataset = parts[1] if len(parts) == 2 else str(key)
            candidates = list(self.channel_config.get_candidates("PFY"))
            if not candidates:
                pat = str(self.channel_config.get_pattern("PFY") or "")
                candidates = [pat] if pat else []
            text = dataset.lower()
            return any(str(c).strip().lower() in text for c in candidates if str(c).strip())
        except Exception:
            return False

    def self_absorption_eligibility(self):
        keys = self._self_absorption_visible_keys()
        if len(keys) != 1:
            return False, "Exactly one Processed Data spectrum must be visible."
        key = keys[0]
        if not self._self_absorption_is_pfy_key(key):
            return False, "The visible spectrum is not identified as PFY by the active channel profile."
        chk = getattr(self, "chk_normalize", None)
        if chk is None or not chk.isChecked():
            return False, "Normalize by I₀ must be enabled."
        combo = getattr(self, "combo_norm", None)
        if combo is None or combo.count() < 1 or not str(combo.currentText()).strip():
            return False, "A valid I₀ channel must be selected."
        if bool(getattr(self, "chk_sum", None) and self.chk_sum.isChecked()):
            return False, "Summed curves are not supported by Level 1."
        return True, ""

    def update_self_absorption_action_state(self):
        ok, reason = self.self_absorption_eligibility()
        action = getattr(self, "sa_correction_action", None)
        if action is not None:
            action.setEnabled(bool(ok))
            action.setToolTip(
                "Open isolated Level-1 PFY self-absorption correction diagnostics"
                if ok else reason
            )

    def open_self_absorption_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        ok, reason = self.self_absorption_eligibility()
        if not ok:
            QMessageBox.information(self, "Self-absorption correction", reason)
            self.update_self_absorption_action_state()
            return
        confirmation = QMessageBox.question(
            self,
            "SA Correction — work in progress",
            "Self-absorption correction is a work in progress and is not yet validated for routine use.\n\n"
            "Do you want to explore the experimental tool?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmation != QMessageBox.StandardButton.Ok:
            return
        key = self._self_absorption_visible_keys()[0]
        parts = str(key).split("##", 1)
        if len(parts) != 2:
            QMessageBox.warning(self, "Self-absorption correction", "The selected curve key is invalid.")
            return
        abs_path, hdf5_path = parts
        y_raw = np.asarray((getattr(self, "plot_data", {}) or {}).get(key), dtype=float).ravel()
        parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
        x = np.asarray(lookup_energy(self, abs_path, parent, len(y_raw)), dtype=float).ravel()
        y = np.asarray(apply_normalization(self, abs_path, parent, y_raw), dtype=float).ravel()
        n = min(x.size, y.size)
        if n < 3:
            QMessageBox.warning(self, "Self-absorption correction", "The selected PFY curve contains too few points.")
            return
        try:
            label = self.shorten_label(hdf5_path) if hasattr(self, "shorten_label") else hdf5_path
        except Exception:
            label = hdf5_path
        from .widgets.self_absorption_dialog import SelfAbsorptionDialog
        dlg = SelfAbsorptionDialog(x[:n], y[:n], str(label), parent=self)
        # Modeless owned tool window: the parent remains usable, but owns lifetime.
        # Retain the Python wrapper until Qt destroys the window.
        windows = getattr(self, "_self_absorption_windows", None)
        if windows is None:
            windows = []
            self._self_absorption_windows = windows
        windows.append(dlg)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda _obj=None, d=dlg: self._remove_self_absorption_window(d))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _remove_self_absorption_window(self, dlg):
        windows = getattr(self, "_self_absorption_windows", None)
        if windows is not None:
            self._self_absorption_windows = [w for w in windows if w is not dlg]

