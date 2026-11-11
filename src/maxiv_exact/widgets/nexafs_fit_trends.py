"""Trends tab for a captured NEXAFS analysis."""

import numpy as np
from matplotlib import colormaps
from matplotlib.lines import Line2D
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)

from ..nexafs_fit.trends import Experiment, METRICS, PASSES, export_fits, export_trends, trend_series
from .nexafs_trend_dialogs import ExperimentalParametersDialog, TrendResultsDialog
from .nexafs_trend_lines import trend_lines


class NexafsTrends(QWidget):
    spectrum_selected = pyqtSignal(str)

    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.group = group
        self.experiment = Experiment()
        self._results = {}
        self._names = {}
        self._components = {}
        self._outdated = set()
        self._series = ()
        self._selected = None
        self._colors = {}

        layout = QVBoxLayout(self)
        selection = QHBoxLayout()
        layout.addLayout(selection)
        self.metric = QComboBox()
        for key, (name, _, _, _) in METRICS.items():
            self.metric.addItem(name, key)
        self.passes = QComboBox()
        for label, stages in (("Pass 1 + Pass 2", tuple(PASSES)), *((label, (key,)) for key, label in PASSES.items())):
            self.passes.addItem(label, stages)
        self.axis = QComboBox()
        self.axis.addItems(["Spectrum index", "Experimental parameter"])
        self.line_style = QComboBox()
        self.line_style.addItems(["Points", "Lines", "Smooth"])
        self.line_style.setCurrentText("Lines")
        self.line_style.setToolTip("Interpolation changes only the plot. Exported data retain their original values.")
        for label, widget in (("Plot", self.metric), ("Results", self.passes), ("X axis", self.axis),
                              ("Line style", self.line_style)):
            selection.addWidget(QLabel(label))
            selection.addWidget(widget)
        selection.addStretch()

        actions = QHBoxLayout()
        layout.addLayout(actions)
        self.show_provisional = QCheckBox("Show provisional fits")
        self.show_provisional.setToolTip("Include finite, feasible results that did not converge.")
        actions.addWidget(self.show_provisional)
        actions.addStretch()
        self.experimental_parameters_button = QPushButton("Experimental parameters…")
        self.results_button = QPushButton("Results…")
        actions.addWidget(self.experimental_parameters_button)
        actions.addWidget(self.results_button)
        export_button = QToolButton()
        export_button.setText("Export")
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_menu = QMenu(export_button)
        self.export_fits_action = export_menu.addAction("Export fitted parameters…")
        self.export_trends_action = export_menu.addAction("Export selected trends…")
        export_button.setMenu(export_menu)
        actions.addWidget(export_button)

        plot = QSplitter(Qt.Orientation.Horizontal)
        plot.setChildrenCollapsible(False)
        layout.addWidget(plot, 1)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        figure = Figure(figsize=(7, 3.5))
        figure.subplots_adjust(left=.13, right=.98, top=.97, bottom=.11)
        self.canvas = FigureCanvasQTAgg(figure)
        self.canvas.setMinimumHeight(160)
        self.ax = figure.subplots()
        panel_layout.addWidget(NavigationToolbar2QT(self.canvas, panel))
        panel_layout.addWidget(self.canvas, 1)
        plot.addWidget(panel)

        choices = QWidget()
        choices_layout = QVBoxLayout(choices)
        choices_layout.setContentsMargins(4, 0, 0, 0)
        self.component_list = QListWidget()
        self.component_list.setMinimumWidth(120)
        self.component_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.component_list.setToolTip("Select one or more components with Ctrl or Shift.")
        choices_layout.addWidget(self.component_list)
        self.ratio_controls = QWidget()
        ratio_layout = QVBoxLayout(self.ratio_controls)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        self.numerator = QComboBox()
        self.denominator = QComboBox()
        ratio_layout.addWidget(QLabel("Numerator"))
        ratio_layout.addWidget(self.numerator)
        ratio_layout.addWidget(QLabel("Denominator"))
        ratio_layout.addWidget(self.denominator)
        ratio_layout.addStretch()
        choices_layout.addWidget(self.ratio_controls)
        plot.addWidget(choices)
        plot.setSizes([850, 160])
        plot.setStretchFactor(0, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.experimental_parameters_button.clicked.connect(self._open_experimental_parameters)
        self.results_button.clicked.connect(self._open_results)
        self.line_style.currentIndexChanged.connect(self._draw)
        self.axis.currentIndexChanged.connect(self._refresh)
        self.passes.currentIndexChanged.connect(self._refresh)
        self.show_provisional.toggled.connect(self._refresh)
        self.metric.currentIndexChanged.connect(self._refresh_choices)
        self.component_list.itemSelectionChanged.connect(self._refresh)
        self.numerator.currentIndexChanged.connect(self._refresh)
        self.denominator.currentIndexChanged.connect(self._refresh)
        self.export_fits_action.triggered.connect(self._export_fits)
        self.export_trends_action.triggered.connect(self._export_trends)
        self._refresh_choices()

    def set_experiment(self, experiment):
        self.experiment = experiment.for_group(self.group)
        self._refresh()

    def current_experiment(self):
        return self.experiment.for_group(self.group)

    def _open_experimental_parameters(self):
        dialog = ExperimentalParametersDialog(self.group, self.experiment, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_experiment(dialog.experiment)

    def _open_results(self):
        dialog = TrendResultsDialog(self.group, self._results, self._names,
                                    self.experiment, self._outdated, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.spectrum_key is not None:
            self.set_selected_spectrum(dialog.spectrum_key)
            self.spectrum_selected.emit(dialog.spectrum_key)

    def set_fits(self, model, names, results, outdated):
        passes = {key: results[key] for key in PASSES if key in results}
        components = {spec.key: type(spec.initial) for spec in model.components}
        for result in passes.values():
            components.update((spec.key, type(spec.initial)) for spec in result.model.components)
        if (passes, components, names, outdated) == (self._results, self._components, self._names, self._outdated):
            return
        self._results, self._components = passes, components
        self._names, self._outdated = dict(names), set(outdated)
        self._refresh_choices()

    def set_selected_spectrum(self, key):
        if self._selected == key:
            return
        self._selected = key
        self._draw()

    def _color(self, key):
        if key not in self._colors:
            palette = colormaps["tab20"]
            self._colors[key] = palette(len(self._colors) % palette.N)
        return self._colors[key]

    def _refresh_choices(self):
        metric = self.metric.currentData()
        kind = METRICS[metric][2]
        keys = [key for key, component_type in self._components.items() if component_type is kind]
        selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.component_list.selectedItems()}
        with QSignalBlocker(self.component_list):
            self.component_list.clear()
            for key in keys:
                item = QListWidgetItem(self._names.get(key, key))
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setToolTip(key)
                swatch = QPixmap(10, 10)
                swatch.fill(QColor.fromRgbF(*self._color(key)))
                item.setIcon(QIcon(swatch))
                self.component_list.addItem(item)
                item.setSelected(key in selected)
            if keys and not self.component_list.selectedItems():
                self.component_list.item(0).setSelected(True)
        ratio = metric == "ratio"
        self.component_list.setVisible(not ratio)
        self.ratio_controls.setVisible(ratio)
        if ratio:
            for combo, default in ((self.numerator, 0), (self.denominator, 1)):
                previous = combo.currentData()
                with QSignalBlocker(combo):
                    combo.clear()
                    for key in keys:
                        combo.addItem(self._names.get(key, key), key)
                    index = combo.findData(previous)
                    combo.setCurrentIndex(index if index >= 0 else min(default, len(keys) - 1))
        self._refresh()

    def _series_name(self, series):
        name = self._names.get(series.component, series.component)
        if series.denominator is not None:
            name += f" / {self._names.get(series.denominator, series.denominator)}"
        return name

    def _refresh(self):
        metric = self.metric.currentData()
        stages = self.passes.currentData() or ()
        denominator = None
        if metric == "ratio":
            numerator, denominator = self.numerator.currentData(), self.denominator.currentData()
            keys = [numerator] if numerator is not None and denominator is not None and numerator != denominator else []
        else:
            keys = [item.data(Qt.ItemDataRole.UserRole) for item in self.component_list.selectedItems()]
        self._series = trend_series(self.group, self._results, stages, metric, keys, denominator,
                                    show_provisional=self.show_provisional.isChecked())
        self._draw()
        self.export_fits_action.setEnabled(bool(self._results))
        self.export_trends_action.setEnabled(bool(self._series) and any(stage in self._results for stage in stages))
        missing = sum(s.key not in self.experiment.values for s in self.group.spectra) if self.axis.currentIndex() else 0
        notes = []
        if not self._results:
            notes.append("Run Pass 1 or Pass 2 to plot fitted trends.")
        elif metric == "ratio" and not keys:
            notes.append("Select two different Gaussian components for the ratio.")
        if missing:
            notes.append(f"Missing experimental X values: {missing}.")
        stale = ", ".join(PASSES[stage] for stage in stages if stage in self._outdated)
        if stale:
            notes.append(f"Outdated: {stale}.")
        if not self.show_provisional.isChecked() and any(
            "Provisional" in line.fit_statuses for line in self._series
        ):
            notes.append("Provisional fits hidden.")
        self.status.setText("  ".join(notes))
        self.status.setVisible(bool(notes))

    def _draw(self):
        self.ax.clear()
        x = (np.asarray([self.experiment.values.get(s.key, np.nan) for s in self.group.spectra])
             if self.axis.currentIndex() else np.arange(1, len(self.group.spectra) + 1))
        selected = next((i for i, spec in enumerate(self.group.spectra) if spec.key == self._selected), None)
        style = self.line_style.currentText()
        component_keys = {}
        pass_keys = {}
        for series in self._series:
            color = self._color(series.component)
            y = np.asarray([np.nan if value is None else value for value in series.values])
            valid = np.isfinite(x) & np.isfinite(y)
            provisional = np.asarray([status == "Provisional" for status in series.fit_statuses])
            first_pass = series.stage == "pass1"
            for mask, pending in ((valid & ~provisional, False), (valid & provisional, True)):
                if not mask.any():
                    continue
                marker = ("x" if first_pass else "+") if pending else ("o" if first_pass else "s")
                filled = first_pass and not pending
                line_style = "-" if first_pass and not pending else "--" if pending else ":"
                if style != "Points":
                    for xx, yy in trend_lines(x, y, mask, smooth=style == "Smooth"):
                        self.ax.plot(xx, yy, linestyle=line_style, color=color, alpha=.8, linewidth=1.1)
                self.ax.plot(x[mask], y[mask], linestyle="none", color=color, marker=marker,
                             markerfacecolor=color if filled else "none", markersize=5)
                component_keys[series.component, series.denominator] = Line2D(
                    [], [], color=color, linewidth=2, label=self._series_name(series)
                )
                pass_keys[series.stage, pending] = Line2D(
                    [], [], linestyle="none", color="0.25", marker=marker,
                    markerfacecolor="0.25" if filled else "none",
                    label=PASSES[series.stage] + (" provisional" if pending else ""),
                )
            if selected is not None and valid[selected]:
                self.ax.scatter(x[selected], y[selected], facecolors="none", edgecolors="black", s=75)
        name, unit, _, _ = METRICS[self.metric.currentData()]
        self.ax.set_xlabel(self.experiment.axis_label if self.axis.currentIndex() else "Spectrum index",
                           parse_math=False)
        self.ax.set_ylabel(f"{name} ({unit})" if unit != "dimensionless" else name)
        if component_keys:
            handles = [*component_keys.values(), *pass_keys.values()]
            legend = self.ax.legend(handles=handles, loc="best", fontsize="small",
                                    ncols=min(3, (len(handles) + 5) // 6))
            for text in legend.get_texts():
                text.set_parse_math(False)
        else:
            self.ax.text(.5, .5, "No values to plot", transform=self.ax.transAxes, ha="center", va="center")
        self.canvas.draw_idle()

    def _export(self, caption, writer, *arguments):
        path, _ = QFileDialog.getSaveFileName(self, caption, "", "CSV (*.csv)")
        if path:
            try:
                writer(path if path.lower().endswith(".csv") else path + ".csv", *arguments)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, caption, str(error))

    def _export_fits(self):
        self._export("Export fitted parameters", export_fits, self.group, self._results, self._names,
                     self.current_experiment(), self._outdated)

    def _export_trends(self):
        self._export("Export selected trends", export_trends, self.group, self._series, self._names,
                     self.current_experiment(), self.metric.currentData(), bool(self.axis.currentIndex()),
                     self._outdated)
