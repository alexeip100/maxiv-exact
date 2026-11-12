"""Linked spectral and residual plots for the NEXAFS Fit tab."""

from dataclasses import dataclass, replace
from math import hypot, isfinite

import numpy as np
from matplotlib.backend_bases import MouseButton
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget


from ..nexafs_fit.model import Gaussian, IPStep


@dataclass(frozen=True, slots=True)
class _ComponentHandle:
    key: str
    component: Gaussian | IPStep
    position_field: str
    amplitude_field: str
    unit_intensity: float
    position_bounds: tuple[float | None, float | None]
    curve: Line2D
    marker: Line2D


class NexafsFitPlot(QWidget):
    component_edited = pyqtSignal(str, object, object)

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
        self.selected_key = None
        self._handles = []
        self._drag = None
        self.canvas.mpl_connect("button_press_event", self._press)
        self.canvas.mpl_connect("motion_notify_event", self._move)
        self.canvas.mpl_connect("button_release_event", self._release)

    def display(self, context, data, fit_energy, prediction, residual, curves, limits, *,
                spectrum_title, preview=False, editable_components=None):
        self._handles.clear()
        self._drag = None
        self._residual_line = None
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
            for key, label, color, linestyle, values in curves:
                curve, = self.main_ax.plot(
                    fit_energy, values, label=label, color=color, linestyle=linestyle, linewidth=1.15,
                )
                if editable_components and key in editable_components:
                    component, position_bounds = editable_components[key]
                    self._add_handle(key, component, position_bounds, curve)
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
            self._residual_line, = self.residual_ax.plot(fit_energy, residual, color="#3d6790", linewidth=1)
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
        if self._residual_line is not None:
            self.main_ax.callbacks.connect("xlim_changed", self._autoscale_residual)
            self.residual_ax.callbacks.connect("xlim_changed", self._autoscale_residual)
            self.residual_ax.callbacks.connect("ylim_changed", self._autoscale_residual)
            self._autoscale_residual(self.main_ax)
        self.canvas.draw_idle()

    def _autoscale_residual(self, axis):
        if self._residual_line is None:
            return
        low, high = sorted(axis.get_xlim())
        energy, residual = self._residual_line.get_data()
        finite = np.isfinite(residual)
        visible = finite & (energy >= low) & (energy <= high)
        values = residual[visible if visible.any() else finite]
        if values.size:
            bottom = min(0.0, float(values.min()))
            top = max(0.0, float(values.max()))
            pad = 0.08 * (top - bottom) if bottom < top else 1e-12
            self.residual_ax.set_ylim(bottom - pad, top + pad, emit=False)

    def _add_handle(self, key, component, position_bounds, curve):
        position_field, amplitude_field = (
            ("center", "area") if isinstance(component, Gaussian) else ("position", "height")
        )
        position = getattr(component, position_field)
        energy = curve.get_xdata()
        if not energy.size or not energy.min() <= position <= energy.max():
            return
        unit_intensity = float(replace(component, **{amplitude_field: 1.0}).evaluate([position])[0])
        intensity = unit_intensity * getattr(component, amplitude_field)
        marker, = self.main_ax.plot(
            [position], [intensity], marker="o", linestyle="none", markersize=6,
            color=curve.get_color(), markeredgecolor="#404040", markeredgewidth=0.65, zorder=5,
        )
        self._handles.append(_ComponentHandle(
            key, component, position_field, amplitude_field, unit_intensity, position_bounds, curve, marker,
        ))

    def _press(self, event):
        if event.button != MouseButton.LEFT or event.inaxes != self.main_ax or self.toolbar.mode:
            return
        nearest = None
        radius = self.canvas.figure.dpi * 6 / 72
        best = None
        for handle in self._handles:
            anchor_x, anchor_y = self.main_ax.transData.transform(handle.marker.get_xydata()[0])
            distance = hypot(event.x - anchor_x, event.y - anchor_y)
            # Use the selected row to disambiguate handles at the same pixel.
            priority = (round(distance), handle.key != self.selected_key)
            if distance <= radius and (best is None or priority < best):
                nearest, best = handle, priority
        if nearest is not None:
            self._drag = nearest, event

    def _drag_values(self, event):
        handle, press = self._drag
        position = amplitude = None
        if event.inaxes == self.main_ax and not self.toolbar.mode:
            if abs(event.x - press.x) >= 2:
                initial = getattr(handle.component, handle.position_field)
                position = initial + (event.xdata - press.xdata)
                low, high = handle.position_bounds
                if low is not None:
                    position = max(low, position)
                if high is not None:
                    position = min(high, position)
                if not isfinite(position):
                    position = None
            if abs(event.y - press.y) >= 2:
                initial = getattr(handle.component, handle.amplitude_field)
                value = initial + (event.ydata - press.ydata) / handle.unit_intensity
                if isfinite(value):
                    amplitude = max(0.0, value)
        return position, amplitude

    @staticmethod
    def _draw_handle(handle, position=None, amplitude=None):
        fields = {}
        if position is not None:
            fields[handle.position_field] = position
        if amplitude is not None:
            fields[handle.amplitude_field] = amplitude
        component = replace(handle.component, **fields) if fields else handle.component
        handle.curve.set_ydata(component.evaluate(handle.curve.get_xdata()))
        handle.marker.set_data(
            [getattr(component, handle.position_field)],
            [handle.unit_intensity * getattr(component, handle.amplitude_field)],
        )

    def _move(self, event):
        if self._drag is not None:
            self._draw_handle(self._drag[0], *self._drag_values(event))
            self.canvas.draw_idle()

    def _release(self, event):
        if self._drag is None or event.button != MouseButton.LEFT:
            return
        handle = self._drag[0]
        position, amplitude = self._drag_values(event)
        self._drag = None
        self._draw_handle(handle)
        self.canvas.draw_idle()
        if position is not None or amplitude is not None:
            self.component_edited.emit(handle.key, position, amplitude)
