from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "maxiv_exact" / "widgets" / "reference_panel.py"
UI = ROOT / "src" / "maxiv_exact" / "ui.py"


def test_reference_panel_is_wired_into_main_tabs():
    ui = UI.read_text(encoding="utf-8")
    assert "from .widgets.reference_panel import ReferencePanel" in ui
    assert 'self.reference_tab = ReferencePanel(self)' in ui
    assert 'self.data_tabs.addTab(self.reference_tab, "Reference")' in ui


def test_reference_panel_has_user_facing_controls():
    text = PANEL.read_text(encoding="utf-8")
    for token in (
        '"Elements"',
        '"Source:"',
        '"Quantity:"',
        '"Full source range"',
        '"Henke / CXRO"',
        '"Chantler / XrayDB"',
    ):
        assert token in text


def test_reference_panel_uses_backend_not_direct_hdf5_access():
    text = PANEL.read_text(encoding="utf-8")
    assert "ReferenceDatabase" in text
    assert "reference_database" in text
    assert "h5py" not in text


def test_reference_tab_is_visually_separated_like_panda():
    ui = UI.read_text(encoding="utf-8")
    assert 'self.reference_tab_bar = _SelectionAwareTabBar' in ui
    assert 'setCornerWidget(self.reference_tab_bar, Qt.Corner.TopRightCorner)' in ui
    assert 'setTabVisible(reference_index, False)' in ui


def test_reference_panel_has_comparison_and_live_energy_cursor():
    text = PANEL.read_text(encoding="utf-8")
    for token in (
        '"Henke + Chantler"',
        '"Photon energy:"',
        'self.photon_energy_spin',
        'self._photon_marker',
        'self._intersection_markers',
        'set_draggable(True)',
        'self.values_table',
        'ToolTipRole',
    ):
        assert token in text


def test_reference_help_explains_chantler_fprime_conversion():
    help_text = (ROOT / "src" / "maxiv_exact" / "docs" / "usage_controls.md").read_text(encoding="utf-8")
    assert "# X-ray Reference" in help_text
    assert "Z + f′" in help_text
    assert "The original Chantler `f′` remains unchanged in the frozen database." in help_text


def test_reference_panel_has_compound_formula_entry_and_chantler_only_path():
    text = PANEL.read_text(encoding="utf-8")
    for token in (
        '"Compound(s)"',
        'self.compound_edit',
        'returnPressed.connect(self._apply_compound_formula)',
        'compound_mass_attenuation(',
        'compound_mass_attenuation_value(',
        '("mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g")',
    ):
        assert token in text


def test_active_help_explains_compound_composition_handling():
    controls = (ROOT / "src" / "maxiv_exact" / "docs" / "usage_controls.md").read_text(encoding="utf-8")
    workflow = (ROOT / "src" / "maxiv_exact" / "docs" / "usage_workflows.md").read_text(encoding="utf-8")
    for token in ("Chemical composition and compound mass attenuation", "Co2O3", "mass fraction", "cm²/g", "Density is not required"):
        assert token in controls
    assert "Plot one or several compound mass attenuation coefficients" in workflow
    assert "comma-separated formulas" in controls
    assert "CoO, Co2O3, Co3O4" in controls
    assert "Up to eight compounds" in controls


def test_attenuation_plots_use_log_scale_with_zero_values_masked():
    text = PANEL.read_text(encoding="utf-8")
    assert 'attenuation_quantity = quantity.startswith("mu_")' in text
    assert 'y_plot[y_plot <= 0] = np.nan' in text
    assert 'if attenuation_quantity:\n            self.ax.set_yscale("log")' in text
    assert 'if curve_quantity.startswith("mu_") and numeric_value <= 0:' in text



def test_reference_panel_supports_multiple_compounds():
    text = PANEL.read_text(encoding="utf-8")
    for token in (
        'text.split(",")',
        'len(unique_formula_texts) > 8',
        'self._compounds = compounds',
        'for index, compound in enumerate(self._compounds)',
        'source.startswith("compound:")',
        'self._compounds[compound_index]',
        'f"{len(compounds)} compounds active: "',
    ):
        assert token in text


def test_reference_panel_can_compare_attenuation_quantities_for_one_material():
    text = PANEL.read_text(encoding="utf-8")
    for token in (
        '"mu_compare"',
        '"μ compare"',
        '("mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g")',
        'if quantity == "mu_compare"',
        'if source == "chantler"',
        'if len(self._compounds) == 1',
        'title_quantity = "attenuation comparison" if mu_comparison else definition.label',
    ):
        assert token in text


def test_reference_intersection_marker_is_filled():
    source = Path("src/maxiv_exact/widgets/reference_panel.py").read_text(encoding="utf-8")
    assert 'markerfacecolor=line.get_color()' in source
    assert 'markersize=4.5' in source



def test_reference_plot_has_protected_axis_margins():
    text = PANEL.read_text(encoding="utf-8")
    assert "subplots_adjust(left=0.105, right=0.98, bottom=0.13, top=0.92)" in text
    assert "self.figure.tight_layout(pad=1.0)" not in text


def test_reference_uses_compact_log_tick_formatter():
    source = Path("src/maxiv_exact/widgets/reference_panel.py").read_text(encoding="utf-8")
    assert "class _CompactLogFormatter(LogFormatter):" in source
    assert "set_major_formatter(_CompactLogFormatter(base=10.0))" in source
    assert "set_minor_formatter(_CompactLogFormatter(base=10.0))" in source
    assert 'return rf"$\\times 10^{{{exponent}}}$"' in source
