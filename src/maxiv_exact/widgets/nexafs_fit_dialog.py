"""Modeless NEXAFS Fit / Trends workspace for a captured Group BG group."""

from dataclasses import replace
from threading import Event

import numpy as np
from PyQt6.QtCore import QObject, QSignalBlocker, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMenu, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)
from matplotlib import colormaps
from matplotlib.colors import to_hex

from ..nexafs_fit.fit_export import export_fit_pass
from ..nexafs_fit.group import mean_spectrum
from ..nexafs_fit.model import (
    FitComponent, FitModel, Gaussian, IPStep, ParameterMode, StepForm, evaluate_model, gaussian_basis,
)
from ..nexafs_fit.persistence import Configuration, SavedAnalysis, load_configuration, save_analysis, save_configuration
from ..nexafs_fit.solver import FitCancelled, fit_pass1, fit_pass2, fit_reference
from .nexafs_fit_constraints import AdvancedConstraintsDialog
from .nexafs_fit_plot import NexafsFitPlot
from .nexafs_trend_dialogs import FitNumberDelegate
from .nexafs_fit_trends import NexafsTrends


_STAGES = {"model": "Model preview", "reference": "Reference", "pass1": "Pass 1", "pass2": "Pass 2"}
_FIT_FUNCTIONS = {"reference": fit_reference, "pass1": fit_pass1, "pass2": fit_pass2}
_MODEL_COLUMNS = ("Name", "Type", "Pos. (eV)", "Mode", "FWHM (eV)", "Mode", "Area/height", "Mode")
_MODEL_NUMBERS = (2, 4, 6)
_MODE_COLUMNS = {
    3: ("position_mode", "Center / position"),
    5: ("width_mode", "FWHM"),
    7: ("amplitude_mode", "IP height"),
}
_MODE_HELP = (
    "F = Fixed at the model value. S = Shared across spectra in Pass 2. I = Independent. "
    "S and I both vary in the reference fit and Pass 1."
)


def _set_number(item, value, *, amplitude=False):
    item.setData(Qt.ItemDataRole.UserRole, float(value))
    item.setText(f"{value:.3g}" if amplitude else f"{value:.2f}")


class _TableChoice(QComboBox):
    def wheelEvent(self, event):  # noqa: N802
        # Scrolling over the table must not change a constraint.
        event.ignore()


class _FitWorker(QObject):
    finished = pyqtSignal(object, str)

    def __init__(self, function, group, model, arguments):
        super().__init__()
        self.function = function
        self.group = group
        self.model = model
        self.arguments = arguments
        self.cancel_event = Event()

    @pyqtSlot()
    def run(self):
        try:
            result = self.function(
                self.group, self.model, cancelled=self.cancel_event.is_set, **self.arguments
            )
        except FitCancelled:
            self.finished.emit(None, "")
        except Exception as error:
            self.finished.emit(None, str(error) or type(error).__name__)
        else:
            self.finished.emit(result, "")


class NexafsFitDialog(QDialog):
    def __init__(self, group, *, analysis=None):
        super().__init__(None, Qt.WindowType.Window)
        self.group = group
        self.setWindowTitle("NEXAFS Fit / Trends")
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.resize(1150, 690)
        self._spectra = {spectrum.key: spectrum for spectrum in group.spectra}
        self._average_error = ""
        try:
            self._average = mean_spectrum((s.energy, s.intensity) for s in group.spectra)
        except ValueError as error:
            self._average = np.empty(0), np.empty(0)
            self._average_error = str(error)
        self.results = {}
        self.names = {}
        self._serials = {"Gaussian": 0, "IP": 0}
        self._colors = {}
        self._hidden = set()
        self._thread = None
        self._worker = None
        self._cancel_event = None
        self._close_requested = False
        self._fit_error = ""
        self._interval_error = ""

        low = max(s.normalization_range[0] for s in group.spectra)
        high = min(s.normalization_range[1] for s in group.spectra)
        self._default_range = (low, high)
        y = self._average[1]
        n = max(1, y.size // 10)
        height = max(0.0, float(np.median(y[-n:]) - np.median(y[:n]))) if y.size else 0.0
        step = IPStep(0.5 * (low + high), 0.1 * (high - low), height)
        if analysis is None:
            self.model = FitModel((self._new_component(step),), self._default_range)
        else:
            self.model = analysis.configuration.model
            self.results = dict(analysis.results)
            self._merge_names(analysis.configuration.names)

        self._build_ui(*self._fit_limits())
        self._fill_model_table()
        self._refresh()
        if analysis is not None:
            self.trends.set_experiment(analysis.configuration.experiment)
            stage = next((stage for stage in ("pass2", "pass1", "reference") if stage in self.results), None)
            if stage is not None:
                self._select_fit_result(self.results[stage])

    def _build_ui(self, low, high):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        files = QToolButton()
        files.setText("Analysis files")
        files.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(files)
        self.save_config_action = menu.addAction("Save configuration…")
        self.load_config_action = menu.addAction("Load configuration…")
        self.save_analysis_action = menu.addAction("Save complete analysis…")
        self.save_config_action.triggered.connect(lambda: self._save_file(complete=False))
        self.load_config_action.triggered.connect(self._load_config)
        self.save_analysis_action.triggered.connect(lambda: self._save_file(complete=True))
        files.setMenu(menu)
        tabs.setCornerWidget(files, Qt.Corner.TopRightCorner)
        layout.addWidget(tabs)
        fit = QWidget()
        tabs.addTab(fit, "Fit")
        fit_layout = QVBoxLayout(fit)

        selectors = QHBoxLayout()
        plot_side = QWidget()
        plot_layout = QVBoxLayout(plot_side)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addLayout(selectors)
        self.spectrum = QComboBox()
        self.spectrum.addItem("Group average", None)
        for key, spec in self._spectra.items():
            self.spectrum.addItem(spec.label, key)
            self.spectrum.setItemData(self.spectrum.count() - 1, key, Qt.ItemDataRole.ToolTipRole)
        self.spectrum.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.spectrum.setMinimumContentsLength(16)
        self.view = QComboBox()
        for key, label in _STAGES.items():
            self.view.addItem(label, key)
        selectors.addWidget(QLabel("Spectrum"))
        selectors.addWidget(self.spectrum, 1)
        self.previous_spectrum = self._spectrum_arrow(Qt.ArrowType.LeftArrow, "Previous spectrum", -1)
        self.next_spectrum = self._spectrum_arrow(Qt.ArrowType.RightArrow, "Next spectrum", 1)
        selectors.addWidget(self.previous_spectrum)
        selectors.addWidget(self.next_spectrum)
        display_controls = QHBoxLayout()
        display_controls.addStretch(1)
        display_controls.addWidget(QLabel("Display"))
        display_controls.addWidget(self.view)
        self.components_button = QToolButton()
        self.components_button.setText("Components")
        self.components_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.components_menu = QMenu(self.components_button)
        self.components_menu.aboutToShow.connect(self._build_components_menu)
        self.components_button.setMenu(self.components_menu)
        display_controls.addWidget(self.components_button)
        self.export_button = QPushButton("Export fits…")
        self.export_button.clicked.connect(self._export_displayed_pass)
        display_controls.addWidget(self.export_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        fit_layout.addWidget(splitter, 1)
        self.plot = NexafsFitPlot()
        plot_layout.addWidget(self.plot, 1)
        splitter.addWidget(plot_side)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(2, 0, 0, 0)
        side_layout.addLayout(display_controls)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([615, 510])

        self.model_panel = QWidget()
        side_layout.addWidget(self.model_panel, 1)
        model_layout = QVBoxLayout(self.model_panel)
        self.model_note = QLabel()
        self.model_note.setTextFormat(Qt.TextFormat.PlainText)
        self.model_note.setWordWrap(True)
        model_layout.addWidget(self.model_note)
        self.model_table = self._make_table()
        self._component_sort_column = 0
        self._component_sort_order = Qt.SortOrder.AscendingOrder
        self.model_table.horizontalHeader().sectionClicked.connect(self._sort_by_header)
        model_layout.addWidget(self.model_table, 1)
        delegate = FitNumberDelegate(self.model_table)
        delegate.number_edited.connect(self._edit_component)
        for column in _MODEL_NUMBERS:
            self.model_table.setItemDelegateForColumn(column, delegate)
        legend = QLabel("F Fixed   ·   S Shared (Pass 2)   ·   I Independent")
        legend.setToolTip(_MODE_HELP)
        model_layout.addWidget(legend)

        self.model_edits = QWidget()
        edits = QGridLayout(self.model_edits)
        edits.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.model_edits)
        self.add_gaussian = QPushButton("Add Gaussian")
        self.add_ip = QPushButton("Add IP")
        self.remove_component = QPushButton("Remove selected")
        edits.addWidget(self.add_gaussian, 0, 0)
        edits.addWidget(self.add_ip, 0, 1)
        edits.addWidget(self.remove_component, 1, 0)
        self.remove_component.setToolTip("Remove the selected component. The model requires at least one IP step.")
        self.advanced_constraints = QPushButton("Advanced constraints…")
        self.advanced_constraints.setToolTip("Set optional center and FWHM bounds for the selected component.")
        edits.addWidget(self.advanced_constraints, 1, 1)

        self.fit_controls = QWidget()
        controls = QGridLayout(self.fit_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.fit_controls)
        self.fit_min = self._energy_spin(low)
        self.fit_max = self._energy_spin(high)
        controls.addWidget(QLabel("Fit interval (eV)"), 0, 0)
        controls.addWidget(self.fit_min, 0, 1)
        controls.addWidget(self.fit_max, 0, 2)
        self.reference_button = QPushButton("Fit reference")
        self.reference_button.setToolTip("Fit the selected spectrum or group average as the reference.")
        self.pass1_button = QPushButton("Run Pass 1")
        self.pass2_button = QPushButton("Run Pass 2")
        self.pass1_button.setToolTip("Fit each spectrum independently.")
        self.pass2_button.setToolTip("Fit the group simultaneously using the configured constraints.")
        for column, button in enumerate((self.reference_button, self.pass1_button, self.pass2_button)):
            controls.addWidget(button, 1, column)
        status_row = QHBoxLayout()
        fit_layout.addLayout(status_row)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        status_row.addWidget(self.summary, 1)
        self.details_button = QPushButton("Diagnostics…")
        status_row.addWidget(self.details_button)
        self.activity = QProgressBar()
        self.activity.setRange(0, 0)
        self.activity.setMaximumWidth(95)
        self.activity.setTextVisible(False)
        status_row.addWidget(self.activity)
        self.cancel_button = QPushButton("Cancel fit")
        status_row.addWidget(self.cancel_button)

        self.trends = NexafsTrends(self.group)
        self.trends.spectrum_selected.connect(self._select_spectrum)
        tabs.addTab(self.trends, "Trends")

        self.spectrum.currentIndexChanged.connect(self._show_selection)
        self.view.currentIndexChanged.connect(self._show_selection)
        self.model_table.cellChanged.connect(self._edit_component)
        self.model_table.currentCellChanged.connect(self._select_plot_component)
        self.plot.component_edited.connect(self._drag_component)
        self.add_gaussian.clicked.connect(self._add_gaussian)
        self.add_ip.clicked.connect(self._add_ip)
        self.remove_component.clicked.connect(self._remove_component)
        self.advanced_constraints.clicked.connect(self._edit_advanced_constraints)
        self.fit_min.valueChanged.connect(self._edit_interval)
        self.fit_max.valueChanged.connect(self._edit_interval)
        self.reference_button.clicked.connect(lambda: self._start_fit("reference"))
        self.pass1_button.clicked.connect(lambda: self._start_fit("pass1"))
        self.pass2_button.clicked.connect(lambda: self._start_fit("pass2"))
        self.cancel_button.clicked.connect(self._cancel_fit)
        self.details_button.clicked.connect(self._show_details)

    @staticmethod
    def _energy_spin(value):
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(-1e8, 1e8)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        spin.setSingleStep(0.1)
        return spin

    @staticmethod
    def _make_table():
        table = QTableWidget(0, len(_MODEL_COLUMNS))
        table.setHorizontalHeaderLabels(_MODEL_COLUMNS)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_MODEL_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeaderItem(0).setToolTip("Click to sort by component number.")
        table.horizontalHeaderItem(2).setToolTip("Click to sort by the displayed Gaussian center or IP position in eV.")
        for column, (_, label) in _MODE_COLUMNS.items():
            table.horizontalHeaderItem(column).setToolTip(f"{label} mode. {_MODE_HELP}")
        return table

    def _new_component(self, values):
        kind = "Gaussian" if isinstance(values, Gaussian) else "IP"
        while True:
            self._serials[kind] += 1
            key = f"{kind} {self._serials[kind]}"
            if key not in self.names:
                break
        self._merge_names({key: key})
        return FitComponent(key, values)

    def _merge_names(self, names):
        for key, name in names.items():
            self.names[key] = name
            if key not in self._colors:
                self._colors[key] = colormaps["tab20"].colors[len(self._colors) % 20]

    def _fill_model_table(self):
        table = self.model_table
        selected = max(1, table.currentRow())
        specs = self.model.components
        with QSignalBlocker(table):
            table.setRowCount(0)
            table.setRowCount(len(specs) + 1)
            self._add_all_mode_row(table)
            for row, spec in enumerate(specs, 1):
                component = spec.initial
                gaussian = isinstance(component, Gaussian)
                kind = "Gaussian" if gaussian else f"IP ({component.form})"
                name = QTableWidgetItem(self.names[spec.key])
                name.setToolTip(self.names[spec.key])
                marker = QPixmap(10, 10)
                marker.fill(QColor(to_hex(self._colors[spec.key])))
                name.setIcon(QIcon(marker))
                table.setItem(row, 0, name)
                kind_item = QTableWidgetItem(kind)
                kind_item.setFlags(kind_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, 1, kind_item)

                values = (
                    (component.center, component.fwhm, component.area) if gaussian
                    else (component.position, component.fwhm, component.height)
                )
                for index, (column, value) in enumerate(zip(_MODEL_NUMBERS, values)):
                    item = QTableWidgetItem()
                    _set_number(item, value, amplitude=index == 2)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if index == 1 and not gaussian:
                        item.setToolTip("FWHM of the IP-step derivative")
                    if index == 2:
                        item.setToolTip("Integrated Gaussian area" if gaussian else "IP step height")
                    table.setItem(row, column, item)

                self._add_mode_cells(table, row, spec, gaussian)
                if not gaussian:
                    forms = (("IP (erf)", StepForm.ERF), ("IP (atan)", StepForm.ARCTAN))
                    combo = self._table_choice(forms, component.form, "IP step form",
                                               "Choose the error-function or arctangent IP step.")
                    combo.currentIndexChanged.connect(
                        lambda _, key=spec.key, choice=combo: self._edit_step_form(key, choice.currentData())
                    )
                    table.setCellWidget(row, 1, combo)
        table.selectRow(min(selected, len(specs)))

    def _sort_by_header(self, column):
        if column in (0, 2):
            descending = column == self._component_sort_column and self._component_sort_order == Qt.SortOrder.AscendingOrder
            self._component_sort_column = column
            self._component_sort_order = Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
            self._sort_component_rows()
        self.model_table.horizontalHeader().setSortIndicator(self._component_sort_column, self._component_sort_order)

    def _sort_component_rows(self):
        table = self.model_table
        header = table.verticalHeader()
        rows = range(1, table.rowCount())
        reverse = self._component_sort_order == Qt.SortOrder.DescendingOrder
        if self._component_sort_column == 2:
            ordered = sorted(rows, key=lambda row: table.item(row, 2).data(Qt.ItemDataRole.UserRole), reverse=reverse)
        else:
            def number_order(row):
                spec = self.model.components[row - 1]
                kind = "Gaussian" if isinstance(spec.initial, Gaussian) else "IP"
                prefix, _, serial = spec.key.rpartition(" ")
                number = int(serial) if prefix == kind and serial.isdecimal() else float("inf")
                return isinstance(spec.initial, Gaussian), number

            ordered = sorted(rows, key=number_order, reverse=reverse)

        # The logical row still identifies the same component for edits and selections.
        for visual_row, logical_row in enumerate(ordered, 1):
            previous = header.visualIndex(logical_row)
            if previous != visual_row:
                header.moveSection(previous, visual_row)

    def _show_table_values(self, fitted):
        # Keep the editable widgets bound to the model. Only the displayed
        # numbers follow the selected spectrum and result.
        with QSignalBlocker(self.model_table):
            for row, spec in enumerate(self.model.components, 1):
                component = fitted.get(spec.key)
                has_fit = type(component) is type(spec.initial)
                if not has_fit:
                    values = spec.values
                elif isinstance(component, Gaussian):
                    values = component.center, component.fwhm, component.area
                else:
                    values = component.position, component.fwhm, component.height
                for index, (column, value) in enumerate(zip(_MODEL_NUMBERS, values)):
                    item = self.model_table.item(row, column)
                    _set_number(item, value, amplitude=index == 2)
                    source = "Fitted value" if has_fit else "Starting value"
                    detail = " · FWHM of the IP-step derivative" if index == 1 and isinstance(spec.initial, IPStep) else ""
                    item.setToolTip(source + detail)
        self._sort_component_rows()

    @staticmethod
    def _table_choice(choices, current, label, help_text):
        combo = _TableChoice()
        combo.setAccessibleName(label)
        combo.setToolTip(help_text)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for text, value in choices:
            combo.addItem(text, value)
            combo.setItemData(combo.count() - 1, value.value.title(), Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(combo.findData(current))
        return combo

    @staticmethod
    def _mode_choices(field):
        return ((mode.value[0].upper(), mode) for mode in ParameterMode
                if field != "amplitude_mode" or mode != ParameterMode.FIXED)

    def _add_all_mode_row(self, table):
        label = QTableWidgetItem("All")
        label.setFlags(Qt.ItemFlag.ItemIsEnabled)
        table.setItem(0, 0, label)
        for column, (field, name) in _MODE_COLUMNS.items():
            target = "all IP steps" if field == "amplitude_mode" else "all components"
            combo = self._table_choice(self._mode_choices(field), None, f"All {name} modes",
                                       f"Set {name.lower()} mode for {target}. {_MODE_HELP}")
            combo.setPlaceholderText("—")
            combo.currentIndexChanged.connect(
                lambda _, col=column, choice=combo: self._edit_all_modes(col, choice.currentData())
            )
            table.setCellWidget(0, column, combo)
            self._sync_all_mode(column)

    def _sync_all_mode(self, column):
        field, _ = _MODE_COLUMNS[column]
        modes = {getattr(spec, field) for spec in self.model.components
                 if field != "amplitude_mode" or isinstance(spec.initial, IPStep)}
        combo = self.model_table.cellWidget(0, column)
        with QSignalBlocker(combo):
            combo.setCurrentIndex(combo.findData(next(iter(modes))) if len(modes) == 1 else -1)

    def _edit_all_modes(self, column, mode):
        if mode is None:
            return
        field, _ = _MODE_COLUMNS[column]
        components = tuple(
            replace(spec, **{field: mode})
            if field != "amplitude_mode" or isinstance(spec.initial, IPStep) else spec
            for spec in self.model.components
        )
        if components == self.model.components:
            return
        self.model = replace(self.model, components=components)
        for row in range(1, self.model_table.rowCount()):
            combo = self.model_table.cellWidget(row, column)
            if combo is not None:
                with QSignalBlocker(combo):
                    combo.setCurrentIndex(combo.findData(mode))
        self._fit_error = ""
        self._show_model_edit()

    def _add_mode_cells(self, table, row, spec, gaussian):
        for column, (field, label) in _MODE_COLUMNS.items():
            if field == "amplitude_mode" and gaussian:
                item = QTableWidgetItem("I")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip("Gaussian areas are fitted independently.")
                table.setItem(row, column, item)
                continue
            combo = self._table_choice(
                self._mode_choices(field),
                getattr(spec, field), f"{label} mode", _MODE_HELP,
            )
            combo.currentIndexChanged.connect(
                lambda _, key=spec.key, name=field, choice=combo:
                self._edit_mode(key, name, choice.currentData())
            )
            table.setCellWidget(row, column, combo)

    def _edit_mode(self, key, field, mode):
        row, spec = next((row, spec) for row, spec in enumerate(self.model.components) if spec.key == key)
        self._apply_table_setting(row, replace(spec, **{field: mode}))
        column = next(column for column, (name, _) in _MODE_COLUMNS.items() if name == field)
        self._sync_all_mode(column)

    def _edit_step_form(self, key, form):
        row, spec = next((row, spec) for row, spec in enumerate(self.model.components) if spec.key == key)
        self._apply_table_setting(row, replace(spec, initial=replace(spec.initial, form=StepForm(form))))

    def _replace_component(self, row, spec):
        components = self.model.components
        self.model = replace(self.model, components=(*components[:row], spec, *components[row + 1:]))

    def _apply_table_setting(self, row, spec):
        if self.model.components[row] != spec:
            self._replace_component(row, spec)
            self._fit_error = ""
            self._show_model_edit()

    def _select_plot_component(self, row, *_):
        self.plot.selected_key = self.model.components[row - 1].key if 1 <= row <= len(self.model.components) else None

    def _drag_component(self, key, position, amplitude):
        if self._thread is not None:
            return
        for row, spec in enumerate(self.model.components):
            if spec.key == key:
                gaussian = isinstance(spec.initial, Gaussian)
                fields = {}
                if position is not None:
                    fields["center" if gaussian else "position"] = position
                if amplitude is not None:
                    fields["area" if gaussian else "height"] = amplitude
                updated = replace(spec, initial=replace(spec.initial, **fields))
                self._apply_table_setting(row, updated)
                self.model_table.selectRow(row + 1)
                return

    def _show_model_edit(self):
        with QSignalBlocker(self.view):
            self.view.setCurrentIndex(self.view.findData("model"))
        self._refresh()

    def _edit_component(self, row, column, entered=None):
        if row < 1 or (column != 0 and column not in _MODEL_NUMBERS):
            return
        spec = self.model.components[row - 1]
        item = self.model_table.item(row, column)
        text = (item.text() if entered is None else entered).strip()
        try:
            if column == 0:
                if not text:
                    raise ValueError("Enter a component name.")
                self.names[spec.key] = text
            else:
                gaussian = isinstance(spec.initial, Gaussian)
                fields = ("center", "fwhm", "area") if gaussian else ("position", "fwhm", "height")
                index = _MODEL_NUMBERS.index(column)
                value = float(text)
                if value != item.data(Qt.ItemDataRole.UserRole):
                    initial = replace(spec.initial, **{fields[index]: value})
                    updated = replace(spec, initial=initial)
                    if updated != spec:
                        self._replace_component(row - 1, updated)
                        self._fit_error = ""
                        self._show_model_edit()
                        return
        except ValueError as error:
            self._fit_error = str(error)
        else:
            self._fit_error = ""
        with QSignalBlocker(self.model_table):
            if column == 0:
                item.setText(self.names[spec.key])
                item.setToolTip(self.names[spec.key])
        self._refresh()

    def _edit_interval(self):
        low, high = self.fit_min.value(), self.fit_max.value()
        self._interval_error = "" if low < high else "Fit interval minimum must be below its maximum."
        if not self._interval_error:
            self.model = replace(self.model, fit_range=(low, high))
        self._fit_error = ""
        self._refresh()

    def _selection_data(self):
        key = self.spectrum.currentData()
        if key is None:
            return self._average
        spec = self._spectra[key]
        return spec.energy, spec.intensity

    def _fit_limits(self):
        return self.model.fit_range or self._default_range

    def _add_gaussian(self):
        low, high = self._fit_limits()
        width = (high - low) / 18
        x, y = self._selection_data()
        mask = np.isfinite(y) & (x >= low) & (x <= high)
        center, area = 0.5 * (low + high), 0.0
        if mask.any():
            x = x[mask]
            excess = y[mask] - evaluate_model(x, [spec.initial for spec in self.model.components])
            peak = int(np.argmax(excess))
            center = float(x[peak])
            area = max(0.0, float(excess[peak] / gaussian_basis(center, center, width)))
        self._append_component(Gaussian(center, width, area))

    def _add_ip(self):
        low, high = self._fit_limits()
        self._append_component(IPStep(0.5 * (low + high), 0.1 * (high - low), 0.0))

    def _append_component(self, values):
        self.model = replace(self.model, components=(*self.model.components, self._new_component(values)))
        self._fill_model_table()
        self.model_table.selectRow(self.model_table.rowCount() - 1)
        self._fit_error = ""
        self._show_model_edit()

    def _remove_component(self):
        row = self.model_table.currentRow() - 1
        if row < 0:
            return
        specs = self.model.components
        try:
            self.model = replace(self.model, components=specs[:row] + specs[row + 1:])
        except ValueError as error:
            self._fit_error = str(error)
        else:
            self._fit_error = ""
            self._fill_model_table()
            self.model_table.selectRow(min(row + 1, self.model_table.rowCount() - 1))
            self._show_model_edit()
            return
        self._refresh()

    def _edit_advanced_constraints(self):
        selected = max(0, self.model_table.currentRow() - 1)
        dialog = AdvancedConstraintsDialog(self.model.components, self.names, self, selected_row=selected)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.model = replace(self.model, components=dialog.components)
            self._fill_model_table()
            self._fit_error = ""
            self._show_model_edit()

    def _save_file(self, *, complete):
        title = "Save complete NEXAFS analysis" if complete else "Save NEXAFS fit configuration"
        pattern = "NEXAFS analysis (*.h5 *.hdf5)" if complete else "NEXAFS configuration (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, title, "", pattern)
        if not path:
            return
        config = Configuration(self.model, dict(self.names), self.trends.current_experiment())
        try:
            if complete:
                if not path.lower().endswith((".h5", ".hdf5")):
                    path += ".h5"
                save_analysis(path, SavedAnalysis(self.group, config, dict(self.results)))
            else:
                save_configuration(path if path.lower().endswith(".json") else path + ".json", config, self.group)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, title, str(error))

    def _export_displayed_pass(self):
        stage = self.view.currentData()
        result = self.results.get(stage)
        if stage not in ("pass1", "pass2") or result is None or self._thread is not None:
            return
        label = _STAGES[stage]
        title = f"Export {label} fits"
        outdated = self._outdated(result)
        buttons = QMessageBox.StandardButton
        if outdated and QMessageBox.question(
            self, title, f"{label} is outdated. Export it with that status?",
            buttons.Yes | buttons.No, buttons.No,
        ) != buttons.Yes:
            return

        include_provisional = False
        provisional_count = sum(row.usable and not row.diagnostics.converged for row in result.spectra)
        if provisional_count:
            answer = QMessageBox.question(
                self, title,
                f"{label} has {provisional_count} provisional fit(s). Include their fitted values? "
                "Choose No to export their processed data and status only.",
                buttons.Yes | buttons.No | buttons.Cancel, buttons.No,
            )
            if answer == buttons.Cancel:
                return
            include_provisional = answer == buttons.Yes

        dialog = QFileDialog(self, title)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("NEXAFS fit archive (*.zip)")
        dialog.setDefaultSuffix("zip")
        dialog.selectFile(f"nexafs-{stage}-fits.zip")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            export_fit_pass(
                dialog.selectedFiles()[0], self.group, result, self.names, self.trends.current_experiment(),
                outdated=outdated, include_outdated=outdated, include_provisional=include_provisional,
            )
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, title, str(error))

    def _load_config(self):
        title = "Load NEXAFS fit configuration"
        path, _ = QFileDialog.getOpenFileName(self, title, "", "NEXAFS configuration (*.json)")
        if not path:
            return
        try:
            config = load_configuration(path)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, title, str(error))
            return
        # Preserve names attached to existing fits when an imported configuration
        # reuses a local identifier for a differently named component.
        fitted_kinds = {spec.key: type(spec.initial) for result in self.results.values()
                        for spec in result.model.components}
        claimed = set(self.names) | set(config.names)
        components, names = [], {}
        for spec in config.model.components:
            key, name = spec.key, config.names[spec.key]
            if key in fitted_kinds and (self.names[key] != name or fitted_kinds[key] is not type(spec.initial)):
                index = 2
                while f"{key} ({index})" in claimed:
                    index += 1
                key = f"{key} ({index})"
                claimed.add(key)
            components.append(replace(spec, key=key))
            names[key] = name
        self.model = replace(config.model, components=tuple(components))
        self._merge_names(names)
        low, high = self._fit_limits()
        with QSignalBlocker(self.fit_min), QSignalBlocker(self.fit_max):
            self.fit_min.setValue(low)
            self.fit_max.setValue(high)
        self._interval_error = self._fit_error = ""
        self._fill_model_table()
        self.trends.set_experiment(config.experiment)
        self._refresh()
        unmatched = len(config.experiment.values) - len(self.trends.experiment.values)
        if unmatched:
            QMessageBox.information(self, title, f"{unmatched} experimental values had no matching spectrum identifier.")

    def _spectrum_arrow(self, arrow, label, offset):
        button = QToolButton()
        button.setArrowType(arrow)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(lambda: self.spectrum.setCurrentIndex(self.spectrum.currentIndex() + offset))
        return button

    def _select_spectrum(self, key):
        self.spectrum.setCurrentIndex(self.spectrum.findData(key))

    @staticmethod
    def _reference_starting_model(result):
        row = result.spectra[0]
        if not row.usable or not row.diagnostics.converged:
            return result.model
        components = []
        for spec, fitted in zip(result.model.components, row.components, strict=True):
            # Conversion from the solver's scaled coordinates can leave an
            # explicit bound a fraction of a float away from the result.
            position = fitted.center if isinstance(fitted, Gaussian) else fitted.position
            width = fitted.fwhm
            for index, limit in enumerate(spec.position_bounds):
                if limit is not None:
                    position = (max if index == 0 else min)(position, limit)
            for index, limit in enumerate(spec.width_bounds):
                if limit is not None:
                    width = (max if index == 0 else min)(width, limit)
            field = "center" if isinstance(fitted, Gaussian) else "position"
            components.append(replace(spec, initial=replace(fitted, **{field: position, "fwhm": width})))
        return replace(result.model, components=tuple(components))

    def _outdated(self, result):
        if self._interval_error:
            return True
        if result.model == self.model:
            return False
        return result.stage != "reference" or self._reference_starting_model(result) != self.model

    def _update_controls(self):
        busy = self._thread is not None
        self.model_panel.setEnabled(not busy)
        self.fit_controls.setEnabled(not busy)
        self.load_config_action.setEnabled(not busy)
        self.save_config_action.setEnabled(not self._interval_error)
        self.save_analysis_action.setEnabled(not self._interval_error)
        for button in (self.reference_button, self.pass1_button, self.pass2_button):
            button.setEnabled(not self._interval_error)
        self.activity.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy and not self._cancel_event.is_set())
        with QSignalBlocker(self.view):
            for stage in ("reference", "pass1", "pass2"):
                index = self.view.findData(stage)
                result = self.results.get(stage)
                label = _STAGES[stage]
                if result is not None and self._outdated(result):
                    label += " (outdated)"
                self.view.setItemText(index, label)
                self.view.model().item(index).setEnabled(result is not None)

    def _refresh(self):
        self._update_controls()
        self.trends.set_fits(self.model, self.names, self.results,
                            {stage for stage, result in self.results.items() if self._outdated(result)})
        self._show_selection()

    def _build_components_menu(self):
        self.components_menu.clear()
        result = self.results.get(self.view.currentData())
        specs = self.model.components if result is None else result.model.components
        for spec in specs:
            action = self.components_menu.addAction(self.names[spec.key])
            action.setCheckable(True)
            action.setChecked(spec.key not in self._hidden)
            action.toggled.connect(lambda visible, key=spec.key: self._toggle_component(key, visible))

    def _toggle_component(self, key, visible):
        if visible:
            self._hidden.discard(key)
        else:
            self._hidden.add(key)
        self._show_selection()

    def _show_selection(self):
        index = self.spectrum.currentIndex()
        self.previous_spectrum.setEnabled(index > 0)
        self.next_spectrum.setEnabled(index < self.spectrum.count() - 1)
        key = self.spectrum.currentData()
        self.trends.set_selected_spectrum(key)
        stage = self.view.currentData()
        result = self.results.get(stage)
        is_pass = stage in ("pass1", "pass2") and result is not None
        self.export_button.setText(f"Export {_STAGES[stage]}…" if is_pass else "Export fits…")
        self.export_button.setEnabled(is_pass and self._thread is None)
        self.export_button.setToolTip(
            f"Export {_STAGES[stage]} fits for all spectra as a CSV and JSON ZIP archive."
            if is_pass else "Display completed Pass 1 or Pass 2 results to export fits."
        )
        energy, intensity = self._selection_data()
        limits = self._fit_limits() if result is None else result.fit_range
        fit_energy = prediction = residual = None
        components = ()
        specs = self.model.components if result is None else result.model.components
        curves = ()
        details = []
        values_note = "Model starting values"
        if result is None:
            mask = (energy >= limits[0]) & (energy <= limits[1])
            fit_energy = energy[mask]
            preview = tuple(spec.initial for spec in specs)
            prediction = evaluate_model(fit_energy, preview)
            curves = self._component_curves(specs, [preview], fit_energy)
            status = self._average_error if key is None and self._average_error else (
                "Model preview. Fit the selected spectrum or group average to create a reference."
            )
        elif key is None and stage != "reference":
            values_note = "Select an individual spectrum for its fitted parameter values."
            if all(row.components for row in result.spectra):
                try:
                    fit_energy, observed = mean_spectrum((row.energy, row.observed) for row in result.spectra)
                except ValueError as error:
                    status = f"No average overlay: {error}"
                else:
                    all_values = [row.components for row in result.spectra]
                    prediction = np.mean([evaluate_model(fit_energy, values) for values in all_values], axis=0)
                    residual = observed - prediction
                    curves = self._component_curves(specs, all_values, fit_energy)
                    count = sum(row.diagnostics.converged for row in result.spectra)
                    status = f"Mean of fitted curves. {count}/{len(result.spectra)} spectra converged."
            else:
                count = sum(bool(row.components) for row in result.spectra)
                status = f"No average overlay. Fitted curves are available for {count}/{len(result.spectra)} spectra."
            for row in result.spectra:
                if not row.diagnostics.converged:
                    details.append(f"{row.label}: {row.diagnostics.message}")
        else:
            row = next((scan for scan in result.spectra if scan.key == key), None)
            if row is None:
                target = result.spectra[0].label
                status = values_note = f"Reference was fitted to {target}. Select that spectrum to inspect it."
            else:
                components = row.components
                values_note = f"{row.label} · fitted values" if components else f"{row.label} · no fitted values"
                if components:
                    fit_energy, prediction, residual = row.energy, row.prediction, row.residual
                    curves = self._component_curves(specs, [components], fit_energy)
                status = self._describe_diagnostics(row.diagnostics)
                details.extend(self._diagnostic_details(row.diagnostics))
        if result is not None and result.global_diagnostics is not None:
            diagnostics = result.global_diagnostics
            status += f" Global fit: {self._describe_diagnostics(diagnostics)}"
            details.extend(self._diagnostic_details(diagnostics))
        if result is not None and self._outdated(result):
            status = f"Outdated fit. {status}"
            values_note = f"Outdated fit · {values_note}"
        fitted = {spec.key: component for spec, component in zip(specs, components)}
        self._show_table_values(fitted)
        if result is not None:
            values_note += " · Edits update the common starting model."
        editable_components = {}
        if self._thread is None:
            current = {spec.key: spec for spec in self.model.components}
            displayed = preview if result is None else components
            for spec, component in zip(specs, displayed):
                target = current.get(spec.key)
                if target is not None and type(target.initial) is type(component):
                    editable_components[spec.key] = component, target.position_bounds
        self.model_note.setText(values_note)
        self._details = "\n".join(dict.fromkeys(details))
        self.details_button.setEnabled(bool(self._details))
        if self._thread is not None:
            status = "Cancelling fit…" if self._cancel_event.is_set() else self._running_message
        self.summary.setText(self._interval_error or self._fit_error or status)
        self.plot.display(
            (key, stage, result), (energy, intensity), fit_energy, prediction, residual,
            curves, limits, spectrum_title=self.spectrum.currentText(), preview=result is None,
            editable_components=editable_components,
        )

    def _component_curves(self, specs, component_sets, energy):
        return tuple(
            (spec.key, self.names[spec.key], self._colors[spec.key],
             "-." if isinstance(spec.initial, IPStep) else "--",
             np.mean([component.evaluate(energy) for component in values], axis=0))
            for spec, values in zip(specs, zip(*component_sets))
            if spec.key not in self._hidden
        )

    @staticmethod
    def _describe_diagnostics(diagnostics):
        status = {"Converged": "Converged.", "Provisional": "Provisional fit (not converged).",
                  "Failed": "Fit failed."}[diagnostics.outcome]
        if diagnostics.rms is not None:
            status += f" RMS {diagnostics.rms:.4g}."
        if diagnostics.bounds_reached:
            status += f" At or near bounds: {len(diagnostics.bounds_reached)}."
        if diagnostics.warnings:
            status += f" Warnings: {len(diagnostics.warnings)}."
        return status

    @staticmethod
    def _diagnostic_details(diagnostics):
        lines = [diagnostics.message]
        for label, value in (
            ("Solver", diagnostics.solver), ("SciPy status", diagnostics.status),
            ("Function evaluations", diagnostics.nfev), ("Jacobian evaluations", diagnostics.njev),
            ("Iterations", diagnostics.nit), ("Optimality", diagnostics.optimality), ("Solver cost", diagnostics.cost),
        ):
            if value is not None:
                lines.append(f"{label}: {value:.6g}" if isinstance(value, float) else f"{label}: {value}")
        lines.extend((*diagnostics.bounds_reached, *diagnostics.warnings))
        if diagnostics.condition_number is not None:
            lines.append(f"Column-normalized Jacobian condition number: {diagnostics.condition_number:.4g}")
        return lines

    def _show_details(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("NEXAFS Fit Diagnostics")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(self.summary.text())
        dialog.setDetailedText(self._details)
        dialog.exec()

    def _start_fit(self, stage):
        if self._thread is not None or self._interval_error:
            return
        arguments = {}
        if stage == "reference":
            arguments["spectrum_key"] = self.spectrum.currentData()
        else:
            seed_stage = "reference" if stage == "pass1" else "pass1"
            seed = self.results.get(seed_stage)
            # A promoted reference already supplies its fitted starting values.
            # The backend accepts a separate seed only for an identical model.
            if seed is not None and seed.model == self.model:
                arguments[seed_stage] = seed

        thread = QThread(self)
        worker = _FitWorker(_FIT_FUNCTIONS[stage], self.group, self.model, arguments)
        self._thread, self._worker = thread, worker
        self._cancel_event = worker.cancel_event
        self._fit_error = ""
        self._running_message = f"Fitting {_STAGES[stage]}…"
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._fit_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear_worker)
        thread.finished.connect(thread.deleteLater)
        self._refresh()
        thread.start()

    @pyqtSlot(object, str)
    def _fit_finished(self, result, error):
        if self._cancel_event.is_set():
            self._fit_error = "Fit cancelled. Previous results are available."
        elif error:
            self._fit_error = error
        elif result is not None:
            self.results[result.stage] = result
            if result.stage == "reference":
                self.model = self._reference_starting_model(result)
                self._fill_model_table()
            self._update_controls()
            self._select_fit_result(result)

    def _select_fit_result(self, result):
        with QSignalBlocker(self.spectrum):
            if result.stage == "reference":
                key = result.spectra[0].key
                self.spectrum.setCurrentIndex(0 if key is None else self.spectrum.findData(key))
            elif self.spectrum.currentData() is None:
                row = next((row for row in result.spectra if row.components), None)
                if row is not None:
                    self.spectrum.setCurrentIndex(self.spectrum.findData(row.key))
        self.view.setCurrentIndex(self.view.findData(result.stage))

    @pyqtSlot()
    def _clear_worker(self):
        self._thread = self._worker = self._cancel_event = None
        if self._close_requested:
            self.close()
        else:
            self._refresh()

    def _cancel_fit(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self._refresh()

    def reject(self):
        if self._thread is not None:
            self._close_requested = True
            self._cancel_fit()
            return
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        if self._thread is not None:
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
