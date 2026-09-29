from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = (ROOT / "src" / "maxiv_exact" / "data.py").read_text(encoding="utf-8")
UI = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
WORKER = (ROOT / "src" / "maxiv_exact" / "hdf5_worker.py").read_text(encoding="utf-8")


def test_new_hdf5_files_are_scanned_in_separate_process():
    assert "process = QProcess(self)" in DATA
    assert 'worker_args = ["-m", "maxiv_exact.hdf5_worker", *new_paths]' in DATA
    assert 'QTimer.singleShot(0, lambda p=process, a=worker_args: p.start(sys.executable, a))' in DATA
    assert "process.readyReadStandardOutput.connect(self._read_hdf5_process_stdout)" in DATA
    assert "process.finished.connect(self._finish_hdf5_process_load)" in DATA


def test_worker_is_qt_free_and_returns_plain_payloads():
    assert "from PyQt5" not in WORKER
    assert '"root_children": root_children' in WORKER
    assert '"norm_channels": norm_channels' in WORKER
    assert 'with _open_h5_read(abs_path) as f:' in WORKER


def test_redundant_drop_loading_status_removed():
    assert "Loading dropped HDF5 file(s)" not in UI
    assert "Drop HDF5 file(s) to load" not in UI


def test_overlapping_hdf5_loads_are_guarded():
    assert "process is not None and process.state() != QProcess.ProcessState.NotRunning" in DATA
    assert "An HDF5 file is already being loaded." in DATA


def test_gui_path_validation_does_not_stat_network_files():
    """New-file loading must not call os.path.isfile/stat in the GUI thread."""
    start = DATA.index("    def load_hdf5_paths")
    end = DATA.index("    def _record_hdf5_async_failure", start)
    src = DATA[start:end]
    assert "require_exists=False" in src
    assert "require_exists=True" not in src


def test_background_process_start_is_deferred_to_event_loop():
    """Allow the busy row to paint before launching the loader process."""
    start = DATA.index("    def load_hdf5_paths")
    end = DATA.index("    def _record_hdf5_async_failure", start)
    src = DATA[start:end]
    assert "QTimer.singleShot(0" in src
    assert "p.start(sys.executable" in src


def test_recursive_all_channel_scan_is_done_in_worker():
    assert '"all_channels": sorted(all_channels' in WORKER
    assert 'f.visititems(_visit)' in WORKER
    assert 'cache[abs_path] = list(payload.get("all_channels", []) or [])' in DATA


def test_new_file_all_channel_refresh_uses_worker_cache():
    """Normal async load must cache channel metadata before scheduling combo refresh."""
    start = DATA.index("    def _apply_loaded_hdf5_payload")
    end = DATA.index("    def _apply_norm_channels", start)
    src = DATA[start:end]
    cache_pos = src.index('cache[abs_path] = list(payload.get("all_channels", []) or [])')
    refresh_pos = src.index('QTimer.singleShot(0, getattr(self, "_refresh_all_in_channel_combo"')
    assert cache_pos < refresh_pos


def test_busy_loading_status_uses_ascii_ellipsis():
    assert 'self._begin_busy(f"Loading {first_name}...")' in DATA
    assert 'f"Loading {os.path.basename(abs_path)}..."' in WORKER
