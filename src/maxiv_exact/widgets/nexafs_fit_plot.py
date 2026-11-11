"""Linked spectral and residual plots for the NEXAFS Fit tab."""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class NexafsFitPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        figure = Figure(figsize=(6, 5), layout="none")
        figure.subplots_adjust(left=0.18, right=0.98, bottom=0.14, top=0.98, hspace=0.13)
        self.canvas = FigureCanvasQTAgg(figure)
        self.canvas.setMinimumSize(320, 245)
        self.main_ax, self.residual_ax = figure.subplots(
            2, 1, sharex=True, gridspec_kw={"height_ratios": (3, 1)}
        )
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self._context = None

    def display(self, context, data, fit_energy, prediction, residual, curves, limits, *,
                spectrum_title, preview=False):
        same_view = context == self._context
        previous_limits = self.main_ax.get_xlim()
        self._context = context
        self.main_ax.clear()
        self.residual_ax.clear()
        energy, intensity = data
        measured, = self.main_ax.plot(energy, intensity, color="#404040", linewidth=1.2, label=spectrum_title)
        if prediction is not None:
            self.main_ax.plot(
                fit_energy, prediction, color="#ae2c2c", linewidth=1.4,
                linestyle="--" if preview else "-", label="Model preview" if preview else "Total fit",
            )
            for label, color, linestyle, values in curves:
                self.main_ax.plot(fit_energy, values, label=label, color=color, linestyle=linestyle, linewidth=1.15)
        if limits is not None:
            for axis in (self.main_ax, self.residual_ax):
                for edge in limits:
                    axis.axvline(edge, color="0.55", linestyle=":", linewidth=0.8, alpha=0.8)
        self.main_ax.set_ylabel("Processed intensity")
        self.main_ax.tick_params(labelbottom=False)
        handles, labels = self.main_ax.get_legend_handles_labels()
        entries = [(measured, spectrum_title)]
        entries.extend((handle, label) for handle, label in zip(handles, labels) if handle is not measured)
        if len(entries) > 8:
            entries = entries[:2]
        handles, labels = zip(*entries)
        legend = self.main_ax.legend(handles, labels, loc="upper left", fontsize="small")
        for text in legend.get_texts():
            text.set_parse_math(False)
        self.residual_ax.axhline(0, color="0.5", linewidth=0.8)
        if residual is not None:
            self.residual_ax.plot(fit_energy, residual, color="#3d6790", linewidth=1)
        else:
            self.residual_ax.text(
                0.5, 0.5, "Select a completed fit to see residuals",
                ha="center", va="center", color="0.4", transform=self.residual_ax.transAxes,
            )
        self.residual_ax.set_xlabel("Photon energy (eV)")
        self.residual_ax.set_ylabel("Residual")
        if same_view:
            self.main_ax.set_xlim(previous_limits)
        else:
            self.toolbar.update()
        self.canvas.draw_idle()
