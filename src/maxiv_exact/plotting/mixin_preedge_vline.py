"""Pre-edge vertical line interaction mixin (Phase 3).

Moved from maxiv_exact.plotting.PlottingMixin.
"""

import numpy as np


class PreedgeVlineMixin:
    def _draw_preedge_vline(self, x):
        """Draw or update the vertical pre-edge boundary marker on the Processed plot."""
        import numpy as np
        if x is None:
            return
        try:
            x = np.asarray(x, dtype=float)
            if x.size < 2:
                return
        except Exception:
            return

        # Compute index from current pre-edge %
        try:
            pre = float(getattr(self, "spin_preedge").value()) / 100.0
        except Exception:
            pre = 0.1
        pre = max(0.001, min(0.999, pre))
        idx = int(pre * len(x))
        idx = max(1, min(idx, len(x) - 1))
        x0 = float(x[idx])

        ln = getattr(self, "proc_preedge_line", None)
        if ln is not None:
            try:
                if ln.axes is not self.proc_ax:
                    ln = None
            except Exception:
                ln = None

        if ln is None:
            try:
                ln = self.proc_ax.axvline(x0, linestyle=":", linewidth=1.2, alpha=0.8)
                # Make the line reliably pickable/draggable across backends and HiDPI.
                # Prefer using the artist's built-in hit-testing instead of pixel-space heuristics.
                try:
                    # Enable picking and enlarge pick radius (in points).
                    ln.set_picker(True)
                    if hasattr(ln, "set_pickradius"):
                        ln.set_pickradius(10)
                    else:
                        # Older API fallback
                        ln.set_picker(10)
                except Exception:
                    pass
                self.proc_preedge_line = ln
            except Exception:
                return
        else:
            try:
                ln.set_xdata([x0, x0])
            except Exception:
                pass

    def _on_preedge_vline_press(self, event):
        """Start dragging the pre-edge marker (Auto BG only).

        Uses the artist's hit-testing (Line2D.contains) which is robust across
        backends and HiDPI scaling.
        """
        import numpy as np
        try:
            # Only for Automatic background mode
            if getattr(self, "combo_bg", None) is None:
                return
            if self.combo_bg.currentText() != "Automatic":
                return
            if event is None:
                return
            if getattr(event, "button", None) not in (1,):
                return
            # Prefer not to hard-require event.inaxes: on some backends/HiDPI
            # configurations the press can arrive with inaxes=None even though
            # the click was visually on the axes.
            if getattr(self, "proc_ax", None) is None:
                return

            ln = getattr(self, "proc_preedge_line", None)
            if ln is None:
                return

            # Prefer robust artist hit-testing (accounts for HiDPI/backend details)
            try:
                contains, _info = ln.contains(event)
                if bool(contains):
                    self._dragging_preedge = True
                    return
            except Exception:
                pass

            # Fallback: data/pixel-space tolerance (in case contains() fails)
            try:
                x0 = float(ln.get_xdata()[0])
                ax = self.proc_ax
                xlim = ax.get_xlim()
                xr = abs(float(xlim[1]) - float(xlim[0]))
                # generous tolerance: 3% of the visible range, but at least a few grid steps
                tol = max(0.03 * xr, 1e-6)
                x = getattr(self, "_proc_last_x", None)
                if x is not None:
                    x = np.asarray(x, dtype=float)
                    if x.size >= 2:
                        dx = np.nanmedian(np.diff(x))
                        if np.isfinite(dx) and dx > 0:
                            tol = max(tol, 3.0 * float(dx))
                xevt = None
                if getattr(event, "xdata", None) is not None and np.isfinite(event.xdata):
                    xevt = float(event.xdata)
                elif getattr(event, "x", None) is not None:
                    # Convert display x (pixels) to data x
                    try:
                        y0, y1 = ax.get_ylim()
                        ymid = 0.5 * (float(y0) + float(y1))
                        ydisp = float(ax.transData.transform((0.0, ymid))[1])
                        xevt = float(ax.transData.inverted().transform((float(event.x), ydisp))[0])
                    except Exception:
                        xevt = None
                if xevt is None:
                    return
                if abs(float(xevt) - x0) <= tol:
                    self._dragging_preedge = True
            except Exception:
                return
        except Exception:
            return


    def _on_preedge_vline_pick(self, event):
        """Start dragging the pre-edge marker when the marker line is picked."""
        try:
            if getattr(self, "combo_bg").currentText() != "Automatic":
                return
            ln = getattr(self, "proc_preedge_line", None)
            if ln is None:
                return
            if getattr(event, "artist", None) is not ln:
                return
            # Only left mouse button
            me = getattr(event, "mouseevent", None)
            if me is not None and getattr(me, "button", None) not in (1,):
                return
            self._dragging_preedge = True
        except Exception:
            return

    def _on_preedge_vline_motion(self, event):
        """Drag handler for the pre-edge marker."""
        import numpy as np
        if not getattr(self, "_dragging_preedge", False):
            return
        try:
            ax = getattr(self, "proc_ax", None)
            if ax is None:
                return
            # event.xdata can be None on some backend/HiDPI combos; fall back to pixel->data conversion.
            x_new = None
            if getattr(event, "xdata", None) is not None and np.isfinite(event.xdata):
                x_new = float(event.xdata)
            elif getattr(event, "x", None) is not None:
                try:
                    y0, y1 = ax.get_ylim()
                    ymid = 0.5 * (float(y0) + float(y1))
                    # Get display y at the midpoint, then invert transform for the mouse x.
                    ydisp = float(ax.transData.transform((0.0, ymid))[1])
                    x_new = float(ax.transData.inverted().transform((float(event.x), ydisp))[0])
                except Exception:
                    x_new = None
            if x_new is None:
                return
            x = getattr(self, "_proc_last_x", None)
            if x is None:
                return
            x = np.asarray(x, dtype=float)
            if x.size < 2:
                return
            # Find nearest index
            idx = int(np.argmin(np.abs(x - x_new)))
            idx = max(1, min(idx, len(x) - 1))
            pre_pct = 100.0 * (idx / float(len(x)))
            pre_pct = max(0.1, min(99.9, pre_pct))
            spin = getattr(self, "spin_preedge", None)
            if spin is None:
                return
            # Avoid tiny oscillations
            if abs(float(spin.value()) - pre_pct) >= 0.1:
                spin.setValue(pre_pct)
            # Move marker immediately for responsiveness
            try:
                ln = getattr(self, "proc_preedge_line", None)
                if ln is not None:
                    ln.set_xdata([float(x[idx]), float(x[idx])])
                    self.canvas_proc.draw_idle()
            except Exception:
                pass
        except Exception:
            return

    def _on_preedge_vline_release(self, event):
        """Stop dragging the pre-edge marker."""
        try:
            self._dragging_preedge = False
        except Exception:
            pass

    # ------------ Misc helpers ------------

