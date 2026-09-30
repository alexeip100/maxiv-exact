from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
DATA = (ROOT / "src" / "maxiv_exact" / "data.py").read_text(encoding="utf-8")
SPINNER = ROOT / "src" / "maxiv_exact" / "widgets" / "busy_spinner.py"


def test_busy_indicator_is_below_hdf5_tree():
    tree_pos = UI.index("self.left_panel.addWidget(self.tree)")
    busy_pos = UI.index("self.left_panel.addWidget(self.busy_row_widget)")
    right_panel_pos = UI.index("# Right panel: tab widget")
    assert tree_pos < busy_pos < right_panel_pos
    assert "diameter=26" in UI
    assert 'setProperty("exact_ui_role", "busy_row")' in UI
    assert "small_row_height" in (ROOT / "src" / "maxiv_exact" / "ui_metrics.py").read_text(encoding="utf-8")


def test_busy_indicator_is_used_for_file_and_group_loading():
    assert 'self._begin_busy(f"Loading {first_name}...")' in DATA
    assert '"type": "progress"' in (ROOT / "src" / "maxiv_exact" / "hdf5_worker.py").read_text(encoding="utf-8")
    assert 'f"role:{role}"' in UI
    assert 'self._begin_busy(("Loading" if checked else "Clearing") + f" {role} data...")' in UI
    assert SPINNER.is_file()
