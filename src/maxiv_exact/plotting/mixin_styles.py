"""Curve styles/colors/visibility helpers (Phase 2 refactor)."""

import matplotlib.pyplot as plt


class StylesMixin:
    def get_line_color_for_key(self, key, ax):
        for line in ax.get_lines():
            if getattr(line, "dataset_key", None) == key:
                return line.get_color()
        return None

    def _ensure_curve_color_map(self):
        """Ensure persistent color mapping for raw/processed curves.

        This prevents Matplotlib's color cycle from reassigning colors when curves
        are temporarily hidden or removed from the selection.
        """
        if not hasattr(self, "_curve_color_map") or getattr(self, "_curve_color_map") is None:
            self._curve_color_map = {}
        if not hasattr(self, "_curve_color_cycle_idx") or getattr(self, "_curve_color_cycle_idx") is None:
            self._curve_color_cycle_idx = 0

    def _get_persistent_curve_color(self, key):
        """Return a stable color for a given dataset key."""
        self._ensure_curve_color_map()
        try:
            if key in self._curve_color_map and self._curve_color_map[key]:
                return self._curve_color_map[key]
        except Exception:
            pass

        # Pull Matplotlib's default color cycle (C0..)
        try:
            colors = plt.rcParams.get("axes.prop_cycle", None)
            if colors is not None:
                colors = colors.by_key().get("color", [])
            else:
                colors = []
        except Exception:
            colors = []
        if not colors:
            colors = [f"C{i}" for i in range(10)]

        try:
            used = set(v for v in self._curve_color_map.values() if v)
        except Exception:
            used = set()

        base = int(getattr(self, "_curve_color_cycle_idx", 0) or 0)
        chosen = None
        for i in range(len(colors)):
            c = colors[(base + i) % len(colors)]
            if c not in used:
                chosen = c
                self._curve_color_cycle_idx = (base + i + 1) % len(colors)
                break
        if chosen is None:
            chosen = colors[base % len(colors)]
            self._curve_color_cycle_idx = (base + 1) % len(colors)

        try:
            self._curve_color_map[key] = chosen
        except Exception:
            pass
        return chosen

    def change_curve_color(self, key, new_color):
        # Persist user-picked colors across re-plotting (Raw/Processed).
        try:
            self._ensure_curve_color_map()
            self._curve_color_map[key] = new_color
        except Exception:
            pass
        if key in self.plotted_lines:
            self.plotted_lines[key].set_color(new_color)
            self.update_legend()

    def change_curve_visibility(self, key, visible):
        if key in self.plotted_lines:
            self.plotted_lines[key].set_visible(visible)
            self.update_legend()
            self.rescale_plotted_axes()

    def change_curve_style(self, key, style, size):
        if key in self.plotted_lines:
            line = self.plotted_lines[key]
            if style == "Solid":
                line.set_linestyle("-")
                line.set_marker("")
                line.set_linewidth(size)
            elif style == "Dashed":
                line.set_linestyle("--")
                line.set_marker("")
                line.set_linewidth(size)
            elif style == "Scatter":
                line.set_linestyle("None")
                line.set_marker("o")
                line.set_markersize(size)
            self.update_legend()
            self.canvas_plotted.draw()
