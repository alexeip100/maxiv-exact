from pathlib import Path


def test_version_metadata_is_244():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    init = Path("src/flexpes_nexafs/__init__.py").read_text(encoding="utf-8")
    assert 'version = "2.4.4"' in pyproject
    assert '__version__ = "2.4.4"' in init
    assert '__date__ = "2026-09-07"' in init


def test_hdf5_locking_is_set_before_h5py_import():
    data = Path("src/flexpes_nexafs/data.py").read_text(encoding="utf-8")
    assert data.index('os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")') < data.index("import h5py")


def test_group_bg_pass_to_plotted_no_stale_name_defined_ignore():
    raw_mixin = Path("src/flexpes_nexafs/plotting/mixin_raw_plot.py").read_text(encoding="utf-8")
    assert "type: ignore[name-defined]" not in raw_mixin
    assert "np.asarray(x_arr[:mlen]" not in raw_mixin


def test_hdf5_drag_drop_and_shared_loader_are_wired():
    ui = Path("src/flexpes_nexafs/ui.py").read_text(encoding="utf-8")
    data = Path("src/flexpes_nexafs/data.py").read_text(encoding="utf-8")
    assert "self.tree.setAcceptDrops(True)" in ui
    assert "installEventFilter(self)" in ui
    assert "def eventFilter" in ui
    assert "self.load_hdf5_paths(paths, source=\"drop\")" in ui
    assert "def load_hdf5_paths" in data
    assert "def refresh_hdf5_file" in data
    assert "Refresh already loaded HDF5 file(s)" in data

def test_normalization_refresh_guards_group_and_nested_payloads():
    helper = Path("src/flexpes_nexafs/hdf5_loading.py").read_text(encoding="utf-8")
    data = Path("src/flexpes_nexafs/data.py").read_text(encoding="utf-8")
    processed = Path("src/flexpes_nexafs/plotting/mixin_processed_plot.py").read_text(encoding="utf-8")
    assert "def normalize_hdf5_path" in helper
    assert "_looks_like_file_path" in helper
    assert "h5load.split_tree_payload" in data
    assert "h5load.normalize_hdf5_path" in processed
    assert "obj = f.get(norm_path, None)" in processed
    assert "isinstance(obj, _h5py.Dataset)" in processed


def test_grid_handler_accepts_programmatic_default_call():
    grid = Path("src/flexpes_nexafs/plotting/mixin_grid_axes.py").read_text(encoding="utf-8")
    raw = Path("src/flexpes_nexafs/plotting/mixin_raw_plot.py").read_text(encoding="utf-8")
    assert "def on_grid_toggled(self, index=None):" in grid
    assert raw.count("self._apply_grid_mode()") >= 3


def test_whats_new_subheadings_are_rendered_without_raw_hash_markers():
    from flexpes_nexafs.utils.help_text import get_whats_new_payload

    html, latest = get_whats_new_payload(current_version="2.4.4", max_versions=1)
    assert latest == "2.4.4"
    assert "####" not in html
    assert "changelog-subheading" in html


def test_mcr_step2_sidebar_and_bounds_are_wired():
    legacy = Path("src/flexpes_nexafs/decomposition/legacy.py").read_text(encoding="utf-8")
    assert "def _build_mcr_sidebar" in legacy
    assert "QGroupBox(\"Constraints\")" in legacy
    assert "✓ Non-negativity of C and S" in legacy
    assert "self.chk_component_bounds = QCheckBox(\"Component bounds\")" in legacy
    assert "self.bounds_table = QTableWidget(0, 3)" in legacy
    assert "setHorizontalHeaderLabels([\"Component\", \"Min %\", \"Max %\"])" in legacy
    assert "self.chk_closure.toggled.connect(self._update_bounds_enabled)" in legacy
    assert "component_bounds=component_bounds" in legacy
    assert "return_diagnostics=True" in legacy
    assert "validate_component_bounds" in legacy


def test_mcr_step2_top_row_keeps_required_controls_and_moves_advanced_controls():
    legacy = Path("src/flexpes_nexafs/decomposition/legacy.py").read_text(encoding="utf-8")
    mcr_init = legacy[legacy.index("class MCRTab"):legacy.index("def _build_mcr_sidebar", legacy.index("class MCRTab"))]
    assert "Auto k (PCA ≥99% EVR)" in legacy
    assert "self.lbl_init = QLabel(\"Init:\")" in mcr_init
    assert "self.lbl_iter = QLabel(\"max_iter:\")" in mcr_init
    assert "self._build_mcr_sidebar()" in mcr_init
    assert "self.lbl_tol = QLabel" not in mcr_init
    assert "self.chk_smooth = QCheckBox" not in mcr_init
    assert "self.chk_closure = QCheckBox" not in mcr_init
    assert "self.spin_tol.setValue(1e-7)" in legacy


def test_mcr_gui_refinements_are_wired():
    legacy = Path("src/flexpes_nexafs/decomposition/legacy.py").read_text(encoding="utf-8")
    assert "def _adjust_bounds_table_height" in legacy
    assert "setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)" in legacy
    assert "setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)" in legacy
    assert "def _init_mcr_busy_indicator" in legacy
    assert "self.ctrl.insertWidget(idx, self.lbl_mcr_busy)" in legacy
    assert "self.chk_show_stability_band.toggled.connect(self._redraw_mcr_concentrations)" in legacy
    assert "def _plot_mcr_concentrations" in legacy
    assert "The band can be shown or hidden after the run without recalculating." in legacy
