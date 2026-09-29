"""Grid/axes helpers for the plotted canvas (Phase 2 refactor)."""

from matplotlib.ticker import AutoMinorLocator


class GridAxesMixin:
    def on_grid_toggled(self, index=None):
        """Handle change of grid density from combo box.

        ``index`` is optional because the default grid setting is also applied
        programmatically during UI setup, before any Qt signal supplies an index.
        """
        try:
            self._apply_grid_mode()
        except Exception:
            pass

    def _apply_grid_mode(self, mode_text=None):
        """Apply grid mode ('None', 'Coarse', 'Fine', 'Finest') to plotted_ax.

        'Coarse' reproduces the original checkbox behavior (major-grid only).
        'Fine' uses 1 minor division (2× finer), 'Finest' uses 5 divisions
        (~5× finer). Minor grid lines are shown less prominently than major
        grid lines."""
        ax = getattr(self, 'plotted_ax', None)
        if ax is None:
            return

# Determine mode from combo if not provided
        if mode_text is None:
            try:
                combo = getattr(self, 'grid_mode_combo', None)
                if combo is not None:
                    mode_text = combo.currentText()
            except Exception:
                mode_text = None
        if not mode_text:
            mode_text = 'None'
        mode = str(mode_text).strip().lower()

# Start from a clean grid state
        try:
            ax.grid(False, which='both')
        except Exception:
            pass

        if mode == 'none':
# No grid at all, turn off minor ticks too
            try:
                ax.minorticks_off()
            except Exception:
                pass
        else:
# Always show major grid lines for any non-'None' mode, as solid lines
            try:
                ax.grid(True, which='major', linestyle='-')
            except Exception:
                pass

# 'Coarse' -> only major grid (no extra minor divisions)
            if mode == 'coarse':
                try:
                    ax.minorticks_off()
                except Exception:
                    pass
            else:
# 'Fine' and 'Finest' -> add minor grid with more divisions, / drawn as softer dashed lines between the major grid lines.
                n = 2 if mode == 'fine' else 5
                try:
                    ax.minorticks_on()
                    ax.xaxis.set_minor_locator(AutoMinorLocator(n))
                    ax.yaxis.set_minor_locator(AutoMinorLocator(n))
# Minor grid only; keep major grid style unchanged
                    ax.grid(True, which='minor', linestyle='--', linewidth=0.5, alpha=0.6)
                except Exception:
                    pass

# Redraw canvas if available
        try:
            if hasattr(self, 'canvas_plotted'):
                self.canvas_plotted.draw()
        except Exception:
            pass

    def rescale_plotted_axes(self):
        x_all, y_all = [], []
        for key, line in self.plotted_lines.items():
            if line.get_visible():
                x = line.get_xdata(); y = line.get_ydata()
                if x is not None and len(x):
                    x_all.extend(x)
                if y is not None and len(y):
                    y_all.extend(y)
        if x_all and y_all:
            xmin, xmax = min(x_all), max(x_all)
            ymin, ymax = min(y_all), max(y_all)
            x_margin = (xmax - xmin) * 0.05 if (xmax - xmin) else 1
            y_margin = (ymax - ymin) * 0.05 if (ymax - ymin) else 1
            self.plotted_ax.set_xlim(xmin - x_margin, xmax + x_margin)
            self.plotted_ax.set_ylim(ymin - y_margin, ymax + y_margin)
# Re-apply grid mode after rescaling axes
            try:
                self._apply_grid_mode()
            except Exception:
                pass
            self.canvas_plotted_fig.tight_layout()
            # Keep Matplotlib's Home/"Reset original view" target in sync
            # with the current full-data limits. Otherwise the toolbar may
            # restore a stale range from a previously plotted energy region.
            try:
                toolbar = getattr(self, "toolbar_plotted", None)
                if toolbar is not None:
                    toolbar.update()
                    toolbar.push_current()
            except Exception:
                pass
            self.canvas_plotted.draw()
