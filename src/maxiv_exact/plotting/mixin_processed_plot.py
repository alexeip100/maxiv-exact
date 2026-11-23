"""Phase 4: Processed plotting pipeline helpers.

This module contains the parts of the original PlottingMixin that primarily deal
with plotting in the *Processed Data* tab.

Group Auto BG helpers remain in the main plotting module for Phase 5; this mixin
calls those methods when group mode is active.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from ..data import lookup_energy
from ..hdf5_curve_type import is_processed_xas_path, paired_raw_axis
from ..nexafs_fit.group import GROUP_REQUIRED
from .. import processing
from .. import hdf5_loading as h5load


class ProcessedPlotMixin:
    """Mixin implementing processed plotting and related helpers."""

    def _is_reference_spectrum(self, key):
        """Recognize selectable X–Y spectra with a validated photon-energy axis."""
        if "##" not in str(key):
            return False
        source, path = key.split("##", 1)
        if path.rsplit("/", 1)[-1] != "y":
            return False
        signal = self.plot_data.get(key)
        if signal is None:
            return False
        try:
            with self._open_h5_read(source) as file:
                pair = paired_raw_axis(file, path, len(signal))
            return pair is not None and pair[1] == "Photon energy (eV)"
        except (OSError, KeyError, TypeError, ValueError, RuntimeError):
            return False

    def _plot_multiple_no_bg(self):
        import numpy as np

        self.proc_ax.clear()
        for combined_label, y_data in (getattr(self, "plot_data", {}) or {}).items():
            if (not self.raw_visibility.get(combined_label, True)
                    or combined_label in getattr(self, "_difference_sources", {})):
                continue
            parts = str(combined_label).split("##", 1)
            if len(parts) != 2:
                continue
            abs_path, hdf5_path = parts
            parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""

            # Robustly coerce y to 1D numeric array
            try:
                y_arr = np.asarray(y_data, dtype=float).ravel()
            except Exception:
                continue
            if y_arr.size < 2:
                continue

            # Robustly get x
            try:
                x_data = lookup_energy(self, abs_path, parent, int(y_arr.size), dataset_key=combined_label)
                x_arr = np.asarray(x_data, dtype=float).ravel()
            except Exception:
                continue
            if x_arr.size < 2:
                continue

            # Apply normalization
            try:
                processed_y, normalized = processing.apply_normalization(self, abs_path, parent, y_arr, report=True)
                processed_y = np.asarray(processed_y, dtype=float).ravel()
            except Exception:
                processed_y = y_arr
                normalized = False

            mlen = int(min(x_arr.size, processed_y.size))
            if mlen < 2:
                continue

            x_use = x_arr[:mlen]
            y_use = processed_y[:mlen]
            if x_use.size < 2:
                continue

            try:
                line, = self.proc_ax.plot(
                    x_use,
                    y_use,
                    label=getattr(self, "_raw_pair_names", {}).get(combined_label)
                    or self.shorten_label(hdf5_path),
                    color=self._get_persistent_curve_color(combined_label),
                )
                line.dataset_key = combined_label
                line.processing_state = self._spectrum_processing_state(normalized)
            except Exception:
                continue

        self.proc_ax.set_xlabel("Photon energy (eV)")

    def _visible_processed_keys(self):
        """Return list of dataset keys currently visible (checked) in the Processed Data tree."""
        try:
            return [k for k in getattr(self, "plot_data", {}) if getattr(self, "raw_visibility", {}).get(k, False)]
        except Exception:
            return []

    def _get_drawn_processed_xy(self, key):
        """Return (x,y) arrays for the curve *as currently drawn* on the Processed axes.

        This is used to ensure "Pass to Plotted" uses exactly the same data the user sees
        (especially in Group BG mode). Returns (None, None) if not found.
        """
        try:
            ax = getattr(self, "proc_ax", None)
            if ax is None:
                return None, None
            for line in ax.get_lines():
                if getattr(line, "dataset_key", None) == key and str(getattr(line, "get_label", lambda: "")()) != "_bg":
                    x = np.asarray(line.get_xdata(), dtype=float).ravel()
                    y = np.asarray(line.get_ydata(), dtype=float).ravel()
                    if x.size == 0 or y.size == 0:
                        return None, None
                    mlen = int(min(x.size, y.size))
                    return x[:mlen], y[:mlen]
        except Exception:
            return None, None
        return None, None

    def _drawn_spectra(self):
        """Only checked spectrum artists, excluding backgrounds and previews."""
        checked = set(self._visible_processed_keys())
        return {line.dataset_key: line for line in self.proc_ax.lines
                if line.get_visible() and getattr(line, "dataset_key", None) in checked}

    def _group_bg_is_active(self):
        checkbox = getattr(self, "chk_group_bg", None)
        return bool(checkbox is not None and checkbox.isEnabled() and checkbox.isChecked())

    def _update_spectra_actions(self):
        if hasattr(self, "spectra_button"):
            count = len(self._drawn_spectra())
            self.sum_spectra_action.setEnabled(count > 0)
            self.calibrate_energy_action.setEnabled(count > 0 and not self._group_bg_is_active())
            self.subtract_spectra_action.setEnabled(count >= 2)

    def _spectra_dialog_inputs(self):
        spectra = {}
        for key, line in self._drawn_spectra().items():
            source_file, path = key.split("##", 1)
            label = (self.curve_display_names.get(key)
                     or getattr(self, "_raw_pair_names", {}).get(key) or self.shorten_label(path))
            _, has_energy = lookup_energy(self, source_file, path.rpartition("/")[0],
                                          len(self.plot_data[key]), report=True)
            spectra[key] = label, line, has_energy
        return spectra

    @staticmethod
    def _distinct_spectrum_labels(spectra):
        labels = Counter(label for label, *_ in spectra.values())
        source_names = Counter(Path(source).name for source in {
            key.split("##", 1)[0] for key in spectra
        })
        result = {}
        for key, (label, *data) in spectra.items():
            if labels[label] > 1:
                source, dataset = key.split("##", 1)
                filename = Path(source).name
                label = f"{label} · {filename if source_names[filename] == 1 else source} · {dataset}"
            result[key] = label, *data
        return result

    def open_energy_calibration_dialog(self):
        from PyQt6.QtWidgets import QDialog
        from ..widgets.spectra_dialogs import EnergyCalibrationDialog

        if self._group_bg_is_active():
            return
        spectra = self._spectra_dialog_inputs()
        if not spectra:
            return
        dialog = EnergyCalibrationDialog(self, {
            key: (label, line, self._energy_shifts.get(key, 0.0), has_energy)
            for key, (label, line, has_energy) in self._distinct_spectrum_labels(spectra).items()
        })
        self._spectra_preview_dialog = dialog
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._spectra_preview_dialog = None
        shifts = dialog.shifts()
        dialog.deleteLater()
        if not accepted or self._group_bg_is_active():
            return
        changed = {key: shift for key, shift in shifts.items()
                   if shift != self._energy_shifts.get(key, 0.0)}
        if not changed:
            return
        # Shift manual background anchors with their spectrum so the existing
        # background and corrected intensities translate together.
        sources = [key for key in spectra if key not in self._difference_sources]
        if self.manual_mode and len(sources) == 1:
            key = sources[0]
            if key in changed:
                delta = changed[key] - self._energy_shifts.get(key, 0.0)
                for point in self.manual_points:
                    point["x"] += delta
        limits = self.proc_ax.get_xlim(), self.proc_ax.get_ylim()
        auto_x, auto_y = self.proc_ax.get_autoscalex_on(), self.proc_ax.get_autoscaley_on()
        for key, shift in changed.items():
            if shift:
                self._energy_shifts[key] = shift
            else:
                self._energy_shifts.pop(key, None)
        self.update_plot_raw()
        self.update_plot_processed()
        self.proc_ax.set_xlim(limits[0], auto=auto_x)
        self.proc_ax.set_ylim(limits[1], auto=auto_y)
        self.canvas_proc.draw_idle()

    def open_spectrum_subtraction_dialog(self):
        from PyQt6.QtWidgets import QDialog
        from ..widgets.spectra_dialogs import SpectrumSubtractionDialog

        spectra = self._spectra_dialog_inputs()
        if len(spectra) < 2:
            return
        states = [getattr(line, "processing_state", {}) for _, line, _ in spectra.values()]
        if any(state.get("group_bg") for state in states):
            state = "Group BG with subtraction" if self.chk_show_without_bg.isChecked() else "Group BG with backgrounds shown"
        elif any(state.get("i0_applied") for state in states):
            state = "I₀-normalized where available"
        else:
            state = "No I₀ normalization applied"
        if any(item.get("snapshot") for item in states):
            state += " · saved differences use snapshot data"
        dialog = SpectrumSubtractionDialog(self, self._distinct_spectrum_labels(spectra), state)
        self._spectra_preview_dialog = dialog
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._spectra_preview_dialog = None
        if accepted:
            ref = dialog.reference.currentData()
            reference = self._difference_input_info(ref, spectra)
            mode = dialog.mode.currentText()
            multiplier = dialog.multiplier.value()
            for key, (x, y) in dialog.results.items():
                self._add_difference_snapshot(x, y, self._difference_input_info(key, spectra),
                                              reference, mode, multiplier)
            self.update_plot_raw()
            self.update_plot_processed()
        dialog.deleteLater()

    def _difference_input_info(self, key, spectra):
        label, line, _ = spectra[key]
        source_file, dataset = key.split("##", 1)
        state = dict(line.processing_state)
        if "group_inputs" in state:
            state["group_inputs"] = {
                member: self._energy_shifts.get(member, 0.0) for member in state["group_inputs"]
            }
        prior = self._difference_sources.get(key)
        return dict(key=key, name=label, source_file=None if prior else source_file,
                    dataset=dataset, shift=self._energy_shifts.get(key, 0.0),
                    processing=state, difference=prior,
                    summed_inputs=tuple(getattr(self, "_summed_curve_sources", {}).get(key, ())))

    def _add_difference_snapshot(self, x, y, sample, reference, mode, multiplier):
        names = set(self.curve_display_names.values())
        while True:
            self._difference_serial += 1
            serial = self._difference_serial
            name = f"Diff {serial}: {sample['name']} − {reference['name']}"
            if name not in names:
                break
        # A synthetic source keeps snapshots independent of closing source files.
        source, parent = "__DIFF__", f"__DIFF__/{serial}"
        key = f"{source}##{parent}/difference"
        self.plot_data[key] = y
        self.energy_cache[f"{source}::{parent}"] = (x, True)
        self.raw_visibility[key] = True
        self.curve_display_names[key] = name
        if not hasattr(self, "_region_overrides"):
            self._region_overrides = {}
        self._region_overrides[key] = {"start": float(x.min()), "end": float(x.max())}
        self._difference_sources[key] = dict(
            sample=sample, reference=reference, mode=mode, multiplier=multiplier,
            operation="Sample − k × Reference", interpolation="linear within overlap",
        )

    def _spectrum_processing_state(self, normalized, *, background="None", subtracted=False,
                                   post_normalization="None", group_bg=False, **details):
        return dict(
            i0_channel=self.combo_norm.currentText() if self.chk_normalize.isChecked() else None,
            i0_applied=bool(self.chk_normalize.isChecked() and normalized),
            group_bg=group_bg, background=background, background_subtracted=subtracted,
            post_normalization=post_normalization, **details,
        )

    def _plot_difference_snapshots(self):
        for key in self._visible_processed_keys():
            if key not in getattr(self, "_difference_sources", {}):
                continue
            abs_path, path = key.split("##", 1)
            y = self.plot_data[key]
            x = lookup_energy(self, abs_path, path.rsplit("/", 1)[0], len(y), dataset_key=key)
            line, = self.proc_ax.plot(x, y, label=self.curve_display_names[key],
                                      color=self._get_persistent_curve_color(key))
            line.dataset_key = key
            line.processing_state = {"snapshot": True}

    def _set_nexafs_group(self, group=None, reason=GROUP_REQUIRED):
        self._nexafs_group = group
        button = getattr(self, "nexafs_fit_button", None)
        if button is not None:
            button.setEnabled(group is not None)
            button.setToolTip(reason if group is None else "Open the captured Group BG spectra.")

    def update_plot_processed(self):
        dialog = getattr(self, "_spectra_preview_dialog", None)
        if dialog is not None and dialog.isVisible():
            dialog.reject()
        self._refresh_processed_plot()
        self._update_spectra_actions()

    def _refresh_processed_plot(self):
        self._set_nexafs_group()
        # Keep the isolated self-absorption launcher in sync with Processed Data state.
        try:
            if hasattr(self, "update_self_absorption_action_state"):
                self.update_self_absorption_action_state()
        except Exception:
            pass
        # Generic 1D HDF5 metadata are available only in the Raw Data viewer.
        # Never reinterpret their indices as photon energies for XAS processing.
        if any("##" in str(key) and not is_processed_xas_path(str(key).split("##", 1)[1])
               and not self._is_reference_spectrum(key)
               for key in getattr(self, "plot_data", {})
               if getattr(self, "raw_visibility", {}).get(key, False)):
            try:
                self.proc_ax.clear()
                self.canvas_proc.draw()
            except Exception:
                pass
            try:
                self.update_pass_button_state()
            except Exception:
                pass
            return
        # Preserve existing behaviour by keeping the logic identical to the pre-split version.
        try:
            self.proc_ax.clear()
        except Exception:
            pass

        visible_curves = 0
        try:
            source_keys = [key for key in self._visible_processed_keys()
                           if key not in getattr(self, "_difference_sources", {})]
            visible_curves = len(source_keys)
        except Exception:
            source_keys = []
            visible_curves = 0

        # Determine background mode from UI
        try:
            mode = self.combo_bg.currentText() if hasattr(self, "combo_bg") else "None"
        except Exception:
            mode = "None"

                # Update Group BG / Match pre-edge checkbox availability based on selection and BG mode.
        try:
            if hasattr(self, "_update_group_bg_checkbox_state"):
                self._update_group_bg_checkbox_state(visible_curves, mode)
        except Exception:
            pass
        try:
            if hasattr(self, "_update_group_bg_slope_checkbox_state"):
                self._update_group_bg_slope_checkbox_state(visible_curves, mode)
        except Exception:
            pass

# If the user has enabled Group BG, enforce the required settings even if
        # other UI flows had previously disabled those widgets.
        try:
            gcb = getattr(self, "chk_group_bg", None)
            if gcb is not None and gcb.isEnabled() and gcb.isChecked():
                self._set_group_bg_mode(True)
                mode = self.combo_bg.currentText() if hasattr(self, "combo_bg") else mode
        except Exception:
            pass

        group_active = False
        try:
            if visible_curves > 1 and (not self.chk_sum.isChecked()) and str(mode) in ("Automatic", "Auto"):
                cb = getattr(self, "chk_group_bg", None)
                if cb is not None and cb.isEnabled() and cb.isChecked():
                    group_active = True
        except Exception:
            group_active = False

        if visible_curves > 1 and not self.chk_sum.isChecked() and not group_active:
            # Default behaviour: multiple curves without sum -> show only normalized curves, no BG controls.
            self._toggle_bg_widgets(False)
            self._plot_multiple_no_bg()
            self._plot_difference_snapshots()
            self.proc_ax.figure.tight_layout()
            self.canvas_proc.draw()
            self.update_pass_button_state()
            self.update_proc_tree()
            return
        else:
            self._toggle_bg_widgets(True)

        # Group automatic background mode for multiple selected curves
        if group_active:
            try:
                group, reason = self._plot_multiple_with_group_auto_bg()
            except Exception as ex:
                print("Group Auto BG plotting failed:", ex)
                self._plot_multiple_no_bg()
                group, reason = None, "Group BG processing failed for the current selection."
            self._plot_difference_snapshots()
            try:
                self._draw_preedge_vline(getattr(self, "_proc_last_x", None))
            except Exception:
                pass
            self.proc_ax.set_xlabel("Photon energy (eV)")
            try:
                self.proc_ax.figure.tight_layout()
            except Exception:
                pass
            try:
                self.canvas_proc.draw()
            except Exception:
                pass
            self.update_pass_button_state()
            self.update_proc_tree()
            self._set_nexafs_group(group, reason)
            return

        main_line = None
        normalized = False
        if self.chk_sum.isChecked():
            main_x, main_y = self.compute_main_curve()
        elif source_keys:
            main_x, main_y, normalized = self.compute_main_curve(dataset_key=source_keys[0], report=True)
        else:
            main_x, main_y = None, None
        if main_x is not None and main_y is not None:
            main_line, = self.proc_ax.plot(main_x, main_y, label="Main curve")

        new_sum_state = self.chk_sum.isChecked()
        new_norm_state = self.chk_normalize.isChecked()
        new_len = len(main_y) if main_y is not None else 0
        mode = self.combo_bg.currentText()

        # Exit manual mode when switching away
        if mode != "Manual" and getattr(self, "manual_mode", False):
            self.reset_manual_mode()

        if mode == "Manual" and main_y is not None:
            if (
                (not self.manual_mode)
                or self.manual_poly_degree is None
                or (self.manual_poly_degree != int(self.combo_poly.currentText()))
                or (new_sum_state != self.last_sum_state)
                or (new_norm_state != self.last_normalize_state)
                or (new_len != self.last_plot_len)
            ):
                self.reset_manual_mode()
                self.init_manual_mode(main_x, main_y)

        self.last_sum_state = new_sum_state
        self.last_normalize_state = new_norm_state
        self.last_plot_len = new_len

        if str(mode) in ("Automatic", "Auto") and main_x is not None and main_y is not None:
            self.spin_preedge.setEnabled(True)
            self._apply_automatic_bg_new(
                main_x,
                main_y,
                deg=int(self.combo_poly.currentText()),
                pre_edge_percent=float(self.spin_preedge.value()) / 100.0,
                ax=self.proc_ax,
                do_plot=True,
            )
            self.reset_manual_mode()
            if self.manual_bg_line is not None:
                self.manual_bg_line.remove()
                self.manual_bg_line = None
        elif mode == "Manual" and main_x is not None and main_y is not None:
            self.spin_preedge.setEnabled(False)
            self._apply_manual_bg(main_x, main_y)
        else:
            self.spin_preedge.setEnabled(True)
            self.reset_manual_mode()
            if self.manual_bg_line is not None:
                self.manual_bg_line.remove()
                self.manual_bg_line = None

        if self.chk_show_without_bg.isChecked() and main_x is not None and main_y is not None:
            main_line = self._show_subtracted_only(mode, main_x, main_y)

        if main_line is not None and len(source_keys) == 1:
            main_line.dataset_key = source_keys[0]
            subtracted = self.chk_show_without_bg.isChecked()
            main_line.processing_state = self._spectrum_processing_state(
                normalized, background=mode, subtracted=subtracted,
                post_normalization=self.combo_post_norm.currentText()
                if subtracted and self.combo_post_norm.isEnabled() else "None",
                polynomial_degree=self.combo_poly.currentText(),
                pre_edge_percent=self.spin_preedge.value(),
                manual_anchors=[(p["x"], p["y"]) for p in self.manual_points] if mode == "Manual" else [],
            )

        self._plot_difference_snapshots()

        try:
            if str(mode) in ("Automatic", "Auto") and main_x is not None:
                self._proc_last_x = np.asarray(main_x)
                self._draw_preedge_vline(self._proc_last_x)
        except Exception:
            pass

        self.proc_ax.set_xlabel("Photon energy (eV)")
        self.proc_ax.figure.tight_layout()
        self.canvas_proc.draw()
        self.update_pass_button_state()
        self.update_proc_tree()

    def _toggle_bg_widgets(self, enabled: bool):
        """Enable/disable BG-related widgets for the Processed Data panel."""
        group_locked = False
        try:
            gcb = getattr(self, "chk_group_bg", None)
            group_locked = bool(gcb is not None and gcb.isChecked())
        except Exception:
            group_locked = False

        try:
            self.combo_bg.setEnabled(bool(enabled) and (not group_locked))
        except Exception:
            pass
        try:
            self.combo_poly.setEnabled(bool(enabled))
        except Exception:
            pass
        try:
            self.spin_preedge.setEnabled(bool(enabled))
        except Exception:
            pass
        try:
            self.chk_show_without_bg.setEnabled(bool(enabled))
        except Exception:
            pass

    def _lookup_energy(self, abs_path, parent, length):
        if length < 1:
            return np.array([])
        if abs_path not in self.hdf5_files:
            return np.arange(length)

        cache_key = f"{abs_path}##{parent}"
        if cache_key in self.energy_cache:
            x_data, _ = self.energy_cache[cache_key]
            return x_data if x_data is not None else np.arange(length)

        x_data = None
        try:
            with self._open_h5_read(abs_path) as f:
                if parent:
                    pcap = f"{parent}/pcap_energy_av"
                    mono = f"{parent}/mono_traj_energy"
                    if pcap in f:
                        x_data = f[pcap][()]
                    elif mono in f:
                        x_data = f[mono][()]
        except Exception:
            x_data = None

        if x_data is None:
            x_data = np.arange(length)
        self.energy_cache[cache_key] = (x_data, False)
        return x_data

    def _coerce_hdf5_relative_path(self, value, abs_path=None):
        """Return a safe HDF5 relative path string from legacy/tree payloads."""
        return h5load.normalize_hdf5_path(
            value,
            known_file_paths=getattr(self, "hdf5_files", {}) or {},
            abs_path=abs_path,
            strip_outer_slashes=True,
        )

    def _apply_normalization(self, abs_path, parent, y_data, *, report=False):
        """Divide by the chosen I0 channel, optionally reporting completion."""
        try:
            normalize = bool(self.chk_normalize.isChecked())
        except Exception:
            normalize = False
        if normalize:
            parent = self._coerce_hdf5_relative_path(parent, abs_path=abs_path)
            norm_channel = self._coerce_hdf5_relative_path(self.combo_norm.currentText(), abs_path=abs_path)
            if not norm_channel:
                return (y_data, False) if report else y_data
            norm_path = f"{parent}/{norm_channel}" if parent else norm_channel
            norm_path = self._coerce_hdf5_relative_path(norm_path, abs_path=abs_path)
            try:
                with self._open_h5_read(abs_path) as f:
                    obj = f.get(norm_path, None)
                    # If the resolved path points to a group, do not index it with
                    # [()]. That h5py access produces the misleading tuple error
                    # reported during refresh. Just leave the spectrum unchanged.
                    try:
                        import h5py as _h5py
                        is_dataset = isinstance(obj, _h5py.Dataset)
                    except Exception:
                        is_dataset = hasattr(obj, "shape") and hasattr(obj, "__getitem__")
                    if is_dataset:
                        try:
                            norm_data = obj[()]
                            if getattr(norm_data, "size", 0) == 0 or getattr(y_data, "size", 0) == 0:
                                copied = y_data.copy()
                                return (copied, False) if report else copied
                            safe = np.divide(
                                y_data,
                                norm_data,
                                out=np.zeros_like(y_data, dtype=float),
                                where=norm_data != 0,
                            )
                            return (safe, True) if report else safe
                        except Exception as ex:
                            # Avoid one console line per curve when the same problem repeats.
                            err_key = (str(abs_path), str(norm_path), str(ex))
                            seen = getattr(self, "_normalization_error_keys", set())
                            if err_key not in seen:
                                print("Normalisation error:", ex)
                                try:
                                    seen.add(err_key)
                                    self._normalization_error_keys = seen
                                except Exception:
                                    pass
            except Exception as ex:
                err_key = (str(abs_path), str(norm_path), str(ex))
                seen = getattr(self, "_normalization_error_keys", set())
                if err_key not in seen:
                    print("Normalisation error:", ex)
                    try:
                        seen.add(err_key)
                        self._normalization_error_keys = seen
                    except Exception:
                        pass
        return (y_data, not normalize) if report else y_data

    def _apply_automatic_bg_new(
        self, main_x, main_y, deg=None, pre_edge_percent=None, ax=None, do_plot=True, *, report=False
    ):
        """Fit automatic BG, optionally reporting whether the primary fit succeeded."""
        import numpy as np

        if deg is None:
            try:
                deg = int(self.combo_poly.currentText())
            except Exception:
                try:
                    deg = int(self.bg_poly_degree_spinbox.value())
                except Exception:
                    deg = 2
        if pre_edge_percent is None:
            try:
                pre_edge_percent = float(self.spin_preedge.value()) / 100.0
            except Exception:
                try:
                    pre_edge_percent = float(self.pre_edge_spinbox.value()) / 100.0
                except Exception:
                    pre_edge_percent = 0.20
        if ax is None:
            for name in ("proc_ax", "ax_processed", "ax_proc", "ax2", "ax"):
                if hasattr(self, name):
                    cand = getattr(self, name)
                    if hasattr(cand, "plot"):
                        ax = cand
                        break

        main_x = np.asarray(main_x, dtype=float).ravel()
        main_y = np.asarray(main_y, dtype=float).ravel()
        N = len(main_x)
        if N == 0 or N != len(main_y):
            background = np.zeros_like(main_y, dtype=float)
            return (background, False) if report else background

        finite = np.isfinite(main_x) & np.isfinite(main_y)
        x_all = main_x[finite]
        y_all = main_y[finite]
        Nf = len(x_all)
        if Nf < 3:
            background = np.zeros_like(main_y, dtype=float)
            if N > 0 and np.isfinite(main_y[0]):
                background[0] = main_y[0]
            if do_plot and ax is not None:
                if hasattr(self, "_auto_bg_vline") and getattr(self._auto_bg_vline, "axes", None) is ax:
                    try:
                        self._auto_bg_vline.remove()
                    except Exception:
                        pass
                self._auto_bg_vline = None
                if hasattr(self, "_auto_bg_line") and getattr(self._auto_bg_line, "axes", None) is ax:
                    try:
                        self._auto_bg_line.remove()
                    except Exception:
                        pass
                self._auto_bg_line = None
            return (background, False) if report else background

        idx_end_finite = max(1, int(pre_edge_percent * Nf))
        idx_end_finite = min(idx_end_finite, Nf - 1)
        M = idx_end_finite

        deg_eff = int(max(0, deg))
        deg_eff = min(deg_eff, max(0, min(M, Nf) - 1))

        x_min = float(x_all[0])
        x_max = float(x_all[-1])
        span = x_max - x_min
        if span <= 0:
            span = 1.0

        x_prime = 2.0 * (x_all - x_min) / span - 1.0
        x_pre = x_prime[:M]
        y_pre = y_all[:M]
        x_end_prime = x_prime[-1]

        i_start = max(M + 1, int(0.95 * Nf))
        if i_start >= Nf - 1:
            i_start = max(Nf - 2, 0)
        x_tail = x_all[i_start:]
        y_tail = y_all[i_start:]
        if len(x_tail) >= 2:
            slope_final, _ = np.polyfit(x_tail, y_tail, 1)
        else:
            slope_final = 0.0
        slope_prime = slope_final * (span / 2.0)

        A = np.zeros((M, deg_eff + 1), dtype=float)
        for i in range(M):
            A[i, :] = np.array([x_pre[i] ** (deg_eff - k) for k in range(deg_eff + 1)], dtype=float)
        b = y_pre.copy()

        deriv_row = np.zeros(deg_eff + 1, dtype=float)
        for k in range(deg_eff + 1):
            power = deg_eff - k
            if power > 0:
                deriv_row[k] = power * (x_end_prime ** (power - 1))

        row_norms = np.linalg.norm(A, axis=1)
        w = np.nanmedian(row_norms) if row_norms.size else 1.0
        if not np.isfinite(w) or w <= 0:
            w = 1.0
        A2 = np.vstack([A, w * deriv_row[None, :]])
        b2 = np.concatenate([b, [w * slope_prime]])

        success = True
        try:
            coeffs, *_ = np.linalg.lstsq(A2, b2, rcond=None)
            if not np.all(np.isfinite(coeffs)):
                raise np.linalg.LinAlgError("Non-finite coefficients")
            x_prime_full = 2.0 * (main_x - x_min) / span - 1.0
            background = np.zeros_like(main_y, dtype=float)
            for i in range(N):
                xx = x_prime_full[i]
                val = 0.0
                for kk in range(deg_eff + 1):
                    power = deg_eff - kk
                    val += coeffs[kk] * (xx ** power)
                background[i] = val
        except Exception as ex:
            success = False
            print("Automatic BG (constrained) failed -> fallback:", ex)
            idx_end_plot = max(1, int(pre_edge_percent * N))
            idx_end_plot = min(idx_end_plot, N - 1)
            x_fit = main_x[:idx_end_plot]
            y_fit = main_y[:idx_end_plot]
            msk = np.isfinite(x_fit) & np.isfinite(y_fit)
            x_fit = x_fit[msk]
            y_fit = y_fit[msk]
            if len(x_fit) == 0:
                background = np.zeros_like(main_y)
            else:
                x0 = float(x_fit[0])
                x1 = float(x_fit[-1])
                span_fb = max(1.0, x1 - x0)
                xp = 2.0 * (x_fit - x0) / span_fb - 1.0
                deg_fb = min(int(deg), max(0, len(xp) - 1))
                p = np.polyfit(xp, y_fit, deg_fb)
                xp_full = 2.0 * (main_x - x0) / span_fb - 1.0
                background = np.polyval(p, xp_full)

        if np.isfinite(main_y[0]):
            background[0] = main_y[0]

        if do_plot and ax is not None:
            idx_end_plot = max(1, int(pre_edge_percent * N))
            idx_end_plot = min(idx_end_plot, N - 1)

            def _alive(artist):
                return (artist is not None) and (getattr(artist, "axes", None) is ax)

            if not hasattr(self, "_auto_bg_vline"):
                self._auto_bg_vline = None
            if not hasattr(self, "_auto_bg_line"):
                self._auto_bg_line = None

            if not _alive(self._auto_bg_vline):
                try:
                    self._auto_bg_vline = ax.axvline(
                        main_x[idx_end_plot],
                        linestyle="--",
                        linewidth=1.0,
                        alpha=0.6,
                        label="_auto_preedge",
                    )
                except Exception:
                    self._auto_bg_vline = None
            else:
                try:
                    x0 = main_x[idx_end_plot]
                    self._auto_bg_vline.set_xdata([x0, x0])
                except Exception:
                    self._auto_bg_vline = None

            if not _alive(self._auto_bg_line):
                try:
                    (self._auto_bg_line,) = ax.plot(main_x, background, linestyle="--", linewidth=1.5, label="_auto_bg")
                except Exception:
                    self._auto_bg_line = None
            else:
                try:
                    self._auto_bg_line.set_data(main_x, background)
                except Exception:
                    self._auto_bg_line = None
            try:
                ax.figure.canvas.draw_idle()
            except Exception:
                pass

        return (background, success) if report else background
