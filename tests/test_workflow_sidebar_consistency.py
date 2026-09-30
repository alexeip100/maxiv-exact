from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "maxiv_exact"


def test_clear_all_and_close_all_return_to_raw_tab():
    core = (PKG / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    data = (PKG / "data.py").read_text(encoding="utf-8")

    clear_block = core[core.index("    def clear_all(self):"):]
    close_block = data[data.index("    def close_file(self):"):data.index("    def close_single_hdf5_file", data.index("    def close_file(self):"))]
    assert "self.data_tabs.setCurrentIndex(0)" in clear_block
    assert "self.data_tabs.setCurrentIndex(0)" in close_block


def test_all_three_curve_sidebars_have_check_and_uncheck_buttons():
    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    assert 'QPushButton("Check all")' in ui
    assert 'QPushButton("Uncheck all")' in ui
    for prefix in ("raw", "proc", "plotted"):
        assert f"self.{prefix}_check_row" in ui
        assert f"self.{prefix}_check_all_button" in ui
        assert f"self.{prefix}_uncheck_all_button" in ui


def test_curve_sidebars_share_one_initial_fraction_and_stretch_ratio():
    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    assert "CURVE_SIDEBAR_FRACTION = 0.25" in ui
    for splitter in ("raw_splitter", "proc_splitter", "plotted_splitter"):
        assert f"self.{splitter}.setStretchFactor(0, 3)" in ui
        assert f"self.{splitter}.setStretchFactor(1, 1)" in ui
        assert f'(\"{splitter}\", self.CURVE_SIDEBAR_FRACTION)' in ui


def test_curve_sidebar_minimum_width_tracks_check_button_text():
    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    appearance = (PKG / "appearance.py").read_text(encoding="utf-8")
    assert ui.count('setProperty("exact_ui_role", "curve_sidebar")') == 3
    assert 'role == "curve_sidebar"' in appearance
    assert 'check.sizeHint().width() + uncheck.sizeHint().width()' in appearance
    assert 'widget.setMinimumWidth(max(original, required))' in appearance


def test_sidebar_bottom_rows_follow_companion_panel_margins():
    ui = (Path(__file__).parents[1] / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
    appearance = (Path(__file__).parents[1] / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    assert "self.proc_sidebar._exact_bottom_margin_source = self.proc_left_widget" in ui
    assert "self.plotted_sidebar._exact_bottom_margin_source = self.plot_left_widget" in ui
    assert 'getattr(widget, "_exact_bottom_margin_source", None)' in appearance
    assert "source.layout().contentsMargins().bottom()" in appearance
