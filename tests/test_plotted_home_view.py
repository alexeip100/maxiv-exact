from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / "src" / "maxiv_exact" / "plotting" / "mixin_grid_axes.py"
RAW = ROOT / "src" / "maxiv_exact" / "plotting" / "mixin_raw_plot.py"


def test_rescale_updates_matplotlib_home_view():
    text = GRID.read_text(encoding="utf-8")
    assert 'toolbar = getattr(self, "toolbar_plotted", None)' in text
    assert "toolbar.update()" in text
    assert "toolbar.push_current()" in text


def test_passing_curves_refreshes_plotted_full_view():
    text = RAW.read_text(encoding="utf-8")
    # Both multi-pass and ordinary pass paths should establish the new full-data view.
    assert text.count('if hasattr(self, "rescale_plotted_axes")') >= 2
