from pathlib import Path


def test_version_metadata_is_250a7():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    init = Path("src/maxiv_exact/__init__.py").read_text(encoding="utf-8")
    assert 'version = "2.5.0"' in pyproject
    assert '__version__ = "2.5.0"' in init
    assert '__date__ = "2026-09-29"' in init


def test_hdf5_locking_is_set_before_h5py_import():
    data = Path("src/maxiv_exact/data.py").read_text(encoding="utf-8")
    assert data.index('os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")') < data.index("import h5py")


def test_group_bg_pass_to_plotted_no_stale_name_defined_ignore():
    raw_mixin = Path("src/maxiv_exact/plotting/mixin_raw_plot.py").read_text(encoding="utf-8")
    assert "type: ignore[name-defined]" not in raw_mixin
    assert "np.asarray(x_arr[:mlen]" not in raw_mixin


def test_hdf5_drag_drop_and_shared_loader_are_wired():
    ui = Path("src/maxiv_exact/ui.py").read_text(encoding="utf-8")
    data = Path("src/maxiv_exact/data.py").read_text(encoding="utf-8")
    assert "self.tree.setAcceptDrops(True)" in ui
    assert "installEventFilter(self)" in ui
    assert "def eventFilter" in ui
    assert "self.load_hdf5_paths(paths, source=\"drop\")" in ui
    assert "def load_hdf5_paths" in data
    assert "def refresh_hdf5_file" in data
    assert "Refresh already loaded HDF5 file(s)" in data

def test_normalization_refresh_guards_group_and_nested_payloads():
    helper = Path("src/maxiv_exact/hdf5_loading.py").read_text(encoding="utf-8")
    data = Path("src/maxiv_exact/data.py").read_text(encoding="utf-8")
    processed = Path("src/maxiv_exact/plotting/mixin_processed_plot.py").read_text(encoding="utf-8")
    assert "def normalize_hdf5_path" in helper
    assert "_looks_like_file_path" in helper
    assert "h5load.split_tree_payload" in data
    assert "h5load.normalize_hdf5_path" in processed
    assert "obj = f.get(norm_path, None)" in processed
    assert "isinstance(obj, _h5py.Dataset)" in processed


def test_grid_handler_accepts_programmatic_default_call():
    grid = Path("src/maxiv_exact/plotting/mixin_grid_axes.py").read_text(encoding="utf-8")
    raw = Path("src/maxiv_exact/plotting/mixin_raw_plot.py").read_text(encoding="utf-8")
    assert "def on_grid_toggled(self, index=None):" in grid
    assert raw.count("self._apply_grid_mode()") >= 3


def test_whats_new_subheadings_are_rendered_without_raw_hash_markers():
    from maxiv_exact.utils.help_text import get_whats_new_payload

    html, latest = get_whats_new_payload(current_version="2.5.0", max_versions=1)
    assert latest == "2.5.0"
    assert "####" not in html
    assert "changelog-subheading" in html


def test_mcr_step2_sidebar_and_bounds_are_wired():
    legacy = Path("src/maxiv_exact/decomposition/legacy.py").read_text(encoding="utf-8")
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
    legacy = Path("src/maxiv_exact/decomposition/legacy.py").read_text(encoding="utf-8")
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
    legacy = Path("src/maxiv_exact/decomposition/legacy.py").read_text(encoding="utf-8")
    assert "def _adjust_bounds_table_height" in legacy
    assert "setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)" in legacy
    assert "setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)" in legacy
    assert "def _init_mcr_busy_indicator" in legacy
    assert "self.ctrl.insertWidget(idx, self.lbl_mcr_busy)" in legacy
    assert "self.chk_show_stability_band.toggled.connect(self._redraw_mcr_concentrations)" in legacy
    assert "def _plot_mcr_concentrations" in legacy
    assert "The band can be shown or hidden after the run without recalculating." in legacy


def test_app_event_loop_is_owned_by_main_not_module_scope():
    import ast

    app_path = Path("src/maxiv_exact/app.py")
    tree = ast.parse(app_path.read_text(encoding="utf-8"))

    top_level_sys_exit = []
    main_fn = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
            main_fn = node
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "sys"
                and call.func.attr == "exit"
            ):
                top_level_sys_exit.append(node)

    assert not top_level_sys_exit
    assert main_fn is not None
    main_src = ast.get_source_segment(app_path.read_text(encoding="utf-8"), main_fn) or ""
    assert "return app.exec()" in main_src


def test_no_legacy_qt5_dialog_or_enum_constants_remain():
    """Guard the PyQt6 migration against Qt5-style dialog/enum constants."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "maxiv_exact"
    forbidden_direct = {
        "QDialog": {"Accepted", "Rejected"},
        "QMessageBox": {"Ok", "Cancel", "Yes", "No", "Close", "Save", "Discard", "Retry", "Abort", "Ignore", "Apply", "Reset", "Help"},
        "QDialogButtonBox": {"Ok", "Cancel", "Yes", "No", "Close", "Save", "Discard", "Retry", "Abort", "Ignore", "Apply", "Reset", "Help"},
        "QFileDialog": {"ExistingFile", "ExistingFiles", "AnyFile", "Directory", "DontUseNativeDialog", "ShowDirsOnly", "ReadOnly"},
        "QAbstractItemView": {"ExtendedSelection", "SingleSelection", "MultiSelection", "NoSelection", "SelectRows", "SelectItems"},
        "QHeaderView": {"Stretch", "ResizeToContents", "Interactive", "Fixed"},
        "QSizePolicy": {"Expanding", "Fixed", "Minimum", "Maximum", "Preferred", "Ignored", "MinimumExpanding"},
    }
    legacy_instance_result_names = {"Accepted", "Rejected"}
    offenders = []
    for source in root.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if isinstance(node.value, ast.Name):
                base = node.value.id
                if base in forbidden_direct and node.attr in forbidden_direct[base]:
                    offenders.append(f"{source.name}:{node.lineno}: {base}.{node.attr}")
                if base in {"dlg", "dialog"} and node.attr in legacy_instance_result_names:
                    offenders.append(f"{source.name}:{node.lineno}: {base}.{node.attr}")
    assert not offenders, "Legacy Qt5 constants remain: " + ", ".join(offenders)


def test_whats_new_stable_release_hides_prerelease_builds():
    from maxiv_exact.utils.help_text import build_whats_new_markdown

    md, latest = build_whats_new_markdown(current_version="2.5.0", max_versions=5)
    assert latest == "2.5.0"
    assert "What changed since 2.4.4" in md
    assert "2.5.0rc1" not in md
    assert "2.5.0a10" not in md

