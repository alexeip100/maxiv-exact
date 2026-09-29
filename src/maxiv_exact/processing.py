"""Processing mixin for the EXACT X-ray absorption viewer.

This module contains the ProcessingMixin and a few small helper functions.
"""

from .data import lookup_energy

# --- / Normalisation helper (module-level wrapper for backward compatibility)
from .qt_helpers import is_checked_state

def apply_normalization(viewer, abs_path, parent, y_data):
    """Apply I0 normalisation for a given spectrum.

    Parts of the codebase call a module-level ``processing.apply_normalization``.
    The actual implementation lives on the main window instance as
    ``_apply_normalization`` (defined in plotting.py).

    This wrapper delegates to that method if present, otherwise returns the
    input unchanged.
    """
    try:
        fn = getattr(viewer, "_apply_normalization", None)
        if callable(fn):
            return fn(abs_path, parent, y_data)
    except Exception:
        pass
    return y_data


import numpy as np
from .compat import trapezoid
import matplotlib.pyplot as plt
plt.ioff()
import re

def _proc_safe_post_normalize(viewer, x, y, mode):
    """Module-level wrapper used across the codebase for post-normalization.

    Delegates to ``viewer._safe_post_normalize`` (method on ProcessingMixin),
    falling back to a minimal safe implementation if that method is unavailable.

    Parameters
    ----------
    viewer : object
        The main HDF5Viewer instance (inherits ProcessingMixin).
    x, y : array-like
        Data arrays.
    mode : str
        One of: "None", "Max", "Jump", "Area".

    Returns
    -------
    np.ndarray
        Post-normalized y (or unchanged if not applicable).
    """
    import numpy as np

# Preferred path: use the mixin method (keeps behavior consistent everywhere).
    try:
        fn = getattr(viewer, "_safe_post_normalize", None)
        if callable(fn):
            return fn(x, y, mode)
    except Exception:
        pass

# Fallback: minimal robust implementation.
    if mode is None or mode == "None":
        return y
    x = np.asarray(x)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if not np.any(m):
        return y
    xf = x[m]
    yf = y[m]
    def _nonzero(v):
        return np.isfinite(v) and abs(v) > 1e-30
    try:
        if mode == "Max":
            d = float(np.max(np.abs(yf)))
            return y / d if _nonzero(d) else y
        if mode == "Jump":
            d = float(yf[-1])
            return y / d if _nonzero(d) else y
        if mode == "Area":
            a = float(trapezoid(yf, xf))
            return y / a if _nonzero(a) else y
    except Exception:
        return y
    return y

class ProcessingMixin:
    def _proc_robust_polyfit_on_normalized(self, xs, ys, deg, x_eval):
        import numpy as np
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        x_eval = np.asarray(x_eval, dtype=float)
        m = np.isfinite(xs) & np.isfinite(ys)
        if not np.any(m):
            return np.zeros_like(x_eval, dtype=float), np.array([], dtype=float)
        xs = xs[m]; ys = ys[m]
        n = xs.size
        try:
            deg_eff = int(deg)
        except Exception:
            deg_eff = 2
        deg_eff = max(1, min(deg_eff, max(1, n - 1)))
        x_min = float(np.nanmin(xs)); x_max = float(np.nanmax(xs))
        if not np.isfinite(x_min) or not np.isfinite(x_max) or x_max <= x_min:
            x0, span = 0.0, 1.0
        else:
            x0 = 0.5 * (x_min + x_max)
            span = x_max - x_min
            if not np.isfinite(span) or span == 0.0:
                span = 1.0
        xp = 2.0 * (xs - x0) / span
        xp_eval = 2.0 * (x_eval - x0) / span
        try:
            p = np.polyfit(xp, ys, deg_eff)
            bg = np.polyval(p, xp_eval)
        except Exception:
            p = np.array([], dtype=float)
            bg = np.zeros_like(x_eval, dtype=float)
        return bg, p

    def recompute_waterfall_layout(self):
        """(Re)apply Waterfall (Uniform step) based on the checkbox + slider/spin."""
        enabled = False
        try:
            enabled = bool(getattr(self, 'waterfall_checkbox', None) and self.waterfall_checkbox.isChecked())
        except Exception:
            enabled = False

        # Enable/disable controls
        try:
            self.waterfall_slider.setEnabled(enabled)
            self.waterfall_spin.setEnabled(enabled)
        except Exception:
            pass

        if not enabled:
            try:
                self.restore_original_line_data()
                self.rescale_plotted_axes()
                if hasattr(self, 'canvas_plotted'):
                    self.canvas_plotted.draw()
            except Exception:
                pass
            return

        # Delegate to apply_waterfall_shift (Uniform step only)
        try:
            self.apply_waterfall_shift()
        except Exception as ex:
            print('apply_waterfall_shift error:', ex)
    def reset_manual_mode(self):
        self.manual_mode = False
        self.manual_points = []
        self.manual_bg_line = None
        self.manual_poly = None
        self.manual_poly_degree = None
        self.last_sum_state = False
        self.last_normalize_state = False
        self.last_plot_len = 0

    def _compute_background(self, main_x, main_y):
        mode = self.combo_bg.currentText()
        deg = int(self.combo_poly.currentText())
        if mode == "None":
            return np.zeros_like(main_y)
        elif mode == "Manual" and self.manual_points:
            try:
                xs = [pt["x"] for pt in self.manual_points]
                ys = [pt["y"] for pt in self.manual_points]
                background, _ = self._proc_robust_polyfit_on_normalized(xs, ys, deg, main_x)
                background[0] = main_y[0]
            except Exception as ex:
                print("Error in manual background computation:", ex)
                background = np.zeros_like(main_y)
            return background
        elif str(mode) in ("Automatic", "Auto"):
            return self._apply_automatic_bg_new( main_x, main_y, do_plot=False)
        return np.zeros_like(main_y)

    def compute_main_curve(self):
        if self.chk_sum.isChecked():
            sum_y, x_ref = None, None
            for combined_label, y_data in self.plot_data.items():
                if not self.raw_visibility.get(combined_label, True):
                    continue
                parts = combined_label.split("##", 1)
                if len(parts) != 2:
                    continue
                abs_path, hdf5_path = parts
                parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                x_data = lookup_energy(self, abs_path, parent, len(y_data))
                processed_y = apply_normalization(self, abs_path, parent, y_data)
                if sum_y is None:
                    sum_y = processed_y.copy()
                    x_ref = x_data
                else:
                    m = min(len(sum_y), len(processed_y))
                    sum_y = sum_y[:m] + processed_y[:m]
                    x_ref = x_ref[:m]
            return x_ref, sum_y
        else:
            for combined_label, y_data in self.plot_data.items():
                if not self.raw_visibility.get(combined_label, True):
                    continue
                parts = combined_label.split("##", 1)
                if len(parts) == 2:
                    abs_path, hdf5_path = parts
                    parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                    return (
                        lookup_energy(self, abs_path, parent, len(y_data)),
                        apply_normalization(self, abs_path, parent, y_data),
                    )
        return None, None

    def _safe_post_normalize(self, x, y, mode):
        """Robust post-normalization on finite data.
        mode: "None" | "Max" | "Jump" | "Area"
        Returns a *copy* of y if scaled, or original y if not applicable.
        """
        import numpy as np
        if mode is None or mode == "None":
            return y
        x = np.asarray(x); y = np.asarray(y, dtype=float)
        mfin = np.isfinite(x) & np.isfinite(y)
        if not np.any(mfin):
            return y
        xf = x[mfin]; yf = y[mfin]
        def _nonzero(val, eps=1e-15):
            return (val is not None) and np.isfinite(val) and (abs(val) > eps)
        try:
            if mode == "Max":
                d = float(np.max(np.abs(yf)))
                if _nonzero(d): return y / d
            elif mode == "Jump":
                d = float(yf[-1])
                if _nonzero(d): return y / d
            elif mode == "Area":
                a = float(trapezoid(yf, xf))
                if _nonzero(a): return y / a
        except Exception as ex:
            print("safe_post_norm error:", ex)
        return y

    def _on_normalize_toggled(self, state):
        self.combo_norm.setEnabled(is_checked_state(state))
        self.update_plot_processed()

    def _on_sum_toggled(self, state):
        """Handle the "Sum up" checkbox.

        If the user attempts to sum curves from more than one energy region,
        show an explicit OK/Cancel warning. We still allow it (sometimes useful
        for nearly identical regions with a few missing points), but we want the
        intent to be explicit.
        """
        try:
            if is_checked_state(state):
                # Determine how many distinct energy regions are currently visible.
                regions = set()
                visible = 0
                plot_data = getattr(self, "plot_data", {}) or {}
                raw_vis = getattr(self, "raw_visibility", {}) or {}
                for combined_label in plot_data.keys():
                    if not raw_vis.get(combined_label, True):
                        continue
                    parts = str(combined_label).split("##", 1)
                    if len(parts) != 2:
                        continue
                    abs_path, hdf5_path = parts
                    parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                    regions.add(f"{abs_path}::{parent}")
                    visible += 1

                if visible > 1 and len(regions) > 1:
                    from PyQt6.QtWidgets import QMessageBox, QDialog
                    ret = QMessageBox.question(
                        self,
                        "Sum across regions?",
                        "You selected spectra from multiple energy regions.\n"
                        "Summing them may be meaningless unless the regions overlap.\n\n"
                        "Do you want to continue?",
                        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel,
                    )
                    if ret != QMessageBox.StandardButton.Ok:
                        # Revert without retriggering this handler.
                        try:
                            self.chk_sum.blockSignals(True)
                            self.chk_sum.setChecked(False)
                        finally:
                            self.chk_sum.blockSignals(False)
                        return
        except Exception:
            # Never block plotting due to warning logic.
            pass

        self.update_plot_processed()

# ---
    # Advanced curve summation (materialises summed curves)
    # ------------------------------------------------------------------
    def _extract_entry_number_for_key(self, key: str):
        """Try to extract an entry number (int) from a dataset key."""
        try:
            parts = str(key).split("##", 1)
            if len(parts) != 2:
                return None
            _abs, hdf5_path = parts
            seg = str(hdf5_path).lstrip("/").split("/", 1)[0]
            m = re.search(r"entry\s*(\d+)", seg, flags=re.IGNORECASE)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return None

    def _auto_sum_name(self, keys):
        """Generate a compact default name for a group of curves.

        Preference: entry number ranges -> 'entry8428–8430 (n=3)'
        Fallback: '<first>…<last> (n=...)'
        """
        try:
            keys = list(keys or [])
            n = len(keys)
            if n <= 0:
                return "Sum"

            nums = []
            for k in keys:
                v = self._extract_entry_number_for_key(k)
                if v is None:
                    nums = []
                    break
                nums.append(int(v))

            if nums:
                nums = sorted(set(nums))
                # Build contiguous runs
                runs = []
                a = b = nums[0]
                for x in nums[1:]:
                    if x == b + 1:
                        b = x
                    else:
                        runs.append((a, b))
                        a = b = x
                runs.append((a, b))

                def fmt_run(r):
                    a, b = r
                    return f"{a}–{b}" if a != b else f"{a}"

                body = ",".join(fmt_run(r) for r in runs)
                name = f"entry{body} (n={n})"
                # Keep it reasonably short
                if len(name) > 48:
                    name = f"entry{nums[0]}–{nums[-1]} (n={n})"
                return name

            # Fallback using stable display labels (do NOT use custom legend labels).
            # Custom labels are for plot legends only; dialogs should show the
            # underlying dataset/curve names so the user can always identify
            # what is being summed.
            def disp(k):
                try:
                    parts = str(k).split("##", 1)
                    return str(parts[1]) if len(parts) == 2 else str(k)
                except Exception:
                    return str(k)

            first = disp(keys[0])
            last = disp(keys[-1])
            return f"{first}…{last} (n={n})"
        except Exception:
            return "Sum"

    def open_curve_summation_dialog(self):
        """Open the Curve summation dialog and create summed curves."""
        try:
            plot_data = getattr(self, "plot_data", {}) or {}
            raw_vis = getattr(self, "raw_visibility", {}) or {}
            keys = [k for k in plot_data.keys() if raw_vis.get(k, False)]
        except Exception:
            keys = []

        from PyQt6.QtWidgets import QMessageBox, QDialog
        if len(keys) < 1:
            QMessageBox.information(self, "Curve summation", "Select (check) at least one curve.")
            return

        # Build display names.
        # NOTE: Use only stable dataset-derived labels here (not custom legend
        # labels). Otherwise, editing the user-defined legend would rename items
        # in the summation dialog, which is confusing.
        curves = []
        for k in keys:
            try:
                parts = str(k).split("##", 1)
                disp = (
                    self.shorten_label(parts[1])
                    if (len(parts) == 2 and hasattr(self, "shorten_label"))
                    else (parts[1] if len(parts) == 2 else str(k))
                )
            except Exception:
                disp = str(k)
            curves.append((k, disp))

        try:
            from .widgets.curve_summation_dialog import CurveSummationDialog
        except Exception:
            QMessageBox.warning(self, "Curve summation", "CurveSummationDialog could not be imported.")
            return

        default_name = self._auto_sum_name([k for k, _d in curves])
        dlg = CurveSummationDialog(curves, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        groups = dlg.get_groups()
        created = []
        for g in groups:
            try:
                gkeys = list(g.get("keys", []) or [])
                if len(gkeys) < 1:
                    continue
                gname = str(g.get("name") or "Sum").strip() or "Sum"
                sum_key = self._create_summed_curve(gkeys, gname)
                if sum_key:
                    created.append((sum_key, gkeys))
            except Exception:
                continue

        if not created:
            QMessageBox.information(self, "Curve summation", "No summed curves were created.")
            return

        # Default visibility: hide components, show sums
        try:
            for sum_key, src_keys in created:
                for sk in src_keys:
                    try:
                        self.raw_visibility[sk] = False
                    except Exception:
                        pass
                try:
                    self.raw_visibility[sum_key] = True
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.update_plot_processed()
        except Exception:
            pass
        try:
            self.update_plot_raw()
        except Exception:
            pass

    def _create_summed_curve(self, keys, name: str):
        """Create one synthetic summed curve from the given dataset keys.

        The new curve is stored in self.plot_data and uses a synthetic parent
        path "__SUM__/N" so that energy axes can be cached.

        Summation uses common overlap + interpolation. If I0 normalization is
        active, each component curve is normalized before interpolation.
        """
        import numpy as np

        keys = list(keys or [])
        if len(keys) < 1:
            return None

        # Choose an anchor file path for the synthetic key (needed for caches)
        abs_anchor = None
        parsed = []  # (abs_path, parent, y)
        for k in keys:
            parts = str(k).split("##", 1)
            if len(parts) != 2:
                continue
            abs_path, hdf5_path = parts
            parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
            y = (getattr(self, "plot_data", {}) or {}).get(k)
            if y is None:
                continue
            try:
                y = np.asarray(y, dtype=float).ravel()
            except Exception:
                continue
            if y.size < 2:
                continue
            if abs_anchor is None:
                abs_anchor = abs_path
            parsed.append((k, abs_path, parent, y))

        if abs_anchor is None or len(parsed) < 1:
            return None

        # Build (x, y) pairs (apply normalization per curve if enabled)
        xy = []
        for k, abs_path, parent, y in parsed:
            try:
                x = lookup_energy(self, abs_path, parent, int(y.size))
                x = np.asarray(x, dtype=float).ravel()
                n = int(min(x.size, y.size))
                if n < 2:
                    continue
                x = x[:n]
                yy = y[:n]
                # Apply I0 normalization if active (per-curve)
                try:
                    yy = apply_normalization(self, abs_path, parent, yy)
                    yy = np.asarray(yy, dtype=float).ravel()
                except Exception:
                    yy = np.asarray(yy, dtype=float).ravel()
                # Drop non-finite
                m = np.isfinite(x) & np.isfinite(yy)
                if np.count_nonzero(m) < 2:
                    continue
                x = x[m]
                yy = yy[m]
                # Ensure monotonic increasing x for np.interp
                order = np.argsort(x)
                x = x[order]
                yy = yy[order]
                # Remove duplicate x
                dx = np.diff(x)
                keep = np.ones_like(x, dtype=bool)
                keep[1:] = dx != 0
                x = x[keep]
                yy = yy[keep]
                if x.size < 2:
                    continue
                xy.append((x, yy))
            except Exception:
                continue

        if len(xy) < 1:
            return None

        # Common overlap
        lo = max(float(np.min(x)) for x, _y in xy)
        hi = min(float(np.max(x)) for x, _y in xy)
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None

        # Reference grid: longest curve segment within [lo, hi]
        best_x = None
        best_n = -1
        for x, _y in xy:
            m = (x >= lo) & (x <= hi)
            nn = int(np.count_nonzero(m))
            if nn > best_n:
                best_n = nn
                best_x = x[m]
        if best_x is None or best_x.size < 2:
            return None

        x_common = np.asarray(best_x, dtype=float).ravel()

        # Interpolate + sum
        y_sum = np.zeros_like(x_common, dtype=float)
        for x, y in xy:
            m = (x >= lo) & (x <= hi)
            x_use = x[m]
            y_use = y[m]
            if x_use.size < 2:
                continue
            try:
                y_i = np.interp(x_common, x_use, y_use)
            except Exception:
                continue
            y_sum = y_sum + y_i

        # Create synthetic key
        serial = int(getattr(self, "_sum_serial", 0) or 0) + 1
        try:
            setattr(self, "_sum_serial", serial)
        except Exception:
            pass
        parent_sum = f"__SUM__/{serial}"
        hdf5_path_sum = f"{parent_sum}/sum"
        sum_key = f"{abs_anchor}##{hdf5_path_sum}"

        # Store y and cache x for both cache key formats used in the codebase
        try:
            self.plot_data[sum_key] = np.asarray(y_sum, dtype=float)
        except Exception:
            return None
        try:
            # Energy caches (two different key formats are used in different parts of the app)
            if not hasattr(self, "energy_cache") or self.energy_cache is None:
                self.energy_cache = {}
            self.energy_cache[f"{abs_anchor}::{parent_sum}"] = (x_common, True)
            self.energy_cache[f"{abs_anchor}##{parent_sum}"] = (x_common, True)
        except Exception:
            pass

        # Provide a nice intrinsic label for Raw/Processed trees and the Plotted curve list.
        # IMPORTANT: Do NOT put this into `custom_labels`, because that mapping is reserved
        # for user-defined legend labels on the Plotted Data tab. Otherwise, renaming in the
        # Plotted legend would unexpectedly rename curves back in the Processed tab.
        try:
            if not hasattr(self, "curve_display_names") or self.curve_display_names is None:
                self.curve_display_names = {}
            self.curve_display_names[sum_key] = str(name)
        except Exception:
            pass

        # Remember metadata (optional)
        try:
            if not hasattr(self, "_summed_curve_sources") or self._summed_curve_sources is None:
                self._summed_curve_sources = {}
            self._summed_curve_sources[sum_key] = list(keys)
        except Exception:
            pass

        # Inherit region assignment from constituents (keep sums in the same Region)
        try:
            if not hasattr(self, "_region_overrides") or self._region_overrides is None:
                self._region_overrides = {}
            # Use the first constituent as the reference for region placement
            ref_key = keys[0] if keys else None
            if ref_key:
                try:
                    groups = self.group_datasets(include_sums=False)
                except Exception:
                    groups = []
                ref_group = None
                for g in groups or []:
                    try:
                        if ref_key in (g.get("keys") or []):
                            ref_group = g
                            break
                    except Exception:
                        continue
                if ref_group:
                    self._region_overrides[sum_key] = {
                        "start": float(ref_group.get("min")),
                        "end": float(ref_group.get("max")),
                        "label": str(ref_group.get("label") or ""),
                        "unfinished": bool(ref_group.get("unfinished", False)),
                    }
        except Exception:
            pass

        return sum_key

    def _on_bg_subtract_toggled(self, state):
        """Enable/disable post‑normalisation combo and update plot."""
        # In Group BG mode, post-normalisation is intentionally locked (Area) regardless of Subtract BG toggle.
        # Keep the widget state managed by Group BG logic; only replot here.
        try:
            cb = getattr(self, "chk_group_bg", None)
            if cb is not None and cb.isEnabled() and cb.isChecked():
                self.update_plot_processed()
                return
        except Exception:
            pass

        self.combo_post_norm.setEnabled(is_checked_state(state))
        self.update_plot_processed()

    def _robust_polyfit_on_normalized(self, xs, ys, deg, x_eval):
        """Stable polynomial fit for manual BG in normalized x ∈ [-1,1]."""
        import numpy as np
        xs = np.asarray(xs, dtype=float).ravel()
        ys = np.asarray(ys, dtype=float).ravel()
        x_eval = np.asarray(x_eval, dtype=float).ravel()
        m = np.isfinite(xs) & np.isfinite(ys)
        xs, ys = xs[m], ys[m]
        if xs.size == 0:
            return np.zeros_like(x_eval, dtype=float), np.array([0.0], dtype=float)
        n_uniq = np.unique(xs).size
        deg_eff = int(max(0, min(int(deg), max(0, n_uniq - 1))))
        x0 = float(xs.min()); x1 = float(xs.max())
        span = max(1e-12, x1 - x0)
        xp = 2.0 * (xs - x0) / span - 1.0
        xp_eval = 2.0 * (x_eval - x0) / span - 1.0
        p = np.polyfit(xp, ys, deg_eff)
        bg = np.polyval(p, xp_eval)
        return bg, p

    def _apply_manual_bg(self, main_x, main_y):
        import numpy as np
        if not getattr(self, "manual_points", None):
            return np.zeros_like(main_y)
        try:
            d = int(self.combo_poly.currentText())
        except Exception:
            d = 2
        xs = [pt["x"] for pt in self.manual_points]
        ys = [pt["y"] for pt in self.manual_points]
        background, coeffs = self._proc_robust_polyfit_on_normalized(xs, ys, d, main_x)
        if np.isfinite(main_y[0]):
            background[0] = main_y[0]
        self.manual_poly = coeffs

        # Draw anchors always
        for pt in self.manual_points:
            if pt.get("artist") is not None:
                try: pt["artist"].remove()
                except Exception: pass
                pt["artist"] = None
            marker, = self.proc_ax.plot(pt["x"], pt["y"], marker='o', linestyle='None', markersize=8, markerfacecolor='blue', markeredgecolor='blue', picker=5)
            pt["artist"] = marker

        # Show/hide red background line
        hide_bg = getattr(self, "chk_show_without_bg", None) is not None and self.chk_show_without_bg.isChecked()
        if hide_bg:
            if getattr(self, "manual_bg_line", None) is not None:
                try: self.manual_bg_line.remove()
                except Exception: pass
                self.manual_bg_line = None
        else:
            if getattr(self, "manual_bg_line", None) is not None and self.manual_bg_line.axes is self.proc_ax:
                try: self.manual_bg_line.remove()
                except Exception: pass
                self.manual_bg_line = None
            self.manual_bg_line, = self.proc_ax.plot(main_x, background, '--', color='red', label='Background')
        try:
            self.canvas_proc.draw_idle()
        except Exception:
            pass
        return background

    def _show_subtracted_only(self, mode, main_x, main_y):
        self.proc_ax.clear()
        self.manual_bg_line = None
        # compute background
        if str(mode) in ("Automatic", "Auto"):
            background = self._apply_automatic_bg_new( main_x, main_y, do_plot=False)
        elif mode == "Manual" and self.manual_points:
            try:
                d = int(self.combo_poly.currentText())
                xs = [pt["x"] for pt in self.manual_points]
                ys = [pt["y"] for pt in self.manual_points]
                background, _ = self._proc_robust_polyfit_on_normalized(xs, ys, d, main_x)
                background[0] = main_y[0]
            except Exception:
                background = np.zeros_like(main_y)
        else:
            background = np.zeros_like(main_y)

        sub = main_y - background

        # post-normalisation (robust)
        if self.combo_post_norm.isEnabled():
            mode_norm = self.combo_post_norm.currentText()
            sub = _proc_safe_post_normalize(self, main_x, sub, mode_norm)
        # finite-only plotting and autoscale
        _mplot = np.isfinite(sub) & np.isfinite(main_x)
        if not np.any(_mplot):
            self.proc_ax.set_xlabel("Photon energy (eV)")
            try:
                self.proc_ax.figure.canvas.draw_idle()
            except Exception:
                pass
            return


        self.proc_ax.plot(np.asarray(main_x)[_mplot], sub[_mplot], label="Background subtracted")
        try:
            self.proc_ax.relim(); self.proc_ax.autoscale_view(); self.proc_ax.figure.tight_layout(); self.canvas_proc.draw_idle()
        except Exception:
            pass
        self.proc_ax.set_xlabel("Photon energy (eV)")

    def init_manual_mode(self, main_x, main_y, auto_bg=None):
        """Prepare manual background mode: anchors + events.
        If auto_bg is None, compute a non-plotted automatic BG for seeding.
        """
        import numpy as np
        self.manual_mode = True
        self._drag_index = None
        self.manual_poly_degree = int(self.combo_poly.currentText())

        # Seed auto_bg if not provided
        if auto_bg is None:
            try:
                deg = int(self.combo_poly.currentText())
            except Exception:
                deg = 2
            try:
                pre = float(self.spin_preedge.value()) / 100.0
            except Exception:
                pre = 0.20
            auto_bg = self._apply_automatic_bg_new(
                main_x, main_y, deg=deg, pre_edge_percent=pre, ax=self.proc_ax, do_plot=False
            )

        # Initialize anchors if absent
        if not hasattr(self, "manual_points") or not self.manual_points:
            # Match the number of anchors to the selected polynomial degree.
            # A polynomial of degree d is defined by (at least) d+1 points.
            try:
                d = int(getattr(self, "manual_poly_degree", int(self.combo_poly.currentText())))
            except Exception:
                d = 3
            n_seed = max(1, d + 1)

            n = len(main_x)
            if n <= 0:
                idxs = np.array([], dtype=int)
            else:
                # Never create more anchors than we have samples.
                n_seed = min(n_seed, n)

                # Evenly distribute anchors across the available x-range.
                idxs = np.linspace(0, n - 1, n_seed)
                idxs = np.unique(np.clip(np.round(idxs).astype(int), 0, n - 1))

                # Guard against duplicate indices after rounding (e.g., when n_seed is close to n).
                # If we lost some anchors, add additional distinct indices to reach n_seed.
                if idxs.size < n_seed:
                    all_idx = np.arange(n, dtype=int)
                    remaining = np.setdiff1d(all_idx, idxs)
                    if remaining.size:
                        take = min(n_seed - idxs.size, remaining.size)
                        extra = remaining[np.clip(np.round(np.linspace(0, remaining.size - 1, take)).astype(int), 0, remaining.size - 1)]
                        idxs = np.sort(np.concatenate([idxs, extra]))

            self.manual_points = [{"x": float(main_x[i]), "y": float(auto_bg[i]), "artist": None} for i in idxs]

        for pt in self.manual_points:
            art = pt.get("artist")
            if art is not None:
                try: art.remove()
                except Exception: pass
            pt["artist"] = None

        # Draw blue, pickable anchors (always visible)
        for pt in self.manual_points:
            (ln,) = self.proc_ax.plot([pt["x"]], [pt["y"]], marker="o", markersize=7,
                                      mfc="#66b3ff", mec="k", linestyle="None", zorder=6, label="_manual_anchor")
            try: ln.set_picker(5)
            except Exception: pass
            pt["artist"] = ln

        # Draw initial manual BG = auto BG (red dashed). Visibility is handled elsewhere.
        if getattr(self, "manual_bg_line", None) is not None:
            try: self.manual_bg_line.remove()
            except Exception: pass
            self.manual_bg_line = None
        self.manual_bg_line, = self.proc_ax.plot(main_x, auto_bg, "--", color="red", label="Background")

        # Connect events
        canvas = self.proc_ax.figure.canvas
        if not hasattr(self, "_mpl_cids"):
            self._mpl_cids = {}
        for key in ("press", "motion", "release"):
            cid = self._mpl_cids.get(key)
            if cid is not None:
                try: canvas.mpl_disconnect(cid)
                except Exception: pass
        self._mpl_cids["press"] = canvas.mpl_connect("button_press_event", self.on_press)
        self._mpl_cids["motion"] = canvas.mpl_connect("motion_notify_event", self.on_motion)
        self._mpl_cids["release"] = canvas.mpl_connect("button_release_event", self.on_release)

        try:
            canvas.draw_idle()
        except Exception:
            pass

    def on_press(self, event):
        import numpy as np
        # Manual BG anchor dragging (only when Manual BG mode is active)
        try:
            mode = self.combo_bg.currentText()
        except Exception:
            mode = "None"
        if mode == "Manual" and getattr(self, "manual_mode", False):
            if getattr(event, "button", None) != 1:
                return
            if event.inaxes is not getattr(self, "proc_ax", None):
                return
            if not getattr(self, "manual_points", None):
                return
            # Cache current y-limits to keep scale stable while dragging
            try:
                self._drag_ylim = tuple(self.proc_ax.get_ylim())
            except Exception:
                self._drag_ylim = None

            xs = np.array([pt["x"] for pt in self.manual_points], dtype=float)
            ys = np.array([pt["y"] for pt in self.manual_points], dtype=float)
            if not len(xs) or event.x is None or event.y is None:
                return
            trans = self.proc_ax.transData
            pts_display = trans.transform(np.column_stack([xs, ys]))
            click = np.array([event.x, event.y], dtype=float)
            d2 = np.sum((pts_display - click) ** 2, axis=1)
            i_min = int(np.argmin(d2))
            if d2[i_min] <= 10.0 ** 2:
                self._drag_index = i_min
            else:
                self._drag_index = None
            return

        # Automatic BG pre-edge marker dragging (mirrors the robust, pixel-space hit-test used above)
        try:
            if getattr(event, "button", None) != 1:
                return
            # NOTE: Unlike manual-anchor dragging we do *not* hard-require
            # event.inaxes == proc_ax. With recent Matplotlib/Qt (incl. HiDPI),
            # clicks on a Line2D artist can occasionally arrive with inaxes=None
            # even though the click is visually inside the axes.
            if getattr(self, "proc_ax", None) is None:
                return
            combo = getattr(self, "combo_bg", None)
            if combo is None or combo.currentText() not in ("Automatic", "Auto"):
                return
            ln = getattr(self, "proc_preedge_line", None)
            if ln is None:
                return
            if event.x is None:
                return

            # Get current line x-position
            try:
                xline = float(np.asarray(ln.get_xdata(), dtype=float)[0])
            except Exception:
                return

            # Compute pixel distance from click to vertical line (use y-mid of current axes limits)
            # Compare in display (pixel) coordinates.
            try:
                y0, y1 = self.proc_ax.get_ylim()
                ymid_data = 0.5 * (float(y0) + float(y1))
            except Exception:
                ymid_data = 0.0
            try:
                xpix, _ypix = self.proc_ax.transData.transform((xline, ymid_data))
            except Exception:
                return

            # Generous tolerance in pixels for easy grabbing.
            if abs(float(event.x) - float(xpix)) <= 25.0:
                self._dragging_preedge = True
                self._drag_index = None
        except Exception:
            return
    def on_motion(self, event):
        import numpy as np
        # Manual BG anchor dragging (only when Manual BG mode is active)
        try:
            mode = self.combo_bg.currentText()
        except Exception:
            mode = "None"
        if mode == "Manual" and getattr(self, "manual_mode", False):
            i = getattr(self, "_drag_index", None)
            if i is None:
                return
            if event.inaxes is not getattr(self, "proc_ax", None):
                return
            if (event.xdata is None or not np.isfinite(event.xdata) or
                    event.ydata is None or not np.isfinite(event.ydata)):
                return
            try:
                x_new = float(event.xdata)
                y_new = float(event.ydata)
            except Exception:
                return
            # Update both X and Y of the active manual background anchor
            self.manual_points[i]["x"] = x_new
            self.manual_points[i]["y"] = y_new
            art = self.manual_points[i].get("artist")
            if art is not None:
                try:
                    art.set_data([x_new], [y_new])
                except Exception:
                    pass
            xs = np.array([pt["x"] for pt in self.manual_points], dtype=float)
            ys = np.array([pt["y"] for pt in self.manual_points], dtype=float)
            try:
                deg = int(self.combo_poly.currentText())
            except Exception:
                deg = 2
            x_grid = None
            if getattr(self, "manual_bg_line", None) is not None:
                try:
                    x_grid = np.asarray(self.manual_bg_line.get_xdata(), dtype=float)
                except Exception:
                    x_grid = None
            if x_grid is None or x_grid.size == 0:
                lines = [ln for ln in self.proc_ax.get_lines() if ln is not getattr(self, "manual_bg_line", None)]
                for ln in lines:
                    xd = ln.get_xdata()
                    if xd is not None and len(xd):
                        x_grid = np.asarray(xd, dtype=float)
                        break
            if x_grid is None or x_grid.size == 0:
                x_min = np.nanmin(xs) if np.isfinite(xs).any() else 0.0
                x_max = np.nanmax(xs) if np.isfinite(xs).any() else 1.0
                if not np.isfinite(x_min) or not np.isfinite(x_max) or x_max <= x_min:
                    x_min, x_max = 0.0, 1.0
                x_grid = np.linspace(x_min, x_max, 512)
            try:
                bg, coeffs = self._proc_robust_polyfit_on_normalized(xs, ys, deg, x_grid)
                self.manual_poly = coeffs
            except Exception:
                try: self.proc_ax.figure.canvas.draw_idle()
                except Exception: pass
                return
            if bg.size and ys.size and np.isfinite(ys[0]):
                bg[0] = ys[0]
            m = np.isfinite(x_grid) & np.isfinite(bg)
            x_plot = x_grid[m] if np.any(m) else np.array([], dtype=float)
            y_plot = bg[m]      if np.any(m) else np.array([], dtype=float)
            if getattr(self, "manual_bg_line", None) is None:
                if x_plot.size and y_plot.size:
                    try:
                        (self.manual_bg_line,) = self.proc_ax.plot(x_plot, y_plot, "--", color="red", label="Background")
                    except Exception:
                        self.manual_bg_line = None
            else:
                if x_plot.size and y_plot.size:
                    try:
                        self.manual_bg_line.set_data(x_plot, y_plot)
                    except Exception:
                        try: self.manual_bg_line.remove()
                        except Exception: pass
                        self.manual_bg_line = None
                        try:
                            (self.manual_bg_line,) = self.proc_ax.plot(x_plot, y_plot, "--", color="red", label="Background")
                        except Exception:
                            self.manual_bg_line = None
            ys_fin = ys[np.isfinite(ys)]
            y_candidates = []
            if y_plot.size: y_candidates.append(y_plot)
            if ys_fin.size: y_candidates.append(ys_fin)
            if y_candidates:
                all_y = np.concatenate(y_candidates)
                if all_y.size:
                    y_min = float(np.nanmin(all_y)); y_max = float(np.nanmax(all_y))
                    if np.isfinite(y_min) and np.isfinite(y_max):
                        # Compute a padded target box from current content
                        if y_max <= y_min:
                            pad_content = max(1e-6, abs(y_max) * 0.05 + 1e-6)
                        else:
                            pad_content = 0.05 * (y_max - y_min)
                        target_low  = y_min - pad_content
                        target_high = y_max + pad_content

                        # During drag, only EXPAND y-limits (no sudden zoom-in)
                        curr_low, curr_high = None, None
                        if hasattr(self, "_drag_ylim") and isinstance(self._drag_ylim, tuple):
                            curr_low, curr_high = self._drag_ylim
                        else:
                            try:
                                curr_low, curr_high = self.proc_ax.get_ylim()
                            except Exception:
                                pass

                        if curr_low is not None and curr_high is not None:
                            new_low  = min(curr_low, target_low)
                            new_high = max(curr_high, target_high)
                        else:
                            new_low, new_high = target_low, target_high

                        # Set limits; guard against identical bounds
                        if np.isfinite(new_low) and np.isfinite(new_high):
                            if new_high <= new_low:
                                new_high = new_low + 1.0
                            try:
                                self.proc_ax.set_ylim(new_low, new_high)
                            except Exception:
                                pass

            try: self.proc_ax.figure.canvas.draw_idle()
            except Exception: pass
            return

        # Automatic BG pre-edge marker dragging
        if not getattr(self, "_dragging_preedge", False):
            return
        if event is None:
            return
        if getattr(self, "proc_ax", None) is None:
            return
        if event.x is None:
            return

        # Determine xdata robustly.
        # Prefer event.xdata, but fall back to pixel->data conversion using the
        # vertical center of the axes (does not depend on event.y/inaxes).
        xdata = getattr(event, "xdata", None)
        if xdata is None or (not np.isfinite(xdata)):
            try:
                bbox = self.proc_ax.bbox
                ypix_mid = 0.5 * (float(bbox.y0) + float(bbox.y1))
                xdata = float(self.proc_ax.transData.inverted().transform((float(event.x), ypix_mid))[0])
            except Exception:
                return
        try:
            xdata = float(xdata)
        except Exception:
            return

        x = getattr(self, "_proc_last_x", None)
        if x is None:
            return
        try:
            x = np.asarray(x, dtype=float)
        except Exception:
            return
        if x.size < 2:
            return

        # Map x-position to nearest data index, then to the integer pre-edge percentage.
        # IMPORTANT: spin_preedge is a QSpinBox (integer). If we move the line continuously
        # but only update the spinbox in 1% steps, the line will "jump back" on redraw.
        # Therefore we SNAP the marker to the same 1% grid during dragging.
        try:
            idx_hit = int(np.argmin(np.abs(x - xdata)))
        except Exception:
            return
        idx_hit = max(1, min(idx_hit, int(x.size - 1)))
        denom = float(max(1, int(x.size - 1)))
        pre_percent_int = int(round(100.0 * float(idx_hit) / denom))
        pre_percent_int = max(1, min(pre_percent_int, 99))
        idx = int(round((float(pre_percent_int) / 100.0) * denom))
        idx = max(1, min(idx, int(x.size - 1)))
        self._preedge_drag_percent_int = pre_percent_int

        # Update UI value without recursive signal storms
        spin = getattr(self, "spin_preedge", None)
        if spin is not None:
            try:
                spin.blockSignals(True)
                spin.setValue(int(pre_percent_int))
                spin.blockSignals(False)
            except Exception:
                try:
                    spin.blockSignals(False)
                except Exception:
                    pass

        # Update line position immediately (plot update will also redraw it)
        try:
            ln = getattr(self, "proc_preedge_line", None)
            if ln is not None:
                x0 = float(x[idx])
                ln.set_xdata([x0, x0])
        except Exception:
            pass
        # During dragging we only move the marker line and update the pre-edge % widget.
        # Recomputing the full processed plot on every mouse-move can recreate artists and
        # interrupt dragging (especially on recent Matplotlib/Qt backends). We therefore
        # recompute once on mouse-release.
        try:
            self.canvas_proc.draw_idle()
        except Exception:
            pass
    def on_release(self, event):
        # Finish automatic BG pre-edge marker drag
        if getattr(self, "_dragging_preedge", False):
            if getattr(event, "button", None) == 1:
                self._dragging_preedge = False
                # Ensure the spinbox reflects the final dragged value (QSpinBox => int)
                spin = getattr(self, "spin_preedge", None)
                if spin is not None:
                    try:
                        v = getattr(self, "_preedge_drag_percent_int", None)
                        if v is not None:
                            spin.blockSignals(True)
                            spin.setValue(int(v))
                            spin.blockSignals(False)
                        else:
                            spin.blockSignals(False)
                    except Exception:
                        pass
                # Recompute processed plot once at the end of dragging
                try:
                    if hasattr(self, "update_plot_processed"):
                        self.update_plot_processed()
                except Exception:
                    pass
                try:
                    self.canvas_proc.draw_idle()
                except Exception:
                    pass
            return

        # Manual BG anchor drag end (only when Manual BG mode is active)
        try:
            mode = self.combo_bg.currentText()
        except Exception:
            mode = "None"
        if mode == "Manual" and getattr(self, "manual_mode", False):
            if getattr(event, "button", None) != 1:
                return
            self._drag_index = None
            # Restore autoscale after drag ends (smoothly)
            try:
                self.proc_ax.relim()
                self.proc_ax.autoscale_view()
                self.proc_ax.figure.canvas.draw_idle()
            except Exception:
                pass
            # clear cached limits
            self._drag_ylim = None

            return

        # Pre-edge marker drag end
        try:
            if getattr(event, "button", None) != 1:
                return
        except Exception:
            pass
        try:
            self._dragging_preedge = False
        except Exception:
            pass
