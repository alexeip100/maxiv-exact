"""Waterfall plotting helpers (Phase 2 refactor)."""

import numpy as np

from ..qt_helpers import is_checked_state

class WaterfallMixin:
    def on_waterfall_toggled(self, state):
        checked = is_checked_state(state)
        self.waterfall_slider.setEnabled(checked)
        self.waterfall_spin.setEnabled(checked)
        self.recompute_waterfall_layout()

    def on_waterfall_slider_changed(self, value):
        param = value / 100.0
        self.waterfall_spin.blockSignals(True)
        self.waterfall_spin.setValue(param)
        self.waterfall_spin.blockSignals(False)
        self.recompute_waterfall_layout()

    def on_waterfall_spin_changed(self, dvalue):
        ival = int(round(dvalue * 100))
        self.waterfall_slider.blockSignals(True)
        self.waterfall_slider.setValue(ival)
        self.waterfall_slider.blockSignals(False)
        self.recompute_waterfall_layout()

    def apply_waterfall_shift(self):
        """Apply/update Waterfall offsets (Uniform step only)."""
        if not getattr(self, "plotted_lines", None):
            return

        enabled = False
        try:
            enabled = bool(getattr(self, "waterfall_checkbox", None) and self.waterfall_checkbox.isChecked())
        except Exception:
            enabled = False

        # Restore originals first so Waterfall is always applied on clean data
        try:
            self.restore_original_line_data()
        except Exception:
            pass

        # Build ordered visible keys (respect the plotted list order if present)
        plotted_keys_in_order = []
        if hasattr(self, "plotted_list"):
            try:
                for i in range(self.plotted_list.count()):
                    item = self.plotted_list.item(i)
                    widget = self.plotted_list.itemWidget(item)
                    if widget:
                        key = getattr(widget, "key", None)
                        line = self.plotted_lines.get(key) if key else None
                        if line is not None and line.get_visible():
                            plotted_keys_in_order.append(key)
            except Exception:
                plotted_keys_in_order = []
        if not plotted_keys_in_order:
            try:
                for k, line in self.plotted_lines.items():
                    if line is not None and line.get_visible():
                        plotted_keys_in_order.append(k)
            except Exception:
                plotted_keys_in_order = []

        if (not plotted_keys_in_order) or (not enabled):
            # No Waterfall: just rescale and redraw
            try:
                self.rescale_plotted_axes()
                if hasattr(self, "canvas_plotted"):
                    self.canvas_plotted.draw()
            except Exception:
                pass
            return

        # Uniform step parameter (0..1) multiplied by global y-range
        try:
            k = float(self.waterfall_spin.value())
        except Exception:
            k = 0.0

        # Compute global y-range from restored originals
        try:
            ymins, ymaxs = [], []
            for key in plotted_keys_in_order:
                line = self.plotted_lines[key]
                y = np.asarray(line.get_ydata(), dtype=float)
                m = np.isfinite(y)
                if np.any(m):
                    ymins.append(float(np.min(y[m])))
                    ymaxs.append(float(np.max(y[m])))
            if not ymins or not ymaxs:
                self.rescale_plotted_axes()
                return
            global_range = max(ymaxs) - min(ymins)
            if not np.isfinite(global_range) or global_range <= 0:
                global_range = 1.0
            step = k * global_range
        except Exception:
            step = 0.0

        # Apply offsets so the visual top-to-bottom order matches both the
        # Plotted list and the legend: the first list/legend item is the top
        # waterfall curve, the last item is the bottom curve.
        try:
            n_curves = len(plotted_keys_in_order)
            for idx, key in enumerate(plotted_keys_in_order):
                line = self.plotted_lines[key]
                y = np.asarray(line.get_ydata(), dtype=float)
                line.set_ydata(y + (n_curves - 1 - idx) * step)
        except Exception:
            pass

        try:
            self.rescale_plotted_axes()
            if hasattr(self, "canvas_plotted"):
                self.canvas_plotted.draw()
        except Exception:
            pass

    def restore_original_line_data(self):
        """Restore each line to the unshifted data we stored earlier."""
        for key, line in getattr(self, "plotted_lines", {}).items():
            if key in self.original_line_data:
                x_orig, y_orig = self.original_line_data[key]
                line.set_xdata(x_orig)
                line.set_ydata(y_orig)
        if hasattr(self, "canvas_plotted"):
            self.canvas_plotted.draw()

    def recompute_waterfall_layout(self):
        """Compatibility alias used by UI callbacks.

        Historically some callbacks call `recompute_waterfall_layout()`. In the current
        implementation, Waterfall is applied via `apply_waterfall_shift()`.
        """
        try:
            return self.apply_waterfall_shift()
        except Exception:
            # Keep UI robust; callers typically don't expect exceptions here.
            return None
