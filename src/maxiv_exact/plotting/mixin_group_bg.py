# Group background / match pre-edge slope support (Phase 5 split) / Extracted from maxiv_exact.plotting.PlottingMixin to reduce module size and co...

import numpy as np
from PyQt6.QtCore import Qt

from ..compat import trapezoid
from ..data import lookup_energy
from .. import processing


from ..qt_helpers import is_checked_state

class GroupBackgroundMixin:
    def _on_group_bg_checkbox_toggled(self, state):
        """Handle Group BG toggle.

        New UX (v2.1.1+):
        - The checkbox becomes *checkable* as soon as >=2 curves are selected.
        - When checked by the user, Group BG *forces* the required math settings:
          BG mode = Automatic, Subtract BG = ON, Post-normalization = Area.
        - While Group BG stays checked, BG mode and Area post-normalization stay fixed
          (controls are locked).
        """
        checked = False
        try:
            checked = is_checked_state(state)
        except Exception:
            checked = bool(state)

# Remember user's choice (only meaningful while in multi-selection)
        try:
            self._group_bg_user_choice = bool(checked)
        except Exception:
            pass

# Enter/exit Group BG mode (force/restore UI + processing settings)
        try:
            self._set_group_bg_mode(bool(checked))
        except Exception:
# If anything goes wrong, still attempt a redraw.
            pass

        try:
            self.update_plot_processed()
        except Exception:
            pass

    def _set_group_bg_mode(self, enabled: bool):
        """Force (or restore) processing controls for Group BG mode.

        When enabled, the required settings are applied and controls are locked:
        - BG mode: Automatic
        - Subtract BG: checked
        - Post-normalization: Area

        When disabled, previously stored user settings (if available) are restored.
        """
# Lazy-import Qt safely (already imported at module top in most builds)
        try:
            _QtChecked = Qt.CheckState.Checked
        except Exception:
            _QtChecked = 2

        cb = getattr(self, "chk_group_bg", None)
        if cb is None:
            return

        if enabled:
# Save previous settings once
            if getattr(self, "_group_bg_prev_settings", None) is None:
                prev = {}
                try:
                    prev["bg_text"] = str(self.combo_bg.currentText())
                    prev["bg_enabled"] = bool(self.combo_bg.isEnabled())
                except Exception:
                    prev["bg_text"] = "None"
                    prev["bg_enabled"] = True
                try:
                    prev["subtract"] = bool(self.chk_show_without_bg.isChecked())
                    prev["subtract_enabled"] = bool(self.chk_show_without_bg.isEnabled())
                except Exception:
                    prev["subtract"] = False
                    prev["subtract_enabled"] = True
                try:
                    prev["post_norm_text"] = str(self.combo_post_norm.currentText())
                    prev["post_norm_enabled"] = bool(self.combo_post_norm.isEnabled())
                except Exception:
                    prev["post_norm_text"] = "None"
                    prev["post_norm_enabled"] = False
                self._group_bg_prev_settings = prev

# Allow the user to toggle "Subtract BG" for visual inspection in Group BG mode. / We only auto-check it the first time Group BG is enabled; afterwar...
            try:
                first_enable = not bool(getattr(self, "_group_bg_mode_active", False))
                self._group_bg_mode_active = True
            except Exception:
                first_enable = True

# Force required settings without triggering cascaded updates
            try:
                self.combo_bg.blockSignals(True)
                self.chk_show_without_bg.blockSignals(True)
                self.combo_post_norm.blockSignals(True)
            except Exception:
                pass
            try:
# BG mode -> Automatic
                try:
                    idx = int(self.combo_bg.findText("Auto"))
                    if idx >= 0:
                        self.combo_bg.setCurrentIndex(idx)
                    else:
                        self.combo_bg.setCurrentText("Auto")
                except Exception:
                    pass

# Subtract BG -> ON (only on first enable)
                if "first_enable" in locals() and first_enable:
                    try:
                        self.chk_show_without_bg.setChecked(True)
                    except Exception:
                        pass

# Post-norm -> Area
                try:
                    idxn = int(self.combo_post_norm.findText("Area"))
                    if idxn >= 0:
                        self.combo_post_norm.setCurrentIndex(idxn)
                    else:
                        self.combo_post_norm.setCurrentText("Area")
                except Exception:
                    pass
            finally:
                try:
                    self.combo_bg.blockSignals(False)
                    self.chk_show_without_bg.blockSignals(False)
                    self.combo_post_norm.blockSignals(False)
                except Exception:
                    pass

# Lock controls that must stay fixed in Group BG mode
            try:
                self.combo_bg.setEnabled(False)
            except Exception:
                pass
            try:
                self.chk_show_without_bg.setEnabled(True)  # keep enabled for visual inspection in Group BG mode
            except Exception:
                pass
            try:
                self.combo_post_norm.setEnabled(False)
            except Exception:
                pass

        else:
# Restore previous settings (if we have them)
            prev = getattr(self, "_group_bg_prev_settings", None)

# Unlock first, then restore values, then restore enabled states.
            try:
                self.combo_bg.setEnabled(True)
            except Exception:
                pass
            try:
                self.chk_show_without_bg.setEnabled(True)
            except Exception:
                pass
            try:
                self.combo_post_norm.setEnabled(True)
            except Exception:
                pass

            if prev:
                try:
                    self.combo_bg.blockSignals(True)
                    self.chk_show_without_bg.blockSignals(True)
                    self.combo_post_norm.blockSignals(True)
                except Exception:
                    pass
                try:
# BG mode
                    try:
                        txt = str(prev.get("bg_text", "None"))
                        idx = int(self.combo_bg.findText(txt))
                        if idx >= 0:
                            self.combo_bg.setCurrentIndex(idx)
                        else:
                            self.combo_bg.setCurrentText(txt)
                    except Exception:
                        pass

# Subtract BG
                    try:
                        self.chk_show_without_bg.setChecked(bool(prev.get("subtract", False)))
                    except Exception:
                        pass

# Post-norm
                    try:
                        txtn = str(prev.get("post_norm_text", "None"))
                        idxn = int(self.combo_post_norm.findText(txtn))
                        if idxn >= 0:
                            self.combo_post_norm.setCurrentIndex(idxn)
                        else:
                            self.combo_post_norm.setCurrentText(txtn)
                    except Exception:
                        pass
                finally:
                    try:
                        self.combo_bg.blockSignals(False)
                        self.chk_show_without_bg.blockSignals(False)
                        self.combo_post_norm.blockSignals(False)
                    except Exception:
                        pass

# Restore enabled states (post-norm enable depends on subtract in normal mode, / so we restore exactly what the user had before entering Group BG).
                try:
                    self.combo_bg.setEnabled(bool(prev.get("bg_enabled", True)))
                except Exception:
                    pass
                try:
                    self.chk_show_without_bg.setEnabled(bool(prev.get("subtract_enabled", True)))
                except Exception:
                    pass
                try:
                    self.combo_post_norm.setEnabled(bool(prev.get("post_norm_enabled", False)))
                except Exception:
                    pass

# Mark Group BG as inactive so Subtract BG can be user-toggled on next activation.
            try:
                self._group_bg_mode_active = False
            except Exception:
                pass

            try:
                self._group_bg_prev_settings = None
            except Exception:
                self._group_bg_prev_settings = None

    def _on_group_bg_slope_checkbox_toggled(self, state):
        """Remember user choice for group pre-edge slope matching and update the processed plot."""
        try:
            self._group_bg_slope_user_choice = is_checked_state(state)
        except Exception:
            pass
        try:
            self.update_plot_processed()
        except Exception:
            pass

    def _update_group_bg_checkbox_state(self, visible_curves: int, mode_text: str):
        """Enable/disable the Group BG checkbox.

        UX goals (2025-12):
        - The checkbox is *checkable* whenever >=2 curves are selected, regardless of current BG/Norm settings.
        - It is NOT auto-checked. Group BG must be an explicit user choice.
        - When selection drops back to 0/1, Group BG is turned off and the checkbox is disabled.

        Math logic is enforced elsewhere:
        - When the user checks Group BG, we force: Automatic BG + Subtract BG + Area normalization
          and lock these controls while Group BG stays checked.
        """
        cb = getattr(self, "chk_group_bg", None)
        if cb is None:
            return
        # Track transitions into/out of multi-selection
        prev_multi = bool(getattr(self, "_group_bg_prev_multi", False))
        multi_now = (int(visible_curves) >= 2)

        if not multi_now:
            # Leaving multi-selection: ensure we exit Group BG mode cleanly.
            try:
                if cb.isChecked():
                    # Avoid recursion via the checkbox signal.
                    try:
                        cb.blockSignals(True)
                        cb.setChecked(False)
                    finally:
                        try:
                            cb.blockSignals(False)
                        except Exception:
                            pass
                    try:
                        self._set_group_bg_mode(False)
                    except Exception:
                        pass
            except Exception:
                pass

            # Reset remembered choice
            try:
                setattr(self, "_group_bg_user_choice", None)
            except Exception:
                pass

            try:
                cb.setEnabled(False)
            except Exception:
                pass
        else:
            # Entering / staying in multi-selection: checkbox is always available.
            try:
                cb.setEnabled(True)
            except Exception:
                pass

            # Do NOT auto-check when transitioning from 1 -> 2+. Keep unchecked unless the user ticks it.
            if (not prev_multi) and multi_now:
                try:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                finally:
                    try:
                        cb.blockSignals(False)
                    except Exception:
                        pass
                try:
                    setattr(self, "_group_bg_user_choice", False)
                except Exception:
                    pass

        try:
            setattr(self, "_group_bg_prev_multi", bool(multi_now))
        except Exception:
            pass

        # Keep the related 'Match pre-edge slope' checkbox in sync
        try:
            self._update_group_bg_slope_checkbox_state(visible_curves=int(visible_curves), mode_text=str(mode_text))
        except Exception:
            pass

    def _update_group_bg_slope_checkbox_state(self, visible_curves: int, mode_text: str):
        """Enable/disable the 'Match pre-edge slope' checkbox.

        This option is only meaningful when:
        - BG mode is Automatic
        - >=2 curves are selected
        - Group background checkbox is enabled & checked

        Default is OFF (unchecked). If the user manually toggles it while in multi-selection,
        keep their choice until selection drops back to 0/1.
        """
        cb = getattr(self, "chk_group_bg_slope", None)
        if cb is None:
            return

        try:
            mode = str(mode_text or "")
        except Exception:
            mode = ""

        # Determine whether group BG is currently usable/active
        group_cb = getattr(self, "chk_group_bg", None)
        group_ok = bool(group_cb is not None and group_cb.isEnabled() and group_cb.isChecked())

        prev_multi = bool(getattr(self, "_group_bg_slope_prev_multi", False))
        user_choice = getattr(self, "_group_bg_slope_user_choice", None)

        multi_now = (int(visible_curves) >= 2)
        usable_now = multi_now and (str(mode) in ("Automatic", "Auto")) and group_ok

        if not multi_now:
            user_choice = None
            try:
                setattr(self, "_group_bg_slope_user_choice", None)
            except Exception:
                pass

        try:
            cb.blockSignals(True)
            cb.setEnabled(bool(usable_now))
            if not usable_now:
                cb.setChecked(False)
            else:
                # Default is OFF when entering multi-selection.
                if (not prev_multi) and multi_now and user_choice is None:
                    cb.setChecked(False)
                    setattr(self, "_group_bg_slope_user_choice", False)
                elif user_choice is not None:
                    cb.setChecked(bool(user_choice))
        finally:
            try:
                cb.blockSignals(False)
            except Exception:
                pass

        try:
            setattr(self, "_group_bg_slope_prev_multi", bool(multi_now))
        except Exception:
            pass

    def _compute_group_auto_backgrounds(self, keys, deg: int, pre_edge_percent: float):
        """Compute *per-spectrum* automatic backgrounds for a group.

        This helper exists mainly for the multi-curve "group BG" plotting path.
        It intentionally does **not** force a strictly shared background shape.
        Instead, it computes the same per-spectrum Automatic BG as in the single
        spectrum workflow (using :meth:`_apply_automatic_bg_new` with
        ``do_plot=False``).

        Returns:
            (x_common, backgrounds_dict)
            - x_common is returned only if all curves share the same energy grid.
              Otherwise it is ``None``.
            - backgrounds_dict maps each dataset key to its background array.
        """
        import numpy as np

        if not keys:
            return None, None

        x_list = []
        bgs = {}

        for key in keys:
            parts = key.split("##", 1)
            if len(parts) != 2:
                continue
            abs_path, hdf5_path = parts
            parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
            y_data = self.plot_data.get(key)
            if y_data is None:
                continue
            try:
                y_arr = np.asarray(y_data, dtype=float).ravel()
            except Exception:
                continue
            if y_arr.size < 2:
                continue
            x_data = lookup_energy(self, abs_path, parent, int(y_arr.size))
            try:
                x_arr = np.asarray(x_data, dtype=float).ravel()
            except Exception:
                continue
            if x_arr.size < 2:
                continue
            y_proc = processing.apply_normalization(self, abs_path, parent, y_arr)
            try:
                y_proc = np.asarray(y_proc, dtype=float).ravel()
            except Exception:
                y_proc = np.asarray(y_arr, dtype=float).ravel()
            mlen = int(min(x_arr.size, y_proc.size))
            if mlen < 3:
                continue
            x_use = np.asarray(x_arr[:mlen], dtype=float).ravel()
            y_use = np.asarray(y_proc[:mlen], dtype=float).ravel()
            bg = self._apply_automatic_bg_new(x_use, y_use, deg=int(deg), pre_edge_percent=float(pre_edge_percent), do_plot=False)
            bgs[key] = np.asarray(bg, dtype=float).ravel()[:mlen]
            x_list.append(x_use)

        if not bgs:
            return None, None

        # Return a common grid only if identical (for optional markers)
        x_common = None
        try:
            x0 = x_list[0]
            same = True
            for xx in x_list[1:]:
                if xx.size != x0.size or (not np.allclose(xx, x0, rtol=0, atol=1e-9, equal_nan=True)):
                    same = False
                    break
            if same:
                x_common = x0
        except Exception:
            x_common = None

        return x_common, bgs

    def _group_equalize_area_jump_and_zero_preedge(self, items_simple: dict, pre: float, match_preedge_slope: bool = False):
        """Adjust *per-spectrum* automatic backgrounds in group mode.

        This routine is used when multiple spectra are selected and the user
        intends to apply **Area** post-normalization. It modifies each spectrum's
        background so that:

        - The **pre-edge baseline after BG subtraction is 0** (per spectrum).
        - The **jump after BG subtraction and Area-normalization** is the same
          across the group (median target).
        - Optionally (when match_preedge_slope=True), the **pre-edge slope after BG subtraction**
          is also made consistent across the group (median target).

        Notes:
            - Backgrounds are not forced to share a common polynomial shape.
            - The correction uses an affine term (linear + constant) per spectrum.
        """
        import numpy as np

        if not items_simple or len(items_simple) < 2:
            return items_simple, None

        # Helper: find pre/post windows on a finite-length array
        def _windows(n: int):
            n = int(n)
            if n < 3:
                return None
            M = max(1, int(float(pre) * n))
            M = min(M, n - 1)
            i_start = max(M + 1, int(0.95 * n))
            if i_start >= n - 1:
                i_start = max(n - 2, 0)
            return M, i_start

        # First pass: compute per-spectrum baseline-zero shift and the current ratio R0 = jump/area.
        ratios = []
        slopes = []  # only used when match_preedge_slope=True
        per = {}
        for key, (x_use, y_use, bg) in items_simple.items():
            x_use = np.asarray(x_use, dtype=float).ravel()
            y_use = np.asarray(y_use, dtype=float).ravel()
            bg = np.asarray(bg, dtype=float).ravel()
            n = min(x_use.size, y_use.size, bg.size)
            if n < 3:
                continue
            x_use = x_use[:n]; y_use = y_use[:n]; bg = bg[:n]
            f = np.isfinite(x_use) & np.isfinite(y_use) & np.isfinite(bg)
            xf = x_use[f]
            if xf.size < 3:
                continue
            yf = y_use[f]
            bgf = bg[f]

            win = _windows(int(xf.size))
            if win is None:
                continue
            M, i_start = win

            # Center x for numerical stability.
            xbar = float(np.nanmean(xf))
            t = xf - xbar

            # Baseline-zero constant for beta=0
            r0 = float(np.nanmean((yf - bgf)[:M]))
            s0 = (yf - bgf) - r0  # pre-edge mean is ~0

            area0 = float(trapezoid(s0, xf))
            if (not np.isfinite(area0)) or abs(area0) < 1e-15:
                continue
            jump0 = float(np.nanmean(s0[i_start:]))  # pre is 0 by construction
            ratio0 = jump0 / area0
            if not np.isfinite(ratio0):
                continue

            # Terms needed for the beta solve under the constraint that pre-edge remains 0.
            mp = float(np.nanmean(t[:M]))
            tt = t - mp  # this ensures the pre-edge mean of the correction term is 0
            T = float(trapezoid(tt, xf))
            P = float(np.nanmean(tt[i_start:]))

            # Optional: pre-edge slope of the BG-subtracted signal (after baseline shift).
            m0 = None
            phi2 = None
            T2 = 0.0
            P2 = 0.0
            if bool(match_preedge_slope):
                try:
                    if int(M) >= 2:
                        m0 = float(np.polyfit(xf[:M], s0[:M], 1)[0])
                    else:
                        m0 = float(np.polyfit(xf[: max(2, int(M))], s0[: max(2, int(M))], 1)[0])
                except Exception:
                    m0 = None

                # A localized pre-edge basis function: w(x)*(x-x_pre_mean)
                # w=1 in pre-edge, then smoothly tapers to 0 well before the post-edge window.
                try:
                    x_pre_mean = float(np.nanmean(xf[:M]))
                    w = np.zeros_like(xf, dtype=float)
                    w[:M] = 1.0
                    # Choose a taper length that (if possible) ends before the post window.
                    k_suggest = max(5, int(0.05 * float(xf.size)))
                    k_max = max(1, int(i_start) - int(M) - 1)
                    K = int(min(k_suggest, k_max))
                    if K < 1:
                        K = 1
                    end = min(int(M) + int(K), int(xf.size) - 1)
                    # Build cosine taper from 1 -> 0 across [M, end]
                    tt_idx = np.arange(0, (end - int(M)) + 1, dtype=float)
                    denomK = float(max(1, (end - int(M))))
                    w[int(M) : end + 1] = 0.5 * (1.0 + np.cos(np.pi * tt_idx / denomK))
                    phi2 = w * (xf - x_pre_mean)
                    T2 = float(trapezoid(phi2, xf))
                    P2 = float(np.nanmean(phi2[i_start:]))
                except Exception:
                    phi2 = None
                    T2 = 0.0
                    P2 = 0.0

                if m0 is not None and np.isfinite(m0):
                    slopes.append(float(m0))

            ratios.append(ratio0)
            per[key] = {
                "n": n,
                "f": f,
                "xf": xf,
                "yf": yf,
                "bgf": bgf,
                "xbar": xbar,
                "r0": r0,
                "mp": mp,
                "s0": s0,
                "area0": area0,
                "jump0": jump0,
                "T": T,
                "P": P,
                "m0": m0,
                "phi2": phi2,
                "T2": T2,
                "P2": P2,
            }

        if len(ratios) < 2:
            return items_simple, None

        R_target = float(np.median(np.asarray(ratios, dtype=float)))

        m_target = None
        if bool(match_preedge_slope):
            try:
                if len(slopes) >= 2:
                    m_target = float(np.median(np.asarray(slopes, dtype=float)))
            except Exception:
                m_target = None

        adjusted = {}
        changed = 0
        for key, (x_use, y_use, bg) in items_simple.items():
            if key not in per:
                adjusted[key] = (x_use, y_use, bg)
                continue
            info = per[key]
            x_use = np.asarray(x_use, dtype=float).ravel()[: info["n"]]
            bg = np.asarray(bg, dtype=float).ravel()[: info["n"]]
            f = info["f"]
            xf = info["xf"]
            yf = info["yf"]
            bgf = info["bgf"]
            xbar = float(info["xbar"])
            r0 = float(info["r0"])
            mp = float(info["mp"])
            area0 = float(info["area0"])
            jump0 = float(info["jump0"])
            T = float(info["T"])
            P = float(info["P"])

            # --- Optional: match pre-edge slope as well (3 constraints, 3 DOF: constant + global linear + localized pre-edge linear) ---
            if bool(match_preedge_slope) and (m_target is not None) and (info.get("phi2") is not None) and (info.get("m0") is not None):
                try:
                    A11 = (R_target * T - P)
                    A12 = (R_target * float(info.get("T2", 0.0)) - float(info.get("P2", 0.0)))
                    rhs1 = (R_target * area0 - jump0)
                    rhs2 = (float(info["m0"]) - float(m_target))
                    det = (A11 - A12)
                    if (not np.isfinite(det)) or abs(det) < 1e-15:
                        raise ZeroDivisionError("singular slope/ratio system")
                    u1 = (rhs1 - A12 * rhs2) / det
                    u2 = rhs2 - u1
                    if (not np.isfinite(u1)) or (not np.isfinite(u2)):
                        raise ValueError("non-finite solution")
                    # Constant term that keeps pre-edge baseline at 0
                    u0 = r0 - float(u1) * mp
                    phi2 = np.asarray(info["phi2"], dtype=float).ravel()
                    bg_adj = bg.copy()
                    bg_adj_f = bgf + float(u0) + float(u1) * (xf - xbar) + float(u2) * phi2
                    bg_adj[f] = bg_adj_f
                    adjusted[key] = (x_use, y_use, bg_adj)
                    changed += 1
                    continue
                except Exception:
                    # Fall back to the 2-parameter solution below
                    pass

            # --- Default 2-parameter equalization (baseline + jump/area) ---
            denom = (R_target * T - P)
            if (not np.isfinite(denom)) or abs(denom) < 1e-15:
                # Fallback: only baseline-zero shift
                bg_adj = bg.copy()
                bg_adj[f] = bgf + r0
                adjusted[key] = (x_use, y_use, bg_adj)
                continue

            beta = (R_target * area0 - jump0) / denom
            if not np.isfinite(beta):
                bg_adj = bg.copy()
                bg_adj[f] = bgf + r0
                adjusted[key] = (x_use, y_use, bg_adj)
                continue

            # Constant term that keeps pre-edge baseline at 0 for the chosen beta.
            c = r0 - float(beta) * mp

            bg_adj = bg.copy()
            bg_adj_f = bgf + float(beta) * (xf - xbar) + float(c)
            bg_adj[f] = bg_adj_f
            adjusted[key] = (x_use, y_use, bg_adj)
            changed += 1

        msg = None
        if changed >= 2:
            if bool(match_preedge_slope) and (m_target is not None):
                msg = (
                    f"Group BG: pre-edge=0, equalized jump after Area normalization (target={R_target:.4g}), "
                    f"matched pre-edge slope (target={m_target:.4g})"
                )
            else:
                msg = f"Group BG: pre-edge=0 and equalized jump after Area normalization (target={R_target:.4g})"

        return adjusted, msg

    def _plot_multiple_with_group_auto_bg(self):
        """Plot multiple selected curves with group automatic background fitting."""
        import numpy as np

        self.proc_ax.clear()
        self.reset_manual_mode()
        try:
            if getattr(self, "manual_bg_line", None) is not None:
                self.manual_bg_line.remove()
                self.manual_bg_line = None
        except Exception:
            pass

        keys = self._visible_processed_keys()
        if not keys:
            return

        # Compute group backgrounds; fall back to per-spectrum if group fit is not possible
        try:
            deg = int(self.combo_poly.currentText())
        except Exception:
            deg = 2
        try:
            pre = float(self.spin_preedge.value()) / 100.0
        except Exception:
            pre = 0.12

        # Determine whether background subtraction is active
        subtract = bool(getattr(self, "chk_show_without_bg", None) is not None and self.chk_show_without_bg.isChecked())

        # Read the chosen post-normalization mode (even if the widget is disabled).
        # In group mode we may want to "anticipate" area normalization when drawing BG lines.
        norm_mode = "None"
        try:
            if hasattr(self, "combo_post_norm"):
                norm_mode = str(self.combo_post_norm.currentText())
        except Exception:
            norm_mode = "None"

        # Compute per-spectrum Automatic BG (same as single-spectrum auto), and collect x/y.
        items = {}
        for key in keys:
            parts = key.split("##", 1)
            if len(parts) != 2:
                continue
            abs_path, hdf5_path = parts
            parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
            y_data = self.plot_data.get(key)
            if y_data is None:
                continue
            try:
                y_arr = np.asarray(y_data, dtype=float).ravel()
            except Exception:
                continue
            if y_arr.size < 2:
                continue
            x_data = lookup_energy(self, abs_path, parent, int(y_arr.size))
            try:
                x_arr = np.asarray(x_data, dtype=float).ravel()
            except Exception:
                continue
            if x_arr.size < 2:
                continue
            y_proc = processing.apply_normalization(self, abs_path, parent, y_arr)
            try:
                y_proc = np.asarray(y_proc, dtype=float).ravel()
            except Exception:
                y_proc = np.asarray(y_arr, dtype=float).ravel()
            mlen = int(min(x_arr.size, y_proc.size))
            if mlen < 3:
                continue
            x_use = np.asarray(x_arr[:mlen], dtype=float).ravel()
            y_use = np.asarray(y_proc[:mlen], dtype=float).ravel()
            bg = self._apply_automatic_bg_new(x_use, y_use, deg=deg, pre_edge_percent=pre, do_plot=False)
            bg = np.asarray(bg, dtype=float).ravel()[:mlen]
            items[key] = (x_use, y_use, bg, hdf5_path)

        if not items:
            return
        # Choose a representative x-grid for the pre-edge marker and dragging.
        # Prefer a common grid if available; otherwise fall back to the first spectrum's grid.
        try:
            # items[key] = (x_use, y_use, bg, hdf5_path)
            _x_first = next(iter(items.values()))[0]
            self._proc_last_x = np.asarray(_x_first, dtype=float)
        except Exception:
            pass

        # Optional marker: show pre-edge boundary if all curves share a common grid.
        try:
            x_common, _bgs = self._compute_group_auto_backgrounds(list(items.keys()), deg=deg, pre_edge_percent=pre)
            if x_common is not None:
                try:
                    if len(x_common) >= 2:
                        self._proc_last_x = np.asarray(x_common, dtype=float)
                except Exception:
                    self._proc_last_x = np.asarray(x_common)
        except Exception:
            pass

        # If user plans to Area-normalize after BG subtraction, equalize the *post-area-normalized jump*
        # across the selected group by adding a per-spectrum zero-area tilt term to the background.
        # This keeps the area (trapz) unchanged while correcting the step height after area normalization.
        try:
            m = str(norm_mode).strip().lower()
            equalize_jump = m in ("area", "area=1")
        except Exception:
            equalize_jump = False

        if equalize_jump and len(items) >= 2:
            # Use a coupled correction so that each spectrum has zero pre-edge baseline after BG subtraction,
            # and the jump after Area-normalization is the same across the selected group.
            try:
                simple = {k: (v[0], v[1], v[2]) for k, v in items.items()}
                _match_slope = False
                try:
                    scb = getattr(self, "chk_group_bg_slope", None)
                    if scb is not None and scb.isEnabled() and scb.isChecked():
                        _match_slope = True
                except Exception:
                    _match_slope = False

                adjusted, msg = self._group_equalize_area_jump_and_zero_preedge(
                    simple, pre=float(pre), match_preedge_slope=bool(_match_slope)
                )
                for k, (x_u, y_u, bg_u) in adjusted.items():
                    if k in items:
                        _x0, _y0, _bg0, hdf5_path = items[k]
                        items[k] = (x_u, y_u, bg_u, hdf5_path)
                if msg:
                    try:
                        self.statusBar().showMessage(msg, 6000)
                    except Exception:
                        pass
            except Exception:
                pass

        # Plot all selected curves
        for key, (x_use, y_use, bg, hdf5_path) in items.items():
            if x_use.size == 0:
                continue
            if subtract:
                yy = y_use - bg
                try:
                    yy = processing._proc_safe_post_normalize(self, x_use, yy, norm_mode)
                except Exception:
                    pass
                line, = self.proc_ax.plot(x_use, yy, label=self.shorten_label(hdf5_path), color=self._get_persistent_curve_color(key))
            else:
                # Show the original (unsubtracted) spectrum together with its fitted background.
                # Use the same persistent color key as the spectrum itself.
                line, = self.proc_ax.plot(
                    x_use,
                    y_use,
                    label=self.shorten_label(hdf5_path),
                    color=self._get_persistent_curve_color(key),
                )
                self.proc_ax.plot(x_use, bg, linestyle="--", linewidth=1.2, alpha=0.65, color=line.get_color(), label="_bg")
            try:
                line.dataset_key = key
            except Exception:
                pass

    # (moved to plotting: update_plot_processed)

    # (moved to plotting: _toggle_bg_widgets)

    # (moved to plotting: _lookup_energy)

    # (moved to plotting: _apply_normalization)

    # (moved to plotting: _apply_automatic_bg_new)
