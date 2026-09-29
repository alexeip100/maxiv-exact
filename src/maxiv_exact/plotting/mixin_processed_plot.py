"""Phase 4: Processed plotting pipeline helpers.

This module contains the parts of the original PlottingMixin that primarily deal
with plotting in the *Processed Data* tab.

Group Auto BG helpers remain in the main plotting module for Phase 5; this mixin
calls those methods when group mode is active.
"""

from __future__ import annotations

import numpy as np

from ..data import lookup_energy
from .. import processing
from .. import hdf5_loading as h5load


class ProcessedPlotMixin:
    """Mixin implementing processed plotting and related helpers."""

    def _plot_multiple_no_bg(self):
        import numpy as np

        self.proc_ax.clear()
        for combined_label, y_data in (getattr(self, "plot_data", {}) or {}).items():
            if not self.raw_visibility.get(combined_label, True):
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
                x_data = lookup_energy(self, abs_path, parent, int(y_arr.size))
                x_arr = np.asarray(x_data, dtype=float).ravel()
            except Exception:
                continue
            if x_arr.size < 2:
                continue

            # Apply normalization
            try:
                processed_y = processing.apply_normalization(self, abs_path, parent, y_arr)
                processed_y = np.asarray(processed_y, dtype=float).ravel()
            except Exception:
                processed_y = y_arr

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
                    label=self.shorten_label(hdf5_path),
                    color=self._get_persistent_curve_color(combined_label),
                )
                line.dataset_key = combined_label
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

    def update_plot_processed(self):
        # Preserve existing behaviour by keeping the logic identical to the pre-split version.
        try:
            self.proc_ax.clear()
        except Exception:
            pass

        visible_curves = 0
        try:
            visible_curves = len([key for key in self.plot_data if self.raw_visibility.get(key, False)])
        except Exception:
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
                self._plot_multiple_with_group_auto_bg()
            except Exception as ex:
                print("Group Auto BG plotting failed:", ex)
                self._plot_multiple_no_bg()
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
            return

        main_x, main_y = self.compute_main_curve()
        if main_x is not None and main_y is not None:
            self.proc_ax.plot(main_x, main_y, label="Main curve")

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
            self._show_subtracted_only(mode, main_x, main_y)

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

    def _apply_normalization(self, abs_path, parent, y_data):
        """Divide by the chosen I0 channel – open file briefly (non-locking)."""
        try:
            normalize = bool(self.chk_normalize.isChecked())
        except Exception:
            normalize = False
        if normalize:
            parent = self._coerce_hdf5_relative_path(parent, abs_path=abs_path)
            norm_channel = self._coerce_hdf5_relative_path(self.combo_norm.currentText(), abs_path=abs_path)
            if not norm_channel:
                return y_data
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
                                return y_data.copy()
                            safe = np.divide(
                                y_data,
                                norm_data,
                                out=np.zeros_like(y_data, dtype=float),
                                where=norm_data != 0,
                            )
                            return safe
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
        return y_data

    def _apply_automatic_bg_new(self, main_x, main_y, deg=None, pre_edge_percent=None, ax=None, do_plot=True):
        # (unchanged algorithm, but made robust and self-contained)
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
            return np.zeros_like(main_y, dtype=float)

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
            return background

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

        return background
