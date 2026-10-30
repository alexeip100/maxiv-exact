"""EXACT fluorescence-map Lines viewer and exploratory independent fitting."""
from __future__ import annotations
from pathlib import Path
from copy import deepcopy
import csv
import h5py
import json
import math
from scipy.signal import find_peaks, peak_widths
import numpy as np
from PyQt6.QtCore import Qt, QPoint, QRect, QObject, QThread, QTimer, pyqtSignal
from .fluorescence_colormap_dialog import open_colormap, available_colormaps
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,QPushButton,
    QHeaderView, QStyle, QStyleOptionButton,
    QDoubleSpinBox,QSpinBox,QAbstractSpinBox,QComboBox,QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,
    QCheckBox,QSplitter,QFormLayout,QGroupBox,QGridLayout,QSizePolicy,QMenuBar,QMenu,QProgressBar,QDialogButtonBox)
from PyQt6.QtGui import QPainter
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from .fluorescence_toolbar import FluorescenceToolbar
from ..fluorescence_energy import match_master, read_energy, available_entries, detector_entry_id
from ..hdf5_loading import split_tree_payload
from ..fluorescence_map import (load_fluorescence_map,fit_detector_spectrum,evaluate_model,
                                save_fit_configuration,load_fit_configuration,fit_fluorescence_batch,batch_row_for_incident,
                                extract_fitted_fy,reconstruct_component,integrate_fluorescence_roi)




class _PeakToggleHeader(QHeaderView):
    """Tri-state master checkboxes for the two peak freedom columns."""

    toggleColumn = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.states = {4: Qt.CheckState.Unchecked, 5: Qt.CheckState.Unchecked}

    def set_state(self, column, state):
        if self.states.get(column) != state:
            self.states[column] = state
            self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)
        if logicalIndex not in self.states:
            return
        option = QStyleOptionButton()
        option.state = QStyle.StateFlag.State_Enabled
        state = self.states[logicalIndex]
        if state == Qt.CheckState.Checked:
            option.state |= QStyle.StateFlag.State_On
        elif state == Qt.CheckState.PartiallyChecked:
            option.state |= QStyle.StateFlag.State_NoChange
        else:
            option.state |= QStyle.StateFlag.State_Off
        indicator = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        option.rect = QRect(rect.left() + 5, rect.center().y() - indicator.height() // 2,
                            indicator.width(), indicator.height())
        painter.save()
        self.style().drawControl(QStyle.ControlElement.CE_CheckBox, option, painter, self)
        painter.restore()

    def mousePressEvent(self, event):
        column = self.logicalIndexAt(event.position().toPoint())
        if column in self.states and event.button() == Qt.MouseButton.LeftButton:
            self.toggleColumn.emit(column, self.states[column] != Qt.CheckState.Checked)
            event.accept()
            return
        super().mousePressEvent(event)


class _BatchWorker(QObject):
    updated=pyqtSignal(int,int)
    finished=pyqtSignal(object)
    failed=pyqtSignal(str)

    def __init__(self, counts, energies, peaks, kwargs):
        super().__init__()
        self.counts=counts;self.energies=energies;self.peaks=peaks;self.kwargs=kwargs
        import threading
        self.cancel_event=threading.Event()

    def run(self):
        try:
            # Qt worker thread already separates fitting from UI. Prevent BLAS
            # parallelism from occupying every core during long least-squares fits.
            try:
                from threadpoolctl import threadpool_limits
            except ImportError:
                from contextlib import nullcontext
                limiter=nullcontext()
            else:
                limiter=threadpool_limits(limits=1)
            with limiter:
                result=fit_fluorescence_batch(self.counts,self.energies,self.peaks,
                                              progress=lambda done,total:self.updated.emit(done,total),cancelled=self.cancel_event.is_set,**self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            if str(e)=="Batch fit aborted":self.failed.emit("ABORTED")
            else:self.failed.emit(str(e))


class FLBatchTrends(QDialog):
    """Independent, non-modal batch result inspection window."""
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window,True)
        self.setWindowTitle('Fluorescence peak trends — EXACT')
        self.resize(960,600)
        layout=QVBoxLayout(self)
        toolbar=QHBoxLayout();layout.addLayout(toolbar)
        toolbar.addWidget(QLabel('Plot:'))
        self.kind=QComboBox();self.kind.addItems(['Peak areas','Peak centers','Peak FWHM','Fit deviance','Background'])
        toolbar.addWidget(self.kind)
        self._labels=QHBoxLayout();toolbar.addLayout(self._labels)
        toolbar.addWidget(QLabel('Peak:'))
        self.trend_peak=QComboBox();self.trend_peak.setMinimumContentsLength(18);self.trend_peak.setMinimumWidth(175);self.trend_peak.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);toolbar.addWidget(self.trend_peak)
        toolbar.addWidget(QLabel('Constraint:'))
        self.trend_parameter=QComboBox();self.trend_parameter.addItems(['Center','FWHM']);toolbar.addWidget(self.trend_parameter)
        self.trend_degree=QComboBox();self.trend_degree.addItems(['None','Polynomial 0','Polynomial 1','Polynomial 2']);toolbar.addWidget(self.trend_degree)
        self.set_trend=QPushButton('Set trend');toolbar.addWidget(self.set_trend)
        self.set_trend.clicked.connect(self.apply_trend)
        self.run_pass2=QPushButton('Run Pass 2');toolbar.addWidget(self.run_pass2)
        self.run_pass2.clicked.connect(lambda: self.parent().start_batch_fit(second_pass=True))
        toolbar.addStretch(1)
        self.figure=Figure(figsize=(10,6));self.canvas=FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas,self));layout.addWidget(self.canvas,1)
        self.checks=[]
        self.trend_configs={}
        self.trend_peak.currentIndexChanged.connect(self.sync_trend_choice)
        self.trend_parameter.currentIndexChanged.connect(self.sync_trend_choice)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def sync_trend_choice(self,*_):
        j=self.trend_peak.currentIndex()-1
        key=(j,'center' if self.trend_parameter.currentIndex()==0 else 'width')
        chosen=self.trend_configs.get(key,None)
        self.trend_degree.blockSignals(True)
        self.trend_degree.setCurrentIndex(0 if chosen is None else chosen+1)
        self.trend_degree.blockSignals(False)

    def apply_trend(self):
        index=self.trend_peak.currentIndex()
        if index<0:return
        count=len(self.parent().peaks)
        param='center' if self.trend_parameter.currentIndex()==0 else 'width'
        degree=self.trend_degree.currentIndex()-1
        for j in (range(count) if index==0 else [index-1]):
            key=(j,param)
            if degree<0:self.trend_configs.pop(key,None)
            else:self.trend_configs[key]=degree
        self.refresh()

    def refresh(self,*_):
        source=self.parent()
        batch=source.active_batch()
        if batch is None:return
        peaks=[dict(p, name=(source.peaks[i]['name'] if i<len(source.peaks) and source.peaks[i].get('id')==p.get('id') else p['name'])) for i,p in enumerate(batch['peaks'])]
        if self.trend_peak.count()!=len(peaks)+1 or any(self.trend_peak.itemText(i+1)!=p['name'] for i,p in enumerate(peaks)):
            old=self.trend_peak.currentIndex();self.trend_peak.blockSignals(True)
            self.trend_peak.clear();self.trend_peak.addItems(['All']+[p['name'] for p in peaks]);self.trend_peak.setCurrentIndex(min(max(old,0),len(peaks)))
            self.trend_peak.blockSignals(False);self.sync_trend_choice()
        self.run_pass2.setEnabled(source._batch_thread is None)
        self.trend_peak.setMinimumWidth(220)
        if len(self.checks)==len(peaks):
            for c,p in zip(self.checks,peaks):c.setText(p['name'])
        if len(self.checks)!=len(peaks):
            while self._labels.count():
                item=self._labels.takeAt(0)
                if item.widget():item.widget().deleteLater()
            self.checks=[]
            for peak in peaks:
                c=QCheckBox(peak['name']);c.setChecked(True);c.toggled.connect(self.refresh)
                self._labels.addWidget(c);self.checks.append(c)
        x=source.batch_incident_x()
        self.figure.clear();ax=self.figure.add_subplot(111)
        kind=self.kind.currentIndex()
        if kind in (0,1,2):
            key=['areas','centers','widths'][kind]
            vals=batch[key]
            for j,c in enumerate(self.checks):
                if not c.isChecked():continue
                y=vals[:,j].copy();y[~batch['success']]=np.nan
                ax.plot(x,y,lw=1,label=peaks[j]['name'])
                if kind in (1,2):
                    param='center' if kind==1 else 'width'
                    cfg=self.trend_configs.get((j,param))
                    if cfg is not None and source.batch_result is not None:
                        from ..fluorescence_map import fit_polynomial_trend
                        try:
                            first=source.batch_result['pass1']
                            reference=first[key][:,j]
                            smooth,_=fit_polynomial_trend(x,reference,cfg,first['success'])
                            ax.plot(x,smooth,'--',lw=2,label=peaks[j]['name']+' trend p='+str(cfg))
                        except ValueError:pass
                if kind==0:
                    err=batch['area_stderr'][:,j]
                    ax.fill_between(x,y-err,y+err,alpha=.12)
            ax.set_ylabel(['Integrated counts per bin','Center (eV)','FWHM (eV)'][kind])
            ax.legend(loc='best',fontsize=8)
        elif kind==3:
            ax.plot(x,np.where(batch['success'],batch['deviance'],np.nan),lw=1)
            ax.set_ylabel('Fit Poisson deviance')
        else:
            ax.plot(x,batch['background'][:,0],label='Background constant')
            if batch['linear_background']:ax.plot(x,batch['background'][:,1],label='Background slope')
            ax.legend(loc='best',fontsize=8);ax.set_ylabel('Background fit')
        ax.set_xlabel('Incident energy (eV)' if source.use_incident_ev.isChecked() else 'Incident scan index')
        self.figure.tight_layout();self.canvas.draw_idle()


class FLMapDialog(QDialog):
    """Modeless independent map and single detector spectrum fit GUI."""
    def __init__(self,parent=None):
        # A parentless top-level window can be placed behind other windows.
        # Keep an explicit reference for transferring spectra to the main app.
        super().__init__(None)
        self._main_window=parent
        self.setWindowTitle('FL Map Analysis — EXACT 2.6.0')
        self.resize(1510,850)
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowFlag(Qt.WindowType.Window,True)
        self.setAcceptDrops(True)
        self.energy_association=None;self._energy_source=None
        self.fm=None;self.fit_result=None;self.batch_result=None;self.trends_window=None;self._batch_thread=None
        self.peaks=[];self.bg0=0.;self.bg1=0.
        self._fit_undo={};self._peak_drag=None;self._peak_drag_last=None
        root=QVBoxLayout(self)
        root.setContentsMargins(5, 3, 5, 4)
        root.setSpacing(2)
        # No action button is a dialog default: Return edits the active input.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # One native menu-bar File menu; do not duplicate it with a toolbar button.
        menubar=QMenuBar(self)
        root.setMenuBar(menubar)
        filemenu=menubar.addMenu('File')
        self.open_action=filemenu.addAction('Open HDF5…',self.open_file)
        self.reload_action=filemenu.addAction('Reload same',self.reload_file)
        self.close_action=filemenu.addAction('Close HDF5',self.close_file)
        filemenu.addAction('Associate master scan…',self.associate_master)
        self.reload_action.setEnabled(False);self.close_action.setEnabled(False)
        filemenu.addAction('Load peak configuration…',self.load_configuration)
        filemenu.addAction('Save peak configuration…',self.save_configuration)
        filemenu.addSeparator()
        self.roi_transfer_action=filemenu.addAction('Send ROI spectrum to Processed Data',self.send_roi_to_processed)
        self.roi_transfer_action.setToolTip('Available only for an Original map with a calibrated incident-energy axis.')
        self.transfer_action=filemenu.addAction('Send fitted spectra to Processed Data…',self.send_fitted_to_processed)
        self.export_csv_action=filemenu.addAction('Export fitted spectra (CSV)…',self.export_fitted_csv)
        self.save_analysis_action=filemenu.addAction('Save fitted analysis (HDF5)…',self.save_analysis_hdf5)
        self.load_analysis_action=filemenu.addAction('Load fitted analysis (HDF5)…',self.load_analysis_hdf5)
        self.export_csv_action.setEnabled(False);self.save_analysis_action.setEnabled(False);self.transfer_action.setEnabled(False)
        self.roi_transfer_action.setEnabled(False)
        top=QHBoxLayout()
        self.file_label=QLabel('Drop an HDF5 map here, or choose File → Open HDF5…')
        top.addWidget(self.file_label,1)
        self.incident_label=QLabel('Incident E (eV):');top.addWidget(self.incident_label)
        self.incident=QSpinBox();self.incident.setRange(0,100000);self.incident.valueChanged.connect(self._new_selection)
        self.incident_display=QDoubleSpinBox();self.incident_display.setDecimals(1);self.incident_display.setRange(-100000,100000);self.incident_display.setSingleStep(.1)
        self.incident_display.valueChanged.connect(self._incident_display_changed);top.addWidget(self.incident_display)
        self.incident_display.setToolTip('Selected incident energy in eV, or scan index if the eV axis is disabled. The nearest measured spectrum is selected.')
        top.addWidget(QLabel('Average ± spectra:'))
        self.avg=QSpinBox();self.avg.setRange(0,500);self.avg.setValue(5);self.avg.valueChanged.connect(self._new_selection)
        top.addWidget(self.avg)
        self.avg.setToolTip('Average this many incident-energy points on each side for the displayed detector spectrum. Batch fit selection is independent.')
        self.fy_label=QLabel('FL E (eV):');top.addWidget(self.fy_label)
        self.fy_center=QSpinBox();self.fy_center.setRange(0,4095);self.fy_center.setValue(900)
        self.fy_center.valueChanged.connect(self._fy_center_changed)
        self.fy_display=QDoubleSpinBox();self.fy_display.setDecimals(1);self.fy_display.setRange(-100000,100000);self.fy_display.setSingleStep(.1)
        self.fy_display.valueChanged.connect(self._fy_display_changed);top.addWidget(self.fy_display)
        self.fy_display.setToolTip('Selected fluorescence energy in eV, or detector channel if the eV axis is disabled. The nearest channel is selected.')
        top.addWidget(QLabel('FL ROI ± ch:'))
        self.roi=QSpinBox();self.roi.setRange(1,2048);self.roi.setValue(80);self.roi.valueChanged.connect(self.refresh)
        top.addWidget(self.roi)
        self.roi.setToolTip('Half-width in detector channels of the FY extraction region around FY center.')
        self._map_mode='Original'
        self._reconstruction_cache={}
        self._colormap='viridis' 
        self._colormaps=available_colormaps()
        self._legend_anchor=None
        from .fluorescence_axes_dialog import build_axes_dialog
        build_axes_dialog(self)
        viewrow=QHBoxLayout()
        viewrow.addWidget(QLabel('Map:'))
        self.map_representation=QComboBox();self.map_representation.addItems(['Original','Fitted','Residual','Component'])
        self.map_representation.setToolTip('Original: measured counts; Fitted: all modeled peaks and background; Residual: measured minus model; Component: selected fitted fluorescence peak.')
        self.map_representation.currentTextChanged.connect(self._representation_changed)
        viewrow.addWidget(self.map_representation)
        self.map_representation.setEnabled(False)
        self.component_label=QLabel('Component:')
        viewrow.addWidget(self.component_label)
        self.component_choice=QComboBox()
        self.component_choice.setMinimumWidth(125)
        self.component_choice.setToolTip('Component map: all Gaussian peaks without background, fitted background alone, or a single user-named peak. Uses the active fitting pass.')
        self.component_choice.currentIndexChanged.connect(self.refresh)
        self.component_choice.setEnabled(False)
        self.component_label.setVisible(False)
        self.component_choice.setVisible(False)
        viewrow.addWidget(self.component_choice)
        self.pass_selector=QComboBox();self.pass_selector.addItems(['Pass 1','Pass 2'])
        self.pass_selector.setToolTip('Select independent Pass 1 or polynomial-trend-constrained Pass 2 results.')
        self.pass_selector.currentIndexChanged.connect(self._pass_changed)
        self.pass_selector.setEnabled(False)
        viewrow.addWidget(self.pass_selector)
        viewrow.addWidget(QLabel('Model:'))
        self.spectrum_model=QComboBox()
        self.spectrum_model.addItems(['Reference','Batch fit'])
        self.spectrum_model.setToolTip('Choose whether the detector-spectrum overlay shows the editable reference configuration or the fitted bin from the active batch pass. Measured counts retain the selected averaging.')
        self.spectrum_model.setEnabled(False)
        self.spectrum_model.currentIndexChanged.connect(self.refresh)
        viewrow.addWidget(self.spectrum_model)
        self.axes_button=QPushButton('Axes')
        self.axes_button.setToolTip('Choose precise map display ranges or energy calibration settings.')
        self.axes_menu=QMenu(self.axes_button)
        self.axes_menu.addAction('Ranges…',self.show_ranges_dialog)
        self.axes_menu.addAction('Calibration…',self.axes_dialog.show)
        self.axes_button.setMenu(self.axes_menu)
        viewrow.addWidget(self.axes_button)
        self.calibration_summary=QLabel('0.9235 eV/ch + 11.81 eV')
        self.calibration_summary.setToolTip('Current detector energy calibration; click Axes… to change it.')
        viewrow.addWidget(self.calibration_summary)
        viewrow.addStretch(1)
        # Independent visibility toggles affect only map guides, not selection or fitting.
        guiderow=QHBoxLayout()
        guiderow.addWidget(QLabel('Map guides:'))
        self.show_incident_guides=QCheckBox('Vertical')
        self.show_incident_guides.setChecked(True)
        self.show_incident_guides.setToolTip('Show the vertical incident-energy guide and averaging region. It selects the detector (FL) spectrum.')
        self.show_incident_guides.toggled.connect(self.refresh)
        guiderow.addWidget(self.show_incident_guides)
        self.show_fluorescence_guides=QCheckBox('Horizontal')
        self.show_fluorescence_guides.setChecked(True)
        self.show_fluorescence_guides.setToolTip('Show the horizontal fluorescence-energy guide and ROI. It selects the excitation (XAS) trace below the map.')
        self.show_fluorescence_guides.toggled.connect(self.refresh)
        guiderow.addWidget(self.show_fluorescence_guides)
        guiderow.addStretch(1)
        # Compact two-row control strip. The group titles sit in the border;
        # all controls share a height and the two columns align vertically.
        # Avoid stretch spacers inside groups: they create large empty areas.
        filename_row=QHBoxLayout()
        filename_row.setContentsMargins(2,0,0,0)
        filename_row.setSpacing(0)
        self.file_label.setStyleSheet('QLabel { padding: 0; margin: 0; }')
        filename_row.addWidget(self.file_label,1)
        root.addLayout(filename_row)

        def framed_group(title, tooltip):
            group=QGroupBox(title)
            group.setToolTip(tooltip)
            group.setStyleSheet('''
                QGroupBox {
                    border: 1px solid palette(mid);
                    border-radius: 4px;
                    margin-top: 12px;
                    padding: 0;
                    font-weight: 500;
                    background-color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 9px;
                    padding: 1px 4px 0 4px;
                    background-color: palette(window);
                }
            ''')
            layout=QHBoxLayout(group)
            layout.setContentsMargins(10, 11, 10, 6)
            layout.setSpacing(8)
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return group,layout

        detector_group,detector_controls=framed_group(
            'Detector spectrum', 'Incident-energy selection and averaging for the detector spectrum.')
        detector_controls.addWidget(self.incident_label)
        detector_controls.addWidget(self.incident_display)
        avg_label=QLabel('Avg ±')
        avg_label.setToolTip('Number of incident-energy spectra averaged on either side.')
        detector_controls.addWidget(avg_label)
        detector_controls.addWidget(self.avg)
        detector_controls.addStretch(1)

        excitation_group,excitation_controls=framed_group(
            'Excitation spectrum', 'Fluorescence-energy selection and ROI width for the excitation spectrum.')
        excitation_controls.addWidget(self.fy_label)
        excitation_controls.addWidget(self.fy_display)
        roi_label=QLabel('ROI ± ch')
        roi_label.setToolTip('ROI half-width in detector channels.')
        excitation_controls.addWidget(roi_label)
        excitation_controls.addWidget(self.roi)
        excitation_controls.addStretch(1)

        map_group,map_controls=framed_group(
            'Map display', 'Map representation, component and guide visibility.')
        map_controls.addWidget(QLabel('Map'))
        map_controls.addWidget(self.map_representation)
        map_controls.addWidget(self.component_label)
        map_controls.addWidget(self.component_choice)
        map_controls.addWidget(self.show_incident_guides)
        map_controls.addWidget(self.show_fluorescence_guides)
        map_controls.addStretch(1)

        fit_group,fit_controls=framed_group(
            'Fit display', 'Batch pass, detector-spectrum model and axis calibration.')
        fit_controls.addWidget(QLabel('Pass'))
        fit_controls.addWidget(self.pass_selector)
        fit_controls.addWidget(QLabel('Model'))
        fit_controls.addWidget(self.spectrum_model)
        fit_controls.addWidget(self.axes_button)
        fit_controls.addStretch(1)

        # A consistent minimum height keeps the two rows visually even,
        # without making the groups expand when the window gets taller.
        for field in (self.incident_display,self.fy_display,self.avg,self.roi,
                      self.map_representation,self.component_choice,
                      self.pass_selector,self.spectrum_model,self.axes_button):
            field.setFixedHeight(23)
        self.incident_display.setFixedWidth(104)
        self.fy_display.setFixedWidth(104)
        self.avg.setFixedWidth(57)
        self.roi.setFixedWidth(57)
        self.map_representation.setMinimumWidth(92)
        self.pass_selector.setMinimumWidth(73)
        self.spectrum_model.setMinimumWidth(100)

        controls_grid=QGridLayout()
        controls_grid.setContentsMargins(0,0,0,0)
        controls_grid.setHorizontalSpacing(7)
        controls_grid.setVerticalSpacing(3)
        controls_grid.setColumnStretch(0,1)
        controls_grid.setColumnStretch(1,1)
        controls_grid.addWidget(detector_group,0,0)
        controls_grid.addWidget(excitation_group,0,1)
        controls_grid.addWidget(map_group,1,0)
        controls_grid.addWidget(fit_group,1,1)
        root.addLayout(controls_grid)
        pane=QSplitter(Qt.Orientation.Horizontal);root.addWidget(pane,1)
        mapwidget=QWidget();mv=QVBoxLayout(mapwidget)
        self.mapfigure=Figure(figsize=(7,6),tight_layout=True)
        self.mapcanvas=FigureCanvasQTAgg(self.mapfigure)
        self.maptoolbar=FluorescenceToolbar(self.mapcanvas,mapwidget)
        mv.addWidget(self.maptoolbar);mv.addWidget(self.mapcanvas)
        pane.addWidget(mapwidget)
        right=QWidget();rv=QVBoxLayout(right)
        self.specfigure=Figure(figsize=(7,4));self.specfigure.subplots_adjust(left=.11,right=.98,top=.96,bottom=.12,hspace=.13);self.speccanvas=FigureCanvasQTAgg(self.specfigure)
        rv.addWidget(FluorescenceToolbar(self.speccanvas,right));rv.addWidget(self.speccanvas,2)
        actions=QHBoxLayout();rv.addLayout(actions)
        for title,callback in [('Add peak',self.add_peak),('Remove peak',self.remove_peak),('Fit spectrum',self.fit_spectrum),('Undo fit',self.undo_fit)]:
            b=QPushButton(title);b.clicked.connect(callback);actions.addWidget(b)
            b.setToolTip({'Add peak':'Add another editable Gaussian component.',
                          'Remove peak':'Remove the selected peak from the reference model.',
                          'Fit spectrum':'Fit the displayed averaged detector spectrum using the reference model.',
                          'Undo fit':'Restore reference parameters from before the most recent single-spectrum fit.'}[title])
        fitrange=QHBoxLayout();rv.addLayout(fitrange)
        fitrange.addWidget(QLabel('Fit channels:'))
        self.fit_min=QSpinBox();self.fit_min.setRange(0,100000);self.fit_min.setValue(150)
        self.fit_max=QSpinBox();self.fit_max.setRange(0,100000);self.fit_max.setValue(1150)
        fitrange.addWidget(self.fit_min);fitrange.addWidget(QLabel('to'));fitrange.addWidget(self.fit_max)
        fitrange.addStretch(1)
        self.peak_table=QTableWidget(0,6)
        self.peak_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.peak_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.peak_table.setHorizontalHeaderLabels(['Name','Center','Area','FWHM','     Free center','     Free width'])
        self.peak_header=_PeakToggleHeader(self.peak_table)
        self.peak_table.setHorizontalHeader(self.peak_header)
        self.peak_header.toggleColumn.connect(self._set_all_peak_freedom)
        self.peak_table.setToolTip('Checked = FREE in both interactive fitting and independent batch Pass 1. Unchecked = FIXED. Trend-constrained Pass 2 is configured in Trends.')
        self.peak_table.itemChanged.connect(self._edit_peaks)
        rv.addWidget(self.peak_table,1)
        self.reference_status=QLabel('Initial guesses — fit a reference spectrum before batch fitting.')
        self.reference_status.setToolTip('The peak table is the reference configuration. Browsing batch results never overwrites it.')
        rv.addWidget(self.reference_status)
        self.fit_settings_dialog=QDialog(self);self.fit_settings_dialog.setWindowTitle('Fit settings — FL Map Analysis')
        settingsroot=QVBoxLayout(self.fit_settings_dialog)
        bgrow=QHBoxLayout();settingsroot.addLayout(bgrow)
        bgrow.addWidget(QLabel('Background constant:'))
        self.bgspin=QDoubleSpinBox();self.bgspin.setToolTip('Initial background constant used for fitting; fitted background may change.');self.bgspin.setRange(0,1e9);self.bgspin.valueChanged.connect(self.refresh);bgrow.addWidget(self.bgspin)
        self.linear_bg=QCheckBox('Linear background');self.linear_bg.setChecked(True);self.linear_bg.setToolTip('Include a linearly varying background rather than a constant-only background.');bgrow.addWidget(self.linear_bg)
        settingsbinrow=QHBoxLayout();settingsroot.addLayout(settingsbinrow)
        settingsbinrow.addWidget(QLabel('Batch bin:'))
        self.batch_bin=QSpinBox();self.batch_bin.setRange(1,100);self.batch_bin.setValue(1)
        self.batch_bin.setToolTip('Sum adjacent detector spectra BEFORE fitting. Bin=1 preserves scan resolution.')
        settingsbinrow.addWidget(self.batch_bin)
        self.batch_refine=QCheckBox('Use trend constraints in Pass 2')
        self.batch_refine.setToolTip('First run independent Pass 1. Then choose polynomial trends in Trends and press Run Pass 2 there.')
        self.batch_refine.setVisible(False)
        self.center_tolerance=QDoubleSpinBox();self.center_tolerance.setValue(8.)
        self.width_tolerance=QDoubleSpinBox();self.width_tolerance.setValue(15.)
        softrow=QHBoxLayout();settingsroot.addLayout(softrow)
        softrow.addWidget(QLabel('Preferred FWHM (eV):'))
        self.soft_width_min=QDoubleSpinBox();self.soft_width_max=QDoubleSpinBox()
        for spin,value in ((self.soft_width_min,80.),(self.soft_width_max,160.)):
            spin.setRange(.01,10000.);spin.setDecimals(1);spin.setValue(value)
            spin.setToolTip('No penalty within the preferred FWHM interval. Free widths may move outside it.')
            softrow.addWidget(spin)
        softrow.addWidget(QLabel('Softness (eV):'))
        self.soft_width_scale=QDoubleSpinBox();self.soft_width_scale.setRange(.1,10000.)
        self.soft_width_scale.setDecimals(1);self.soft_width_scale.setValue(40.)
        self.soft_width_scale.setToolTip('Quadratic penalty (distance beyond interval / softness)²; larger = weaker.')
        softrow.addWidget(self.soft_width_scale);softrow.addStretch(1)
        settingsbinrow.addStretch(1)
        settingsroot.addWidget(QLabel('Widths within the preferred interval are unpenalized; outside it a gentle quadratic penalty applies.'))
        settings_buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        settings_buttons.rejected.connect(self.fit_settings_dialog.close);settings_buttons.accepted.connect(self.fit_settings_dialog.close)
        settingsroot.addWidget(settings_buttons)
        batchrow=QHBoxLayout();rv.addLayout(batchrow)
        self.batch_run=QPushButton('Fit map');self.batch_run.clicked.connect(self.start_batch_fit)
        self.batch_run.setToolTip('Fit the fluorescence map at every incident-energy bin using the reference peak configuration.')
        batchrow.addWidget(self.batch_run)
        self.trends_button=QPushButton('Trends…');self.trends_button.clicked.connect(self.open_trends)
        self.trends_button.setEnabled(False);self.trends_button.setToolTip('Inspect fitted peak intensities, positions and widths; configure trend-constrained Pass 2.')
        batchrow.addWidget(self.trends_button)
        self.fit_settings_button=QPushButton('Fit settings…');self.fit_settings_button.setToolTip('Background model, batch binning and preferred Gaussian width interval.')
        self.fit_settings_button.clicked.connect(self.fit_settings_dialog.show)
        batchrow.addWidget(self.fit_settings_button)
        self.batch_progress=QProgressBar();self.batch_progress.setRange(0,100);self.batch_progress.setValue(0)
        self.batch_progress.setStyleSheet('QProgressBar { text-align: center; } QProgressBar::chunk { background-color: #247bb8; }')
        progressrow=QHBoxLayout();rv.addLayout(progressrow)
        progressrow.addWidget(self.batch_progress,1)
        self.abort_batch=QPushButton('Abort');self.abort_batch.setEnabled(False)
        self.abort_batch.setToolTip('Stop the running batch fit and discard the incomplete results.')
        self.abort_batch.clicked.connect(self.abort_running_batch)
        progressrow.addWidget(self.abort_batch)
        self.status=QLabel('Open an HDF5 map to begin.');rv.addWidget(self.status)
        pane.addWidget(right);pane.setSizes([860,610])
        self.mapcanvas.setToolTip('Left drag: move incident or fluorescence cursor. Right-click: choose a color palette with gradient previews.')
        self.mapcanvas.mpl_connect('button_press_event',self.map_clicked)
        self.mapcanvas.mpl_connect('motion_notify_event',self.map_dragged)
        self.mapcanvas.mpl_connect('button_release_event',self.map_released)
        self.lineax=None
        self._drag=None;self._block_edit=False;self.fy_channel=900
        self._drag_pending=False
        self._drag_timer=QTimer(self);self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(70);self._drag_timer.timeout.connect(self._flush_cursor_drag)
        self.mapcanvas.mpl_connect('button_press_event',self._line_clicked)
        self.speccanvas.mpl_connect('button_release_event',self._remember_legend_position)
        self.mapcanvas.mpl_connect('motion_notify_event',self._line_dragged)
        self.speccanvas.mpl_connect('button_press_event',self._peak_press)
        self.det_slope.valueChanged.connect(self._update_calibration_summary)
        self.det_offset.valueChanged.connect(self._update_calibration_summary)
        self._update_calibration_summary()
        self.speccanvas.mpl_connect('motion_notify_event',self._peak_move)
        self.speccanvas.mpl_connect('button_release_event',self._peak_release)
        self._set_default_peaks()
        self._populate_peaks()
        # Commit hand-entered spin-box values on Enter/focus loss, not per keystroke.
        # Qt still applies arrow/button steps immediately, as expected for spin boxes.
        for spin in self.findChildren(QAbstractSpinBox):
            spin.setKeyboardTracking(False)
        # QPushButton's implicit auto-default otherwise activates Open HDF5 on Enter.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

    def _set_default_peaks(self):
        """Clean, application-generic guesses rather than NiO-specific chemical IDs."""
        self.peaks=[dict(id=f'P{j+1}',name=f'P{j+1}',center=float(c),area=1000.,
                         fwhm=90.,free_center=False,free_width=False)
                    for j,c in enumerate((277.,525.,677.,851.5))]
        self.bg0=0.;self.bg1=0.
        self._reference_state='guesses'

    def _set_reference_state(self,state):
        self._reference_state=state
        messages={
            'guesses':'Initial guesses — fit a reference spectrum before batch fitting.',
            'auto':'Auto-estimated peaks from this map — inspect and fit a reference spectrum.',
            'fitted':'Reference spectrum fitted — parameters ready for batch fitting.',
            'edited':'Parameters modified — fit again, or batch fit with edited values.',
            'loaded':'Configuration loaded — inspect or fit before batch fitting.',
        }
        self.reference_status.setText(messages.get(state,state))

    def _auto_initialize_peaks(self):
        """Data-based peak starting positions, approximate widths and photon areas.

        These are guesses only, deliberately NOT element identifications or a fit.
        """
        counts=self.fm.counts
        n=len(self.fm.detector)
        y=np.mean(counts[max(0,int(.55*len(counts))):],axis=0)
        from scipy.ndimage import gaussian_filter1d
        sm=gaussian_filter1d(y,8.)
        baseline=float(np.percentile(sm,10))
        prominence=max(float(np.ptp(sm))*.045, .3)
        found,props=find_peaks(sm,prominence=prominence,distance=max(12,n//100))
        if found.size:
            ranked=sorted(found,key=lambda k:float(sm[k]),reverse=True)[:4]
            indices=sorted(ranked)
            widths=peak_widths(sm,indices,rel_height=.5)[0]
            estimates=[]
            for j,(idx,w) in enumerate(zip(indices,widths)):
                fw=float(np.clip(w,5,max(12,n*.15)))
                height=max(0.,float(sm[idx])-baseline)
                area=max(10.,height*fw*1.0645)
                energy=float(self.det_slope.value()*self.fm.detector[idx]+self.det_offset.value())
                estimates.append(dict(id=f'P{j+1}',name=f'P{j+1}',center=energy,
                                      area=area,fwhm=fw*self.det_slope.value(),
                                      free_center=False,free_width=False))
            self.peaks=estimates
        self._set_reference_state('auto')
        self._populate_peaks()

    def _clear_analysis_state(self):
        """Release all derived data, trends, temporary fits and reference settings."""
        self.fit_result=None;self.batch_result=None;self._reconstruction_cache={}
        if hasattr(self,'export_csv_action'):self.export_csv_action.setEnabled(False);self.save_analysis_action.setEnabled(False);self.transfer_action.setEnabled(False)
        if hasattr(self,'component_choice'):self.component_choice.clear();self.component_choice.setEnabled(False);self.component_choice.setVisible(False);self.component_label.setVisible(False)
        self._legend_anchor=None
        self._drag=None;self._drag_pending=False;self._drag_timer.stop()
        if self.trends_window is not None:
            self.trends_window.close();self.trends_window.deleteLater();self.trends_window=None
        self.map_representation.blockSignals(True);self.map_representation.setCurrentIndex(0)
        self.map_representation.blockSignals(False);self.map_representation.setEnabled(False)
        self.pass_selector.blockSignals(True);self.pass_selector.setCurrentIndex(0)
        self.pass_selector.blockSignals(False);self.pass_selector.setEnabled(False)
        self.trends_button.setEnabled(False);self.batch_progress.setValue(0)
        self.spectrum_model.blockSignals(True)
        self.spectrum_model.setCurrentIndex(0)
        self.spectrum_model.blockSignals(False)
        self.spectrum_model.setEnabled(False)
        self.mapfigure.clear();self.specfigure.clear()
        self.mapax=None;self.lineax=None;self._spec_legend=None;self._spec_ax=None
        self._set_default_peaks();self._fit_undo.clear();self._populate_peaks()
        self.bgspin.blockSignals(True);self.bgspin.setValue(0.);self.bgspin.blockSignals(False)
        self.fit_min.setValue(150);self.fit_max.setValue(1150)
        self.batch_bin.setValue(1)
        self.soft_width_min.setValue(80.);self.soft_width_max.setValue(160.);self.soft_width_scale.setValue(40.)
        self._set_reference_state('guesses')

    def _fit_busy(self):
        if self._batch_thread is not None:
            QMessageBox.warning(self,'Batch fitting','Finish batch fitting before replacing or closing the map.')
            return True
        return False

    def reload_file(self):
        if self._fit_busy() or self.fm is None:return
        # Reload from disk, not cached or reconstructed data.
        self.load_file(self.fm.source)

    def close_file(self):
        if self._fit_busy():return
        self._clear_analysis_state()
        self.fm=None
        self.energy_association=None;self._energy_source=None
        self._update_roi_transfer_action()
        self._update_energy_source_label()
        self.reload_action.setEnabled(False);self.close_action.setEnabled(False)
        self.file_label.setText('Drop an HDF5 map here, or choose File → Open HDF5…')
        self.incident.blockSignals(True);self.incident.setRange(0,100000);self.incident.setValue(0);self.incident.blockSignals(False)
        self.fy_channel=900
        self.fy_center.blockSignals(True);self.fy_center.setRange(0,4095);self.fy_center.setValue(900);self.fy_center.blockSignals(False)
        for widget,value in ((self.avg,5),(self.roi,80),(self.e_start,0.),(self.e_end,0.),
                             (self.det_slope,.9235),(self.det_offset,11.81)):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        self._colormap='viridis'
        self.use_incident_ev.blockSignals(True);self.use_incident_ev.setChecked(False);self.use_incident_ev.blockSignals(False)
        self.use_detector_ev.blockSignals(True);self.use_detector_ev.setChecked(True);self.use_detector_ev.blockSignals(False)
        self.mapcanvas.draw_idle();self.speccanvas.draw_idle()
        self._sync_position_fields()
        self.status.setText('Open an HDF5 map to begin.')

    def _spectrum_toolbar_busy(self):
        nav=getattr(self.speccanvas,'toolbar',None)
        return bool(nav is not None and getattr(nav,'mode',''))

    def _peak_press(self,event):
        self._peak_drag=None
        if self.fm is None or self._spectrum_toolbar_busy() or event.inaxes is not getattr(self,'_spec_ax',None) or event.button!=1:
            return
        if event.x is None or event.y is None:return
        choices=[]
        for j,mark in enumerate(getattr(self,'_peak_markers',[])):
            mx,my=self._spec_ax.transData.transform((mark.get_xdata()[0],mark.get_ydata()[0]))
            distance=float(np.hypot(event.x-mx,event.y-my))
            if distance<=14:choices.append((distance,j))
        if choices:
            self._peak_drag=min(choices)[1]
            self._peak_drag_last=None

    def _peak_move(self,event):
        j=self._peak_drag
        if j is None or self.fm is None or self._spectrum_toolbar_busy():return
        if event.inaxes is not getattr(self,'_spec_ax',None) or event.xdata is None or event.ydata is None:return
        # Both center and peak HEIGHT follow the pointer. Stored intensity is
        # the integrated area, so adjust it using the current Gaussian width.
        p=self.peaks[j]
        center=float(event.xdata) if self.use_detector_ev.isChecked() else float(event.xdata)*self.det_slope.value()+self.det_offset.value()
        physical_min=self.det_offset.value();physical_max=self.det_slope.value()*(len(self.fm.detector)-1)+physical_min
        center=float(np.clip(center,physical_min,physical_max))
        sigma=max(float(p['fwhm']),.1)/2.354820045
        area=max(0.,float(event.ydata))*sigma*np.sqrt(2*np.pi)
        p['center']=center;p['area']=area
        self._peak_drag_last=(center,area)
        # Synchronize the edited fields without invoking table edit handlers or
        # triggering an expensive full Matplotlib redraw during mouse motion.
        self._block_edit=True
        try:
            for column,value in ((1, center if self.use_detector_ev.isChecked() else (center-self.det_offset.value())/self.det_slope.value()), (2,area)):
                cell=self.peak_table.item(j,column)
                if cell is not None:cell.setText(f'{value:.3f}' if column==1 else f'{value:.4g}')
        finally:
            self._block_edit=False
        # Update only the dragged artist for responsive interaction.
        xdisplay=center if self.use_detector_ev.isChecked() else (center-self.det_offset.value())/self.det_slope.value()
        self._peak_markers[j].set_data([xdisplay],[area/(sigma*np.sqrt(2*np.pi))])
        xplot=self.detector_y()
        xphysical=self.det_slope.value()*self.fm.detector+self.det_offset.value()
        model=area/(sigma*np.sqrt(2*np.pi))*np.exp(-.5*((xphysical-center)/sigma)**2)
        self._reference_component_lines[j].set_data(xplot,model)
        total,_=evaluate_model(xphysical,self.peaks,self.bg0,self.bg1)
        self._spec_total_line.set_data(xplot,total)
        if self._spec_residual_line is not None:
            lo=max(0,self.fit_min.value());hi=min(len(total),self.fit_max.value()+1)
            measured=self.selected_spectrum()
            self._spec_residual_line.set_data(xplot[lo:hi],measured[lo:hi]-total[lo:hi])
        self.speccanvas.draw_idle()

    def _peak_release(self,event):
        if self._peak_drag is None:return
        self._peak_drag=None
        if self._peak_drag_last is not None:
            self.fit_result=None
            self._populate_peaks();self._set_reference_state('edited');self.refresh()
        self._peak_drag_last=None

    def _toolbar_busy(self):
        toolbar=getattr(self.mapcanvas,'toolbar',None)
        return bool(toolbar is not None and getattr(toolbar,'mode',''))

    def _nearest_line(self,event):
        """Pick either map cursor using distance in SCREEN pixels."""
        x=self.incident_x()[self.incident.value()]
        y=self.detector_y()[self.fy_channel]
        px=self.mapax.transData.transform((x,y))
        dx=abs(event.x-px[0]);dy=abs(event.y-px[1])
        threshold=13
        if dx<=threshold or dy<=threshold:
            return 'incident' if dx<=dy else 'detector'
        return 'incident' if event.button==1 else 'detector' if event.button==3 else None

    def _line_clicked(self,event):
        if self.fm is None or self._toolbar_busy() or event.inaxes is not self.lineax or event.button!=1 or event.xdata is None:return
        self._drag='incident';self._set_cursor(event)

    def _line_dragged(self,event):
        # A drag started on the lower XAS panel may continue over either panel.
        if self._drag=='incident' and event.inaxes is self.lineax and event.xdata is not None and not self._toolbar_busy():
            self._drag_cursor(event)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in ('.h5','.hdf5') for u in event.mimeData().urls()):event.acceptProposedAction()
    def dropEvent(self,event):
        for u in event.mimeData().urls():
            if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in ('.h5','.hdf5'):
                self.load_file(u.toLocalFile());event.acceptProposedAction();return
    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Open fluorescence map','','HDF5 files (*.h5 *.hdf5)')
        if path:self.load_file(path)
    def load_file(self,path):
        if self._fit_busy():return
        try:fm=load_fluorescence_map(path)
        except Exception as ex:QMessageBox.warning(self,'FL Map Analysis',str(ex));return
        self._clear_analysis_state()
        self.fm=fm
        self.reload_action.setEnabled(True);self.close_action.setEnabled(True)
        self.file_label.setText(Path(path).name+f' — {fm.counts.shape[0]} × {fm.counts.shape[1]}')
        self.incident.blockSignals(True);self.incident.setMaximum(fm.counts.shape[0]-1);self.incident.setValue(fm.counts.shape[0]//2);self.incident.blockSignals(False)
        self.fy_channel=min(900,fm.counts.shape[1]-1)
        self.fy_center.blockSignals(True);self.fy_center.setMaximum(fm.counts.shape[1]-1);self.fy_center.setValue(self.fy_channel);self.fy_center.blockSignals(False)
        self.energy_association=None
        self._energy_source='detector' if fm.incident_label.endswith('(eV)') else None
        if self._energy_source is None:
            main=self._main_window
            paths=list(getattr(main,'hdf5_files',{})) if main is not None else []
            self.energy_association=match_master(path,paths,fm.counts.shape[0])
            if self.energy_association is not None:self._energy_source='master'
        calibrated=self._energy_source is not None
        axis=self.energy_association.values if self.energy_association is not None else fm.incident
        for widget,value in ((self.e_start,float(axis[0])),(self.e_end,float(axis[-1]))):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        self.use_incident_ev.setChecked(calibrated)
        self._update_energy_source_label()
        self._sync_position_fields()
        self._update_roi_transfer_action()
        self._set_default_peaks();self._populate_peaks();self._set_reference_state('guesses')
        self.status.setText('Map loaded. Default P1–P4 parameters restored; edit or fit before batch fitting.')
        self.refresh()
    def _update_energy_source_label(self):
        if not hasattr(self,'energy_source_label'):return
        a=self.energy_association
        if a is not None:description=f'Master: {Path(a.master_file).name} / {a.entry} / {a.channel}'
        elif self._energy_source=='detector':description='Detector HDF5 metadata'
        elif self._energy_source=='manual':description='Manual first/last energy assignment'
        else:description='Not calibrated — scan index'
        self.energy_source_label.setText('Incident source: '+description)
        if hasattr(self,'master_channel'):
            self.master_channel.blockSignals(True)
            self.master_channel.setEnabled(a is not None)
            self.master_channel.setCurrentIndex(0 if a is None or a.channel=='pcap_energy_av' else 1)
            self.master_channel.blockSignals(False)

    def _choose_master_channel(self,index):
        a=self.energy_association
        if a is None or self.fm is None:return
        channel=('pcap_energy_av','mono_traj_energy')[index]
        try:new=read_energy(a.master_file,a.entry,len(self.fm.incident),channel)
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'Incident energy',str(exc));self._update_energy_source_label();return
        self.energy_association=new
        self._apply_association()

    def _apply_association(self):
        a=self.energy_association
        if a is None:return
        self._energy_source='master'
        for widget,value in ((self.e_start,float(a.values[0])),(self.e_end,float(a.values[-1]))):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        self.use_incident_ev.setChecked(True)
        self._update_energy_source_label()
        self._sync_position_fields();self.mapfigure.clear();self.refresh()

    def associate_master(self):
        if self.fm is None:
            QMessageBox.information(self,'Associate master','Load a fluorescence detector map first.');return
        main=self._main_window
        paths=list(getattr(main,'hdf5_files',{})) if main is not None else []
        path,_=QFileDialog.getOpenFileName(self,'Select master scan HDF5',str(Path(paths[0]).parent) if paths else '', 'HDF5 files (*.h5 *.hdf5)')
        if not path:return
        try:entries=available_entries(path)
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'Master scan',str(exc));return
        from PyQt6.QtWidgets import QInputDialog
        preferred=detector_entry_id(self.fm.source)
        match=next((i for i,e in enumerate(entries) if e.lower()==f'entry{preferred}'.lower()),0)
        entry,ok=QInputDialog.getItem(self,'Master scan entry','Select corresponding entry:',entries,match,False)
        if not ok:return
        try:a=read_energy(path,entry,self.fm.counts.shape[0])
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'Master scan',str(exc));return
        self.energy_association=a;self._apply_association()

    def _sync_position_fields(self):
        """Display calibrated coordinates while preserving integer data indices internally."""
        incident_ev=self.use_incident_ev.isChecked()
        fl_ev=self.use_detector_ev.isChecked()
        self.incident_label.setText('Incident E (eV):' if incident_ev else 'Incident index:')
        self.fy_label.setText('FL E (eV):' if fl_ev else 'FL channel:')
        xx=self.incident_x()
        yy=self.detector_y()
        for field,axis,index,energy in ((self.incident_display,xx,self.incident.value(),incident_ev),
                                         (self.fy_display,yy,self.fy_channel,fl_ev)):
            field.blockSignals(True)
            field.setDecimals(1 if energy else 0)
            field.setSingleStep(.1 if energy else 1.)
            if len(axis):
                field.setRange(float(np.min(axis)),float(np.max(axis)))
                field.setValue(float(axis[min(max(index,0),len(axis)-1)]))
            else:
                field.setRange(-100000,100000)
                field.setValue(float(index))
            field.blockSignals(False)

    def _incident_display_changed(self,value):
        # Respect the energy entered by the user. The internal scan selection is
        # discrete, but snapping this spin box back to its nearest scan energy
        # disrupts both text entry and the 0.1 eV arrow controls.
        axis=self.incident_x()
        index=int(np.argmin(np.abs(axis-float(value)))) if len(axis) else int(round(value))
        self.incident.blockSignals(True)
        self.incident.setValue(index)
        self.incident.blockSignals(False)
        self.fit_result=None
        self.refresh()

    def _fy_display_changed(self,value):
        # A detector channel is discrete, whereas its requested energy is not.
        # Preserve the committed number in the editor; only the channel used
        # for the displayed ROI needs to be rounded to the nearest sample.
        axis=self.detector_y()
        index=int(np.argmin(np.abs(axis-float(value)))) if len(axis) else int(round(value))
        self.fy_channel=index
        self.fy_center.blockSignals(True)
        self.fy_center.setValue(index)
        self.fy_center.blockSignals(False)
        self.refresh()

    def _fy_center_changed(self,value):
        self.fy_channel=int(value)
        self._sync_position_fields()
        self.refresh()
    def _remember_legend_position(self,event=None):
        legend=getattr(self,'_spec_legend',None)
        if legend is None or not legend.get_visible():return
        # Capture its current location in axes coordinates, persisting across redraws.
        try:
            bbox=legend.get_window_extent(self.speccanvas.get_renderer())
            x,y=self._spec_ax.transAxes.inverted().transform((bbox.x0,bbox.y1))
            if np.isfinite(x) and np.isfinite(y):
                # Keep the anchor inside the axes. An external bbox makes tight
                # layout repeatedly shrink the plotted area on every redraw.
                self._legend_anchor=(float(np.clip(x,.02,.78)),float(np.clip(y,.30,.98)))
        except (AttributeError, ValueError):pass
    def _show_colormap_menu(self,event):
        # PANDA-inspired preview chooser, without a blocking nested Qt loop.
        open_colormap(self,self._colormap,self._choose_colormap)
    def _choose_colormap(self,cmap):
        self._colormap=cmap
        self.refresh()
    def show_ranges_dialog(self):
        """Precisely set the visible map area; never change scan calibration or fits."""
        if self.fm is None or self.mapax is None:
            QMessageBox.information(self,'Display ranges','Open an HDF5 fluorescence map first.')
            return
        dialog=QDialog(self)
        dialog.setWindowTitle('Map display ranges — FL Map Analysis')
        layout=QVBoxLayout(dialog)
        current_x=self.mapax.get_xlim()
        current_y=self.mapax.get_ylim()
        def range_row(title, bounds, units):
            group=QGroupBox(f'{title} ({units})')
            line=QHBoxLayout(group)
            widgets=[]
            for label,value in zip(('From','To'),bounds):
                line.addWidget(QLabel(label))
                edit=QDoubleSpinBox()
                edit.setRange(-1e7,1e7)
                edit.setDecimals(1 if units=='eV' else 0)
                edit.setSingleStep(.1 if units=='eV' else 1.)
                edit.setKeyboardTracking(False)
                edit.setValue(float(value))
                line.addWidget(edit)
                widgets.append(edit)
            layout.addWidget(group)
            return widgets
        x_fields=range_row('Incident energy' if self.use_incident_ev.isChecked() else 'Incident scan',current_x,'eV' if self.use_incident_ev.isChecked() else 'index')
        y_fields=range_row('Fluorescence energy' if self.use_detector_ev.isChecked() else 'Detector',current_y,'eV' if self.use_detector_ev.isChecked() else 'channel')
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Reset)
        layout.addWidget(buttons)
        def full_range():
            x=self.batch_incident_x() if self.map_representation.currentText()!='Original' and self.batch_result is not None else self.incident_x()
            y=self.detector_y()
            if len(x) and len(y):
                for w,v in zip(x_fields,(x[0],x[-1])):w.setValue(float(v))
                for w,v in zip(y_fields,(y[0],y[-1])):w.setValue(float(v))
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText('Full range')
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(full_range)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        x0,x1=(f.value() for f in x_fields)
        y0,y1=(f.value() for f in y_fields)
        if abs(x1-x0)<1e-9 or abs(y1-y0)<1e-9:
            QMessageBox.warning(self,'Display ranges','Start and end of each range must be different.')
            return
        self.mapax.set_xlim(x0,x1)
        self.mapax.set_ylim(y0,y1)
        self.maptoolbar.push_current()
        self.mapcanvas.draw_idle()

    def _new_selection(self):
        self.fit_result=None
        self._sync_position_fields()
        self.refresh()
    def _update_calibration(self):
        if self.fm is not None and not getattr(self,'_setting_energy_controls',False):
            self._energy_source='manual';self.energy_association=None
            self.use_incident_ev.setChecked(True)
            self._update_energy_source_label()
        self._update_roi_transfer_action()
        self._sync_position_fields()
        self.mapfigure.clear();self.refresh()
    def _detector_axis_changed(self):
        self._sync_position_fields()
        self.mapfigure.clear();self.specfigure.clear()
        self._populate_peaks()
        self.refresh()
    def _update_calibration_summary(self, *_):
        self.calibration_summary.setText(
            f'FL: {self.det_slope.value():.4f} eV/ch + {self.det_offset.value():.2f} eV')

    def _detector_calibration_changed(self):
        self._sync_position_fields()
        self.mapfigure.clear();self.specfigure.clear();self._populate_peaks();self.refresh()
    def _incident_axis_changed(self):
        if self.fm is not None and self.use_incident_ev.isChecked() and self._energy_source is None:
            self.use_incident_ev.blockSignals(True);self.use_incident_ev.setChecked(False);self.use_incident_ev.blockSignals(False)
            QMessageBox.information(self,'Incident energy','No incident-energy calibration is available. Associate a master scan or assign manual first/last energies.')
        self._sync_position_fields()
        self.mapfigure.clear();self.refresh()
    def incident_x(self):
        if self.fm is None:return np.array([])
        if not self.use_incident_ev.isChecked():return np.arange(self.fm.counts.shape[0],dtype=float)
        if self.energy_association is not None:return self.energy_association.values
        if self._energy_source=='detector':return self.fm.incident
        if self._energy_source=='manual':return np.linspace(self.e_start.value(),self.e_end.value(),self.fm.counts.shape[0])
        return np.arange(self.fm.counts.shape[0],dtype=float)
    def detector_y(self):
        if self.fm is None:return np.array([])
        chan=self.fm.detector
        return self.det_slope.value()*chan+self.det_offset.value() if self.use_detector_ev.isChecked() else chan
    def map_clicked(self,event):
        if self.fm is None or self._toolbar_busy() or event.inaxes is not self.mapax or event.xdata is None:return
        if event.button==3:
            self._show_colormap_menu(event);return
        if event.button!=1:return
        self._drag=self._nearest_line(event)
        self._set_cursor(event)
    def map_dragged(self,event):
        if self._drag and not self._toolbar_busy() and event.inaxes in (self.mapax,self.lineax) and event.xdata is not None:
            self._drag_cursor(event)
    def map_released(self,event):
        if self._drag_pending:
            self._drag_timer.stop();self._flush_cursor_drag()
        self._drag=None
    def _drag_cursor(self,event):
        """Update cursor coordinates promptly; coalesce expensive figure redraws."""
        if self._drag=='incident' and event.xdata is not None:
            i=int(np.argmin(abs(self.incident_x()-event.xdata)))
            if i!=self.incident.value():
                self.incident.blockSignals(True);self.incident.setValue(i);self.incident.blockSignals(False)
                self._drag_pending=True
        elif self._drag=='detector' and event.ydata is not None and event.inaxes is self.mapax:
            i=int(np.argmin(abs(self.detector_y()-event.ydata)))
            if i!=self.fy_channel:
                self.fy_channel=i;self.fy_center.blockSignals(True)
                self.fy_center.setValue(i);self.fy_center.blockSignals(False)
                self._drag_pending=True
        if self._drag_pending and not self._drag_timer.isActive():self._drag_timer.start()

    def _flush_cursor_drag(self):
        if self._drag_pending:
            self._drag_pending=False
            self._sync_position_fields()
            self.refresh()

    def _set_cursor(self,event):
        if self._drag=='incident':
            i=int(np.argmin(abs(self.incident_x()-event.xdata)));self.incident.setValue(i)
        elif self._drag=='detector' and event.ydata is not None and event.inaxes is self.mapax:
            self.fy_channel=int(np.argmin(abs(self.detector_y()-event.ydata)))
            self.fy_center.blockSignals(True);self.fy_center.setValue(self.fy_channel);self.fy_center.blockSignals(False)
            self._sync_position_fields()
            self.refresh()
    def _sync_component_visibility(self):
        active=self.batch_result is not None and self.map_representation.currentText()=='Component'
        self.component_label.setVisible(active)
        self.component_choice.setVisible(active)
        self.component_choice.setEnabled(active)

    def _representation_changed(self,*_):
        self._update_roi_transfer_action()
        self._sync_component_visibility()
        self.refresh()

    def _pass_changed(self,*_):
        if self.trends_window is not None:self.trends_window.refresh()
        self.refresh()

    def active_batch(self):
        if self.batch_result is None:return None
        if self.pass_selector.currentIndex()==0 and self.batch_result.get('refined'):
            return dict(self.batch_result,**self.batch_result['pass1'])
        return self.batch_result

    def reconstructed_map(self):
        """Reconstruct in count units on the native detector grid, no interpolation."""
        batch=self.active_batch()
        if batch is None or self.fm is None:return None
        cache_key=(id(self.batch_result),self.pass_selector.currentIndex(),self.det_slope.value(),self.det_offset.value())
        if cache_key in self._reconstruction_cache:return self._reconstruction_cache[cache_key]
        yy=self.det_slope.value()*self.fm.detector+self.det_offset.value()
        out=np.full((len(batch['success']),len(yy)),np.nan)
        # The fit range is modeled; outside it do not claim a fitted result.
        a,b=batch['fit_slice'];axis=yy[a:b]
        for i,ok in enumerate(batch['success']):
            if not ok:continue
            pp=[dict(p,area=float(batch['areas'][i,j]),center=float(batch['centers'][i,j]),fwhm=float(batch['widths'][i,j])) for j,p in enumerate(batch['peaks'])]
            z,_=evaluate_model(axis,pp,*batch['background'][i]);out[i,a:b]=z
        self._reconstruction_cache={cache_key:out}
        return out

    def component_map(self, peak_index):
        """One reconstructed Gaussian in native detector counts, without background.

        Each fitted batch row is a sum over its bin. Areas are therefore kept
        in counts/bin, consistent with the fitted map and residual map.
        """
        batch=self.active_batch()
        if batch is None or self.fm is None:return None
        x=self.det_slope.value()*self.fm.detector+self.det_offset.value()
        if peak_index==0:  # All Gaussian components, excluding fitted background
            return sum((reconstruct_component(batch,x,j) for j in range(len(batch['peaks']))))
        if peak_index==1:  # Fitted background alone
            out=np.full((len(batch['success']),len(x)),np.nan)
            a,b=batch['fit_slice']
            for i,good in enumerate(batch['success']):
                if good:
                    out[i,a:b]=batch['background'][i,0]+batch['background'][i,1]*(x[a:b]-np.mean(x[a:b]))
            return out
        return reconstruct_component(batch,x,peak_index-2)

    def _refresh_component_choice(self):
        old_id=self.component_choice.currentData()
        self.component_choice.blockSignals(True)
        self.component_choice.clear()
        batch=self.active_batch()
        if batch is not None:
            names={p.get('id'):p['name'] for p in self.peaks}
            self.component_choice.addItem('All peaks (no BG)','__ALL__')
            self.component_choice.addItem('Background','__BG__')
            for j,p in enumerate(batch['peaks']):
                self.component_choice.addItem(names.get(p.get('id'),p['name']),p.get('id',j))
            idx=self.component_choice.findData(old_id)
            self.component_choice.setCurrentIndex(max(idx,0))
        self._sync_component_visibility()
        self.component_choice.blockSignals(False)

    def _export_bundle(self):
        """Build export from the selected pass; no processing or I0 normalization."""
        batch=self.active_batch()
        if batch is None or self.fm is None:raise ValueError('Fit the map first.')
        x=self.batch_incident_x()
        names={p.get('id'):p['name'] for p in self.peaks}
        labels=[names.get(p.get('id'),p['name']) for p in batch['peaks']]
        x,areas,errors=extract_fitted_fy(batch,self.incident_x())
        return x,labels,areas,errors,batch

    def _update_roi_transfer_action(self):
        if hasattr(self,'roi_transfer_action'):
            self.roi_transfer_action.setEnabled(
                self.fm is not None
                and self.map_representation.currentText() == 'Original'
                and self.use_incident_ev.isChecked()
                and self._energy_source is not None)

    def _source_entry_prefix(self):
        """Only show an entry when verified by a master association."""
        a=self.energy_association
        return f'{a.entry} — ' if a is not None else ''

    def _insert_processed_curves(self, curves, status):
        """Shared transactional insertion for fitted and ROI curves.

        curves: sequence of (x, y, display_name, region_label).
        """
        main=self._main_window
        if main is None or not hasattr(main,'plot_data') or not hasattr(main,'update_plot_processed'):
            QMessageBox.warning(self,'Transfer unavailable','This window is not attached to an EXACT Processed Data workspace.')
            return
        source=str(Path(self.fm.source).resolve())
        serial=int(getattr(main,'_sum_serial',0) or 0)
        inserted=[]
        try:
            if not hasattr(main,'energy_cache') or main.energy_cache is None:main.energy_cache={}
            if not hasattr(main,'raw_visibility') or main.raw_visibility is None:main.raw_visibility={}
            if not hasattr(main,'curve_display_names') or main.curve_display_names is None:main.curve_display_names={}
            if not hasattr(main,'_region_overrides') or main._region_overrides is None:main._region_overrides={}
            for x,y,name,region_label in curves:
                serial+=1
                parent=f'__SUM__/FL{serial}'
                key=f'{source}##{parent}/area'
                x=np.asarray(x,dtype=float).copy()
                main.plot_data[key]=np.asarray(y,dtype=float).copy()
                main.energy_cache[f'{source}::{parent}']=(x.copy(),True)
                main.energy_cache[f'{source}##{parent}']=(x.copy(),True)
                main.raw_visibility[key]=True
                main.curve_display_names[key]=name
                main._region_overrides[key]={'start':float(x[0]),'end':float(x[-1]),
                    'label':region_label,'unfinished':False}
                inserted.append((key,parent))
            main.update_plot_processed()
            main._sum_serial=serial
            self.status.setText(status)
        except Exception as exc:
            for key,parent in inserted:
                main.plot_data.pop(key,None)
                main.raw_visibility.pop(key,None)
                main.curve_display_names.pop(key,None)
                main._region_overrides.pop(key,None)
                main.energy_cache.pop(f'{source}::{parent}',None)
                main.energy_cache.pop(f'{source}##{parent}',None)
            QMessageBox.warning(self,'Transfer failed',str(exc))

    def send_roi_to_processed(self):
        """Send the unfitted ROI excitation trace from the Original map only."""
        if self.fm is None or self.map_representation.currentText() != 'Original':return
        if not self.use_incident_ev.isChecked() or self._energy_source is None:
            QMessageBox.warning(self,'Energy axis required','A calibrated incident-energy axis is required.')
            return
        x=np.asarray(self.incident_x(),dtype=float)
        if x.size<2 or not np.isfinite(x).all() or np.any(np.diff(x)<=0):
            QMessageBox.warning(self,'Invalid incident axis','An increasing calibrated incident-energy axis is required.')
            return
        lo=max(0,self.fy_channel-self.roi.value())
        hi=min(self.fm.counts.shape[1],self.fy_channel+self.roi.value()+1)
        # Identical inclusive ROI integration as the lower Original-map trace.
        y=integrate_fluorescence_roi(self.fm.counts,self.fy_channel,self.roi.value())
        center=self.detector_y()[self.fy_channel]
        if self.use_detector_ev.isChecked():
            roi_description=f'{center:.1f} eV ±{self.roi.value()} ch'
        else:
            roi_description=f'channel {self.fy_channel} ±{self.roi.value()} ch'
        name=f'{self._source_entry_prefix()}FL ROI {roi_description}'
        self._insert_processed_curves([(x,y,name,'FL measured ROI (not I₀-normalized)')],
            'Sent measured fluorescence ROI spectrum to Processed Data (not I₀-normalized).')

    def send_fitted_to_processed(self):
        """Insert selected fitted FY spectra using EXACT's synthetic-curve route.

        The injected records are memory-only and have an explicit energy cache,
        exactly as the existing Processed Data summed-group records do.
        """
        if self.batch_result is None:return
        main=self._main_window
        if main is None or not hasattr(main,'plot_data') or not hasattr(main,'update_plot_processed'):
            QMessageBox.warning(self,'Transfer unavailable','This window is not attached to an EXACT Processed Data workspace.')
            return
        x,labels,areas,errors,batch=self._export_bundle()
        if not self.use_incident_ev.isChecked() or self._energy_source is None:
            QMessageBox.warning(self,'Energy axis required','Enable Incident axis: eV before sending XAS curves to Processed Data.')
            return
        if len(x)<2 or not np.isfinite(x).all() or np.any(np.diff(x)<=0):
            QMessageBox.warning(self,'Invalid incident axis','An increasing calibrated incident-energy axis is required.')
            return
        dlg=QDialog(self);dlg.setWindowTitle('Send fluorescence spectra — EXACT')
        v=QVBoxLayout(dlg)
        v.addWidget(QLabel('Select fitted fluorescence components to send to Processed Data:'))
        checks=[]
        for name in labels:
            cb=QCheckBox(name);cb.setChecked(True);v.addWidget(cb);checks.append(cb)
        v.addWidget(QLabel('These are fitted FY counts per original incident spectrum, NOT I₀-normalized.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);v.addWidget(buttons)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        chosen=[i for i,cb in enumerate(checks) if cb.isChecked()]
        if not chosen:return
        curves=[(x,areas[:,j],f'{self._source_entry_prefix()}FL {labels[j]} — fitted FY (counts/spectrum)',
                 f'FL fitted FY ({self.pass_selector.currentText()})') for j in chosen]
        self._insert_processed_curves(curves,
            f'Sent {len(chosen)} fitted FY spectra to Processed Data (not I₀-normalized).')

    def export_fitted_csv(self):
        if self.batch_result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export fitted FY spectra','','CSV (*.csv)')
        if not path:return
        try:
            x,labels,areas,errors,batch=self._export_bundle()
            with open(path,'w',newline='',encoding='utf-8-sig') as f:
                w=csv.writer(f)
                w.writerow(['# EXACT fitted fluorescence excitation spectra; raw counts per incident spectrum; NOT I0 normalized'])
                w.writerow(['# source',self.fm.source,'pass',self.pass_selector.currentText(),'bin_size',batch['bin_size']])
                w.writerow(['incident_energy_eV' if self.use_incident_ev.isChecked() else 'incident_index',
                            *[label+' area_counts_per_spectrum' for label in labels],
                            *[label+' area_stderr' for label in labels], 'fit_success'])
                for i,energy in enumerate(x):
                    w.writerow([float(energy),*areas[i],*errors[i],int(batch['success'][i])])
            self.status.setText(f'Exported {len(labels)} fitted FY spectra to CSV.')
        except Exception as e:QMessageBox.warning(self,'Export failed',str(e))

    def save_analysis_hdf5(self):
        if self.batch_result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save fitted FL analysis','','HDF5 (*.h5 *.hdf5)')
        if not path:return
        try:
            x,labels,areas,errors,batch=self._export_bundle()
            with h5py.File(path,'w') as h:
                h.attrs['format']='exact-fl-analysis-v1'
                h.attrs['source_hdf5']=self.fm.source
                h.attrs['source_shape']=self.fm.counts.shape
                h.attrs['incident_calibration_source']=self._energy_source or 'uncalibrated'
                if self.energy_association is not None:
                    h.attrs['incident_master_file']=self.energy_association.master_file
                    h.attrs['incident_master_entry']=self.energy_association.entry
                    h.attrs['incident_master_channel']=self.energy_association.channel
                h.attrs['incident_start_eV']=self.e_start.value()
                h.attrs['incident_end_eV']=self.e_end.value()
                h.attrs['linear_background']=bool(batch['linear_background'])
                h.attrs['reference_peaks_json']=json.dumps(self.peaks)
                h.attrs['reference_bg0']=self.bg0
                h.attrs['reference_bg1']=self.bg1
                h.attrs['fit_pass']=self.pass_selector.currentText()
                h.attrs['areas_unit']='counts per original incident spectrum; no I0 normalization'
                h.create_dataset('incident_energy',data=x)
                h.create_dataset('peak_names',data=np.asarray(labels,dtype=h5py.string_dtype('utf-8')))
                h.create_dataset('peak_ids',data=np.asarray([p.get('id','') for p in batch['peaks']],dtype=h5py.string_dtype('utf-8')))
                h.create_dataset('areas',data=areas,compression='gzip')
                h.create_dataset('area_stderr',data=errors,compression='gzip')
                h.create_dataset('success',data=batch['success'])
                h.create_dataset('bin_starts',data=batch['starts'])
                h.create_dataset('bin_counts',data=batch['bin_counts'])
                h.attrs['bin_size']=batch['bin_size']
                h.attrs['detector_eV_per_channel']=self.det_slope.value()
                h.attrs['detector_offset_eV']=self.det_offset.value()
                h.create_dataset('detector_energy_eV',data=self.det_slope.value()*self.fm.detector+self.det_offset.value())
                h.create_dataset('fit_slice',data=np.asarray(batch['fit_slice']))
                for label,source in [('pass1',self.batch_result['pass1']),('selected_pass',batch)]:
                    group=h.create_group(label)
                    for key in ('areas','area_stderr','centers','widths','background','deviance','success'):
                        group.create_dataset(key,data=source[key],compression='gzip')
                h.attrs['has_pass2']=bool(self.batch_result['refined'])
                if self.batch_result['refined']:
                    h.attrs['trend_constraints_json']=json.dumps([[int(j),str(kind),int(degree)] for (j,kind),degree in self.batch_result.get('trend_constraints',{}).items()])
            self.status.setText('Saved fluorescence fitting results and extracted spectra to HDF5.')
        except Exception as e:QMessageBox.warning(self,'Save failed',str(e))

    def load_analysis_hdf5(self):
        """Restore saved batch output against an already loaded original map.

        Only the derived fit data are loaded; original detector counts are never
        read from, or replaced by, the analysis file.
        """
        if self.fm is None:
            QMessageBox.information(self,'Load fitted analysis','Open the original fluorescence map first.')
            return
        if self._batch_thread is not None:
            QMessageBox.warning(self,'Load fitted analysis','Abort or finish batch fitting first.')
            return
        path,_=QFileDialog.getOpenFileName(self,'Load fitted analysis','','HDF5 (*.h5 *.hdf5)')
        if not path:return
        try:
            with h5py.File(path,'r') as h:
                if h.attrs.get('format')!='exact-fl-analysis-v1':
                    raise ValueError('Not an EXACT fluorescence analysis file.')
                if Path(str(h.attrs.get('source_hdf5',''))).name != Path(self.fm.source).name:
                    raise ValueError('This analysis belongs to a different source HDF5 filename.')
                if tuple(h.attrs['source_shape'])!=self.fm.counts.shape:
                    raise ValueError('Original HDF5 map dimensions do not match this analysis.')
                def read_group(group):
                    return {k:np.asarray(group[k][...]) for k in ('areas','area_stderr','centers','widths','background','deviance','success')}
                first=read_group(h['pass1'])
                selected=read_group(h['selected_pass'])
                names=h['peak_names'].asstr()[...].tolist()
                ids=h['peak_ids'].asstr()[...].tolist()
                peaks=[dict(id=pid,name=name,area=1.,center=float(first['centers'][0,j]) if np.isfinite(first['centers'][0,j]) else 0.,
                            fwhm=float(first['widths'][0,j]) if np.isfinite(first['widths'][0,j]) else 100.,free_center=False,free_width=False)
                       for j,(pid,name) in enumerate(zip(ids,names))]
                constraints={(int(j),str(k)):int(d) for j,k,d in json.loads(h.attrs.get('trend_constraints_json','[]'))}
                result=dict(**selected,starts=np.asarray(h['bin_starts'][...],dtype=int),
                            bin_counts=np.asarray(h['bin_counts'][...],dtype=int),bin_size=int(h.attrs['bin_size']),
                            fit_slice=tuple(map(int,h['fit_slice'][...])),peaks=peaks,
                            pass1=first,refined=bool(h.attrs['has_pass2']),trend_constraints=constraints,
                            trend_curves={},linear_background=bool(h.attrs.get('linear_background',True)))
                reference=json.loads(h.attrs.get('reference_peaks_json','[]'))
                scale=float(h.attrs['detector_eV_per_channel'])
                offset=float(h.attrs['detector_offset_eV'])
                en_start=float(h.attrs.get('incident_start_eV',self.e_start.value()))
                en_end=float(h.attrs.get('incident_end_eV',self.e_end.value()))
                # Compare actual axes against fitted axes, avoiding silent
                # misregistration if the same-shaped map uses other energies.
                stored=np.asarray(h['incident_energy'])
                if len(stored)!=len(result['starts']):raise ValueError('Invalid saved incident energy axis.')
                if not np.allclose(self.incident_x()[result['starts']],stored,atol=.2,rtol=0):
                    # Binned positions use the BIN MIDPOINT, not start position.
                    probe=np.array([np.mean(self.incident_x()[start:start+n]) for start,n in zip(result['starts'],result['bin_counts'])])
                    if not np.allclose(probe,stored,atol=.2,rtol=0):
                        raise ValueError('Incident energy calibration differs from the fitted analysis.')
            self._clear_analysis_state()
            self.det_slope.setValue(scale);self.det_offset.setValue(offset)
            self.e_start.setValue(en_start);self.e_end.setValue(en_end)
            if reference:self.peaks=reference
            else:self.peaks=peaks
            self._populate_peaks();self._set_reference_state('loaded')
            self.batch_result=result;self._reconstruction_cache={}
            self._refresh_component_choice()
            self.map_representation.setEnabled(True);self.pass_selector.setEnabled(True)
            self.pass_selector.model().item(1).setEnabled(bool(result['refined']))
            self.pass_selector.setCurrentIndex(1 if result['refined'] else 0)
            self.trends_button.setEnabled(True);self.spectrum_model.setEnabled(True)
            self.spectrum_model.setCurrentIndex(1)
            self.export_csv_action.setEnabled(True);self.save_analysis_action.setEnabled(True);self.transfer_action.setEnabled(True)
            self.status.setText('Loaded saved fluorescence fitting analysis; original map unchanged.')
            self.refresh()
        except Exception as e:QMessageBox.warning(self,'Load failed',str(e))

    def _selected_batch_spectrum(self):
        """Return the active pass fit for the bin containing the cursor.

        Batch parameters are independent of the reference parameter table and
        of the user-selected averaging width for the displayed counts trace.
        """
        batch = self.active_batch()
        if batch is None or self.fm is None:
            return None
        starts = np.asarray(batch['starts'])
        if starts.size == 0:
            return None
        index = batch_row_for_incident(starts, self.incident.value())
        if not batch['success'][index]:
            return None
        peaks = [dict(p, area=float(batch['areas'][index, j]),
                      center=float(batch['centers'][index, j]),
                      fwhm=float(batch['widths'][index, j]))
                 for j, p in enumerate(batch['peaks'])]
        # A batch bin contains summed counts; the spectrum trace is a mean.
        # Normalize the fitted intensities/background to counts per scan.
        n = max(int(batch['bin_counts'][index]), 1)
        # Names may have changed after fitting; use current names by ID.
        names = {p['id']: p['name'] for p in self.peaks}
        for peak in peaks:
            peak['area'] /= n
            peak['name'] = names.get(peak.get('id'), peak['name'])
        bg0, bg1 = np.asarray(batch['background'][index], float) / n
        return peaks, float(bg0), float(bg1), tuple(batch['fit_slice']), index

    def selected_spectrum(self):
        center=self.incident.value();lo=max(0,center-self.avg.value());hi=min(self.fm.counts.shape[0],center+self.avg.value()+1)
        return np.mean(self.fm.counts[lo:hi],axis=0)
    def refresh(self,*_):
        self._update_roi_transfer_action()
        if self.fm is None:return
        xx=self.incident_x();yy=self.detector_y();arr=self.fm.counts
        view=self.map_representation.currentText()
        if view!='Original' and self.batch_result is not None:
            modeled=(self.component_map(self.component_choice.currentIndex()) if view=='Component' else self.reconstructed_map())
            batch=self.active_batch()
            # A binned result is displayed on its native (binned) incident axis.
            plot_x=self.batch_incident_x()
            display=modeled if view in ('Fitted','Component') else np.add.reduceat(arr,batch['starts'],axis=0)-modeled
            map_x=plot_x
        else:
            display=arr;map_x=xx
        # Preserve user-controlled pan/zoom across cursor drags and fitting redraws.
        previous_map=(self.mapax.get_xlim(),self.mapax.get_ylim()) if self.mapfigure.axes and self.lineax is not None else None
        previous_spec=self.specfigure.axes[0].get_xlim() if self.specfigure.axes else None
        if self.mapfigure.axes and self.mapax is not None and self.lineax is not None:
            self.mapax.cla();self.lineax.cla()
        else:
            gs=self.mapfigure.add_gridspec(2,1,height_ratios=[3,1])
            self.mapax=self.mapfigure.add_subplot(gs[0]);self.lineax=self.mapfigure.add_subplot(gs[1],sharex=self.mapax)
        extent=[map_x[0],map_x[-1],yy[0],yy[-1]]
        if view=='Residual' and self.batch_result is not None:
            finite=display[np.isfinite(display)]
            # Use the same color limits for Pass 1 and Pass 2, enabling visual comparison.
            residual_reference=np.add.reduceat(arr,batch['starts'],axis=0)
            spread=float(np.percentile(np.abs(residual_reference[:,batch['fit_slice'][0]:batch['fit_slice'][1]]),90))
            vmax=max(spread*.30, float(np.percentile(np.abs(finite),98)) if finite.size else 1.)
            self.mapax.imshow(display.T,aspect='auto',origin='lower',extent=extent,cmap='RdBu_r',vmin=-max(vmax,1e-6),vmax=max(vmax,1e-6),interpolation='nearest')
        else:
            self.mapax.imshow(display.T,aspect='auto',origin='lower',extent=extent,cmap=self._colormap,interpolation='nearest')
        i=self.incident.value(); ilo=max(0,i-self.avg.value());ihi=min(len(xx)-1,i+self.avg.value())
        if self.show_incident_guides.isChecked():
            self.mapax.axvspan(xx[ilo],xx[ihi],facecolor='white',alpha=.10)
            self.mapax.axvline(xx[ilo],color='white',lw=.8,ls='--',alpha=.9)
            self.mapax.axvline(xx[ihi],color='white',lw=.8,ls='--',alpha=.9)
            self.mapax.axvline(xx[i],color='white',lw=1.3,alpha=.95)
        ylo=max(0,self.fy_channel-self.roi.value());yhi=min(len(yy)-1,self.fy_channel+self.roi.value())
        if self.show_fluorescence_guides.isChecked():
            self.mapax.axhspan(yy[ylo],yy[yhi],facecolor='cyan',alpha=.09)
            self.mapax.axhline(yy[ylo],color='cyan',lw=.85,ls='--',alpha=.95)
            self.mapax.axhline(yy[yhi],color='cyan',lw=.85,ls='--',alpha=.95)
            self.mapax.axhline(yy[self.fy_channel],color='cyan',lw=1.3,alpha=.95)
        if view=='Residual' and self.batch_result is not None:
            self.mapax.set_title(self.pass_selector.currentText()+' — residual (measured − fit)',fontsize=9)
        self.mapax.set_xlabel('Incident energy (eV)' if self.use_incident_ev.isChecked() else 'Incident scan index')
        self.mapax.set_ylabel('Fluorescence energy (eV)' if self.use_detector_ev.isChecked() else 'Detector channel')
        lo=max(0,self.fy_channel-self.roi.value())
        hi=min(display.shape[1],self.fy_channel+self.roi.value()+1)
        # The lower trace is an ROI cut through the *visible* 2D map, not
        # unconditionally through the original raw counts. Fitted/component/
        # residual maps have one row per batch bin, and may be NaN outside
        # the fitted detector interval or for unsuccessful rows.
        trace=integrate_fluorescence_roi(display,self.fy_channel,self.roi.value())
        self.lineax.plot(map_x,trace,color='tab:blue',lw=1)
        self.lineax.axvline(xx[self.incident.value()],color='tab:red',lw=.9)
        self.lineax.set_ylabel('ROI counts' if view=='Original' or self.batch_result is None else 'ROI counts / bin')
        self.lineax.set_xlabel(self.mapax.get_xlabel())
        self.mapax.set_xlabel('')
        if previous_map is not None:
            self.mapax.set_xlim(previous_map[0]);self.mapax.set_ylim(previous_map[1])
        # The XAS intensity must follow the selected fluorescence ROI.  Keeping
        # the previous Y limits clips peaks when the ROI width or center changes.
        # Respect the currently zoomed incident-energy X interval, but autoscale
        # the lower plot's Y limits to the data visible in that interval.
        xlo,xhi=self.lineax.get_xlim()
        visible=(map_x>=min(xlo,xhi)) & (map_x<=max(xlo,xhi))
        values=trace[visible] if np.any(visible) else trace
        finite=values[np.isfinite(values)]
        if finite.size:
            ymin,ymax=float(np.min(finite)),float(np.max(finite))
            pad=max((ymax-ymin)*.06, abs(ymax)*.01, 1e-9)
            self.lineax.set_ylim(ymin-pad,ymax+pad)
        self.mapcanvas.draw_idle()
        spectrum=self.selected_spectrum()
        self.specfigure.clear();axes=self.specfigure.subplots(2,1,sharex=True,height_ratios=[3,1]);ax,resax=axes
        self._spec_ax=ax
        ax.plot(yy,spectrum,color='black',lw=.8,label='Detector counts')
        # Show the selected BATCH fit when available, not the frozen single
        # reference fit. Averaging +/- points only controls the black trace.
        # Batch binning governs which fitted row is used for the overlay.
        selected_batch = self._selected_batch_spectrum() if self.spectrum_model.currentIndex()==1 else None
        self._reference_component_lines=[]
        self._peak_markers=[]
        self._spec_residual_line=None
        if selected_batch is not None:
            display_peaks, display_bg0, display_bg1, fit_interval, bin_index = selected_batch
        elif self.batch_result is not None and self.spectrum_model.currentIndex()==1:
            # A failed bin has no batch fit: do not substitute the old reference.
            display_peaks, display_bg0, display_bg1 = [], 0., 0.
        else:
            display_peaks, display_bg0, display_bg1 = self.peaks, self.bg0, self.bg1
            fit_interval = (max(0,self.fit_min.value()), min(len(spectrum),self.fit_max.value()+1))
        if display_peaks:
            full_x=self.det_slope.value()*self.fm.detector+self.det_offset.value()
            plot_x=full_x if self.use_detector_ev.isChecked() else self.fm.detector
            if selected_batch is not None:
                # The slope in the batch backend is evaluated relative to the
                # fitted detector interval's mean, not the full detector axis.
                lo,hi=fit_interval
                local_x=full_x[lo:hi]
                model,components=evaluate_model(local_x,display_peaks,display_bg0,display_bg1)
                draw_x=plot_x[lo:hi]
                label='Batch fit (bin {})'.format(bin_index+1)
            else:
                model,components=evaluate_model(full_x,display_peaks,display_bg0,display_bg1)
                draw_x=plot_x
                lo,hi=fit_interval
                label='Total fit'
            self._spec_total_line=ax.plot(draw_x,model,color='tab:red',lw=1.3,label=label)[0]
            for j,(peak,curve) in enumerate(zip(display_peaks,components)):
                line=ax.plot(draw_x,curve,lw=1,label=peak['name'])[0]
                self._reference_component_lines.append(line)
                # Markers control editable reference parameters only. Batch
                # fitted parameters must never silently alter that table.
                if selected_batch is None:
                    xc=peak['center'] if self.use_detector_ev.isChecked() else (peak['center']-self.det_offset.value())/self.det_slope.value()
                    sigma=max(float(peak['fwhm']),.1)/2.354820045
                    height=float(peak['area'])/(sigma*np.sqrt(2*np.pi))
                    marker=ax.plot([xc],[height],marker='o',ms=6,linestyle='None',color=line.get_color(),zorder=10,picker=9)[0]
                    self._peak_markers.append(marker)
            if selected_batch is not None:
                if hi>lo:
                    self._spec_residual_line=resax.plot(draw_x,spectrum[lo:hi]-model,color='tab:gray',lw=.7)[0]
            elif hi>lo:
                self._spec_residual_line=resax.plot(plot_x[lo:hi],spectrum[lo:hi]-model[lo:hi],color='tab:gray',lw=.7)[0]
        else:
            resax.axhline(0,color='gray',lw=.6)
        if self._legend_anchor is None:
            self._spec_legend=ax.legend(loc='upper right',fontsize=7,ncol=2)
        else:
            self._spec_legend=ax.legend(loc='upper left',bbox_to_anchor=self._legend_anchor,fontsize=7,ncol=2)
        self._spec_legend.set_draggable(True)
        ax.set_ylabel('Counts / spectrum')
        if previous_spec is not None:ax.set_xlim(previous_spec)
        resax.set_ylabel('Residual');resax.set_xlabel('Fluorescence energy (eV)' if self.use_detector_ev.isChecked() else 'Detector channel')
        self.speccanvas.draw_idle()
    def _populate_peaks(self):
        self._block_edit=True;self.peak_table.setRowCount(len(self.peaks))
        for i,p in enumerate(self.peaks):
            center=p['center'] if self.use_detector_ev.isChecked() else (p['center']-self.det_offset.value())/self.det_slope.value()
            width=p['fwhm'] if self.use_detector_ev.isChecked() else p['fwhm']/self.det_slope.value()
            for j,val in enumerate((p['name'],f'{center:.3f}',f"{p['area']:.4g}",f'{width:.3f}')):
                self.peak_table.setItem(i,j,QTableWidgetItem(str(val)))
            for j,key in [(4,'free_center'),(5,'free_width')]:
                it=QTableWidgetItem('');it.setFlags(it.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if p.get(key,True) else Qt.CheckState.Unchecked)
                self.peak_table.setItem(i,j,it)
        self.peak_table.clearSelection()
        self.peak_table.setCurrentItem(None)
        self._block_edit=False
        self._sync_peak_header()

    def _sync_peak_header(self):
        for column, key in ((4,'free_center'), (5,'free_width')):
            flags=[bool(p.get(key, True)) for p in self.peaks]
            state=(Qt.CheckState.Checked if flags and all(flags) else
                   Qt.CheckState.PartiallyChecked if any(flags) else
                   Qt.CheckState.Unchecked)
            self.peak_header.set_state(column, state)

    def _set_all_peak_freedom(self, column, checked):
        key={4:'free_center', 5:'free_width'}.get(column)
        if key is None or not self.peaks:
            return
        for p in self.peaks:
            p[key]=bool(checked)
        self._populate_peaks()
        self.fit_result=None
        self._set_reference_state('edited')
        self.refresh()

    def _edit_peaks(self,item):
        if self._block_edit:return
        i=item.row();j=item.column();p=self.peaks[i]
        try:
            if j==0:
                p['name']=item.text()
            elif j in (1,2,3):
                val=float(item.text())
                if not math.isfinite(val):
                    raise ValueError('Value must be finite.')
                if j==1:
                    converted=val if self.use_detector_ev.isChecked() else val*self.det_slope.value()+self.det_offset.value()
                    if not math.isfinite(converted):raise ValueError('Peak center must be finite.')
                    if self.fm is not None:
                        axis=self.det_slope.value()*self.fm.detector+self.det_offset.value()
                        if converted < min(axis[0],axis[-1]) or converted > max(axis[0],axis[-1]):
                            raise ValueError('Peak center must lie within the detector range.')
                    p['center']=converted
                elif j==2:
                    if val<0:raise ValueError('Peak area cannot be negative.')
                    p['area']=val
                else:
                    if val<=0:raise ValueError('FWHM must be greater than zero.')
                    converted=val if self.use_detector_ev.isChecked() else val*self.det_slope.value()
                    if not math.isfinite(converted) or converted<=0:
                        raise ValueError('FWHM must be positive and finite.')
                    p['fwhm']=converted
            elif j==4:p['free_center']=item.checkState()==Qt.CheckState.Checked
            elif j==5:p['free_width']=item.checkState()==Qt.CheckState.Checked
        except (ValueError,OverflowError) as ex:
            self._populate_peaks()
            self.status.setText(f'Invalid peak parameter: {ex}')
            return
        # Normalize display to the accepted value; never leave a rejected number
        # visible while the model silently uses a different one.
        if j in (1,2,3):
            self._block_edit=True
            display=(p['center'] if self.use_detector_ev.isChecked() else
                     (p['center']-self.det_offset.value())/self.det_slope.value()) if j==1 else (
                     p['area'] if j==2 else p['fwhm'] if self.use_detector_ev.isChecked() else
                     p['fwhm']/self.det_slope.value())
            item.setText(f'{display:.4g}' if j==2 else f'{display:.3f}')
            self._block_edit=False
        if j in (4,5):self._sync_peak_header()
        self.fit_result=None
        if j==0 and self.trends_window is not None:self.trends_window.refresh()
        self._set_reference_state('edited');self.refresh()
    def add_peak(self):
        self.peaks.append(dict(id=f'P{max([int(p.get("id","P0")[1:]) for p in self.peaks if str(p.get("id","P0")).startswith("P") and str(p.get("id","P0"))[1:].isdigit()] or [0])+1}',name=f'P{max([int(p.get("id","P0")[1:]) for p in self.peaks if str(p.get("id","P0")).startswith("P") and str(p.get("id","P0"))[1:].isdigit()] or [0])+1}',center=850.,area=1000.,fwhm=90.,free_center=False,free_width=False));self._populate_peaks();self._set_reference_state('edited');self.refresh()
    def remove_peak(self):
        # currentRow may remain set even after a user clears the selection.
        rows = sorted({idx.row() for idx in self.peak_table.selectionModel().selectedRows()})
        if len(rows) != 1:
            QMessageBox.information(self, 'Remove peak', 'Please select the peak to remove first.', QMessageBox.StandardButton.Ok)
            return
        i = rows[0]
        self.peaks.pop(i)
        self._populate_peaks()
        self.fit_result=None
        self._set_reference_state('edited')
        self.refresh()
    def _spectrum_key(self):
        return (id(self.fm),int(self.incident.value()),int(self.avg.value()))

    def undo_fit(self):
        """Undo the last reference fit for this exact detector/averaging selection."""
        snapshot=self._fit_undo.pop(self._spectrum_key(),None)
        if snapshot is None:
            self.status.setText('No previous fit to undo for the selected spectrum.')
            return
        self.peaks,self.bg0,self.bg1,self.fit_result,state=deepcopy(snapshot)
        self.bgspin.blockSignals(True);self.bgspin.setValue(self.bg0);self.bgspin.blockSignals(False)
        self._populate_peaks();self._set_reference_state(state);self.refresh()
        self.status.setText('Undid the latest fit for this detector spectrum.')
    def _width_penalty_settings(self):
        lo=self.soft_width_min.value();hi=self.soft_width_max.value()
        if lo>=hi:
            raise ValueError('Preferred FWHM minimum must be smaller than maximum.')
        return (lo,hi),self.soft_width_scale.value()

    def fit_spectrum(self):
        if self.fm is None:return
        # The batch overlay is a read-only result.  Offer an explicit switch
        # rather than silently fitting behind that overlay.
        if self.batch_result is not None and self.spectrum_model.currentIndex()==1:
            answer=QMessageBox.question(
                self, 'Fit reference spectrum',
                'The detector spectrum currently shows a batch-fit result.\n\n'
                'Fit the displayed averaged counts as a new reference spectrum?\n'
                'The completed batch results will be preserved, and the spectrum overlay '
                'will switch to Reference parameters.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes)
            if answer != QMessageBox.StandardButton.Yes:return
            self.spectrum_model.setCurrentIndex(0)
        try:
            x=self.det_slope.value()*self.fm.detector+self.det_offset.value()
            lo=max(0,self.fit_min.value());hi=min(len(x),self.fit_max.value()+1)
            if hi-lo<16:raise ValueError('Fit interval must span at least 16 detector channels.')
            snapshot=deepcopy((self.peaks,self.bg0,self.bg1,self.fit_result,self._reference_state))
            soft,scale=self._width_penalty_settings()
            r=fit_detector_spectrum(x[lo:hi],self.selected_spectrum()[lo:hi],self.peaks,self.bgspin.value(),0.,linear_background=self.linear_bg.isChecked(),
                                    width_soft_limits=soft,width_softness=scale)
            r['xfit']=x[lo:hi]
            self._fit_undo[self._spectrum_key()]=snapshot
            self.fit_result=r;self.peaks=r['peaks'];self.bg0=r['bg0'];self.bg1=r['bg1']
            self.bgspin.blockSignals(True);self.bgspin.setValue(self.bg0);self.bgspin.blockSignals(False)
            self._populate_peaks();self._set_reference_state('fitted');self.status.setText(f"Fit: {'converged' if r['success'] else 'not converged'}; Poisson deviance {r['deviance']:.1f}")
            self.refresh()
        except Exception as ex:QMessageBox.warning(self,'Peak fit failed',str(ex))
    def save_configuration(self):
        path,_=QFileDialog.getSaveFileName(self,'Save fitting configuration','','JSON (*.json)')
        if path:save_fit_configuration(path,self.peaks,self.bg0,self.bg1)
    def load_configuration(self):
        path,_=QFileDialog.getOpenFileName(self,'Load fitting configuration','','JSON (*.json)')
        if not path:return
        try:
            obj=load_fit_configuration(path);self.peaks=obj['peaks'];self.bg0=obj['bg0'];self.bg1=obj['bg1'];self._populate_peaks();self.fit_result=None;self._set_reference_state('loaded');self.refresh()
        except Exception as ex:QMessageBox.warning(self,'Invalid fit configuration',str(ex))

    def batch_incident_x(self):
        if self.batch_result is None:return np.array([])
        x=self.incident_x();b=self.batch_result
        return np.array([np.mean(x[start:start+count]) for start,count in zip(b['starts'],b['bin_counts'])])

    def start_batch_fit(self, second_pass=False):
        if self.fm is None:return
        if self._batch_thread is not None:
            self.status.setText('A batch fit is already running.');return
        a=max(0,self.fit_min.value());b=min(self.fm.counts.shape[1],self.fit_max.value()+1)
        if b-a<16:
            QMessageBox.warning(self,'Batch fit','Fit range must contain at least 16 channels.');return
        x=self.det_slope.value()*self.fm.detector+self.det_offset.value()
        if second_pass and (self.batch_result is None or self.trends_window is None):
            QMessageBox.warning(self,'Batch fit','Run Pass 1 and select parameter trends before Pass 2.');return
        if second_pass and not self.trends_window.trend_configs:
            QMessageBox.warning(self,'Batch fit','Select at least one polynomial trend in Trends first.');return
        if second_pass and self.batch_bin.value()!=self.batch_result['bin_size']:
            QMessageBox.warning(self,'Batch fit','Keep the same binning as Pass 1.');return
        if not second_pass and self._reference_state in ('guesses','auto','loaded','edited'):
            choice=QMessageBox.question(self,'Batch fit initialization',
                'The peak table contains '+self._reference_state+' parameters, not a validated reference fit.\n'
                'Batch fitting will use these exact values and the Free checkboxes. Continue?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if choice!=QMessageBox.StandardButton.Yes:return
        try:
            soft,scale=self._width_penalty_settings()
        except ValueError as ex:
            QMessageBox.warning(self,'Width constraints',str(ex));return
        kw=dict(width_soft_limits=soft,width_softness=scale,bin_size=self.batch_bin.value(),fit_slice=(a,b),bg0=self.bg0,bg1=self.bg1,
                linear_background=self.linear_bg.isChecked(),refine_shapes=bool(second_pass),
                trend_constraints=dict(self.trends_window.trend_configs) if second_pass else {},
                prior_result=self.batch_result if second_pass else None)
        self._batch_thread=QThread(self)
        self._batch_worker=_BatchWorker(self.fm.counts,x,[dict(p) for p in self.peaks],kw)
        self._batch_worker.moveToThread(self._batch_thread)
        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.updated.connect(self._batch_updated)
        self._batch_worker.finished.connect(self._batch_finished)
        self._batch_worker.failed.connect(self._batch_failed)
        self._batch_worker.finished.connect(self._batch_thread.quit)
        self._batch_worker.failed.connect(self._batch_thread.quit)
        self._batch_thread.finished.connect(self._batch_worker.deleteLater)
        self._batch_thread.finished.connect(self._batch_thread.deleteLater)
        self._batch_thread.finished.connect(self._batch_clear)
        self.batch_run.setEnabled(False)
        self.abort_batch.setEnabled(True)
        self.batch_progress.setValue(0)
        self.status.setText('Batch fitting detector spectra…')
        self._batch_thread.start()

    def abort_running_batch(self):
        if self._batch_worker is None:return
        self._batch_worker.cancel_event.set()
        self.abort_batch.setEnabled(False)
        self.status.setText('Aborting batch fit; incomplete results will be discarded…')

    def _batch_updated(self,done,total):
        self.batch_progress.setValue(int(100*done/max(total,1)))
        self.status.setText(f'Batch fit: {done}/{total} spectra')

    def _batch_finished(self,result):
        if self._batch_worker.cancel_event.is_set():
            self.status.setText('Batch aborted; existing results preserved.')
            return
        self.batch_result=result
        self._reconstruction_cache={}
        self._refresh_component_choice()
        self.export_csv_action.setEnabled(True);self.save_analysis_action.setEnabled(True);self.transfer_action.setEnabled(True)
        self.map_representation.setEnabled(True)
        self.pass_selector.setEnabled(True)
        self.pass_selector.model().item(1).setEnabled(bool(result['refined']))
        self.pass_selector.setCurrentIndex(1 if result['refined'] else 0)
        self.trends_button.setEnabled(True)
        self.spectrum_model.setEnabled(True)
        self.spectrum_model.setCurrentIndex(1)
        n=int(np.count_nonzero(result['success']))
        self.status.setText(f'Batch {2 if result["refined"] else 1} completed: {n}/{len(result["success"])} bins fitted; original map unchanged.')
        self.batch_progress.setValue(100)
        self.refresh()
        if self.trends_window is not None:self.trends_window.refresh()
        self.open_trends()

    def _batch_failed(self,error):
        if error=='ABORTED':
            self.status.setText('Batch aborted; existing results preserved.')
            return
        self.status.setText('Batch failed: '+error)
        QMessageBox.warning(self,'Batch fit failed',error)

    def _batch_clear(self):
        self._batch_thread=None;self._batch_worker=None
        self.batch_run.setEnabled(True)
        self.abort_batch.setEnabled(False)

    def open_trends(self):
        if self.batch_result is None:return
        if self.trends_window is None:
            self.trends_window=FLBatchTrends(self)
        self.trends_window.refresh();self.trends_window.show();self.trends_window.raise_();self.trends_window.activateWindow()

    def closeEvent(self,event):
        if self._batch_thread is not None:
            QMessageBox.information(self,'Batch fitting','Please finish the running batch fit before closing this window.')
            event.ignore();return
        if self.trends_window is not None:self.trends_window.close()
        super().closeEvent(event)
