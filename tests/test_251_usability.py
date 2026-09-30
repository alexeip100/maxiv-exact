from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plot_canvases_accept_hdf5_drops_via_shared_loader():
    ui = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
    for name in ("canvas_raw", "canvas_proc", "canvas_plotted"):
        assert f"self.{name}.setAcceptDrops(True)" in ui
        assert f"self.{name}.installEventFilter(self)" in ui
    assert "def _handle_hdf5_file_drag_event" in ui
    assert 'self.load_hdf5_paths(paths, source="drop")' in ui


def test_settings_cog_and_dialog_are_wired():
    ui = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
    dialog = (ROOT / "src" / "maxiv_exact" / "widgets" / "settings_dialog.py").read_text(encoding="utf-8")
    assert 'self.settings_button.setText("⚙")' in ui
    assert "self.settings_button.clicked.connect(self.show_settings)" in ui
    assert "apply_appearance_live(dlg.configuration())" in ui
    assert 'self.theme_combo.addItem("System", UiTheme.SYSTEM.value)' in dialog
    assert 'self.theme_combo.addItem("Light", UiTheme.LIGHT.value)' in dialog
    assert 'self.theme_combo.addItem("Dark", UiTheme.DARK.value)' in dialog
    assert 'self.font_combo.addItem("Larger (+1 pt)", 1)' in dialog
    assert 'self.font_combo.addItem("Largest (+2 pt)", 2)' in dialog


def test_appearance_preferences_are_persisted_and_applied_live():
    appearance = (ROOT / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    app = (ROOT / "src" / "maxiv_exact" / "app.py").read_text(encoding="utf-8")
    assert 'QtCore.QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)' in appearance
    assert 'settings.setValue("theme", theme.value)' in appearance
    assert 'settings.setValue("font_offset_pt", font_offset)' in appearance
    assert 'app.setProperty("exact_ui_theme", config.theme.value)' in appearance
    assert 'capture_application_baseline(app)' in app
    assert 'apply_appearance(app)' in app


def test_dark_theme_uses_palette_aware_readable_controls():
    appearance = (ROOT / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    ui = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
    assert "def _dark_palette" in appearance
    assert "QTabBar::tab:selected" in appearance
    assert "QTreeWidget::item:selected" in appearance
    assert "QToolTip" in appearance
    # Fixed grey text from 2.5.0.post1 would be too dark in Dark mode.
    assert 'self.channel_profile_label.setStyleSheet("color: #555;")' not in ui


def test_theme_audit_removes_fixed_dim_text_from_secondary_interfaces():
    legacy = (ROOT / "src" / "maxiv_exact" / "decomposition" / "legacy.py").read_text(encoding="utf-8")
    summation = (ROOT / "src" / "maxiv_exact" / "widgets" / "curve_summation_dialog.py").read_text(encoding="utf-8")
    whats_new = (ROOT / "src" / "maxiv_exact" / "utils" / "help_text.py").read_text(encoding="utf-8")
    assert 'color: #444;' not in legacy
    assert 'color: #555;' not in legacy
    assert 'color: #666;' not in summation
    assert 'background-color:#f2f2f2' not in whats_new
    assert 'background-color:{c["alternate"]}' in whats_new


def test_dark_theme_has_explicit_checkbox_painting_and_disabled_controls():
    appearance = (ROOT / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    assert "class ExactCheckStyle" in appearance
    assert "PE_IndicatorCheckBox" in appearance
    assert "PE_IndicatorItemViewItemCheck" in appearance
    assert "QCheckBox:disabled" in appearance
    assert "QComboBox:disabled" in appearance
    assert "QLabel:disabled" in appearance


def test_font_scaling_uses_shared_ui_metrics_and_no_fixed_setup_width():
    metrics = (ROOT / "src" / "maxiv_exact" / "ui_metrics.py").read_text(encoding="utf-8")
    ui = (ROOT / "src" / "maxiv_exact" / "ui.py").read_text(encoding="utf-8")
    appearance = (ROOT / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    assert "def metrics_for_font_offset" in metrics
    assert "standard_control_height=BASE_METRICS.standard_control_height + 3 * offset" in metrics
    assert "main_tree_min_width=BASE_METRICS.main_tree_min_width + 18 * offset" in metrics
    assert 'setProperty("exact_ui_role", "setup_channels_button")' in ui
    assert "setup_channels_button.setFixedWidth" not in ui
    assert "widget.sizeHint().width()" in appearance
    assert "refresh_ui_metrics(app)" in appearance


def test_tab_geometry_is_theme_independent_and_font_aware():
    appearance = (ROOT / "src" / "maxiv_exact" / "appearance.py").read_text(encoding="utf-8")
    metrics = (ROOT / "src" / "maxiv_exact" / "ui_metrics.py").read_text(encoding="utf-8")
    common_end = appearance.index('if theme is not UiTheme.DARK:')
    common = appearance[:common_end]
    dark = appearance[common_end:]
    assert "tab_h_padding" in metrics
    assert "tab_gap" in metrics
    assert "padding-left: {metrics.tab_h_padding}px" in common
    assert "padding-right: {metrics.tab_h_padding}px" in common
    assert "margin-right: {metrics.tab_gap}px" in common
    # Geometry belongs to the shared block; Dark should add only visual styling.
    assert "padding-left: 10px" not in dark
    assert "margin-right: 2px" not in dark
