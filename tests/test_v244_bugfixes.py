from pathlib import Path


def _read(rel):
    return Path(rel).read_text(encoding="utf-8")


def test_csv_save_directory_is_session_only_and_shared_between_main_csv_exports():
    src = _read("src/flexpes_nexafs/export.py")
    assert 'getattr(self, "_last_csv_save_dir", "")' in src
    assert 'self._last_csv_save_dir = directory' in src
    assert 'default_dir = self._csv_save_start_dir(default_dir)' in src
    assert 'self._remember_csv_save_path(save_path)' in src
    # The remembered folder is intentionally just an instance attribute; no persistent settings.
    assert "QSettings" not in src


def test_waterfall_visual_order_matches_plotted_list_and_legend_order():
    src = _read("src/flexpes_nexafs/plotting/mixin_waterfall.py")
    assert "n_curves = len(plotted_keys_in_order)" in src
    assert "(n_curves - 1 - idx) * step" in src


def test_pass_state_counts_only_current_processed_curves():
    src = _read("src/flexpes_nexafs/plotting/mixin_core.py")
    assert 'vc = len(self._visible_processed_keys())' in src
    assert 'vc == 1' in src
