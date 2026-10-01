from pathlib import Path


def test_reference_toolbar_home_uses_exact_reset_callback():
    text = Path('src/maxiv_exact/widgets/reference_panel.py').read_text(encoding='utf-8')
    assert 'class ReferenceNavigationToolbar(NavigationToolbar):' in text
    assert 'self._reference_reset_callback()' in text
    assert 'ReferenceNavigationToolbar(self.canvas, right, self._reset_reference_view)' in text


def test_reference_default_view_is_recorded_after_current_range_is_applied():
    text = Path('src/maxiv_exact/widgets/reference_panel.py').read_text(encoding='utf-8')
    xlim_pos = text.index('self.ax.set_xlim(visible_min, visible_max)')
    store_pos = text.index('self._default_view_limits = (self.ax.get_xlim(), self.ax.get_ylim())')
    assert store_pos > xlim_pos
    assert 'def _reset_reference_view(self) -> None:' in text
    assert 'self.ax.set_xlim(*xlim)' in text
    assert 'self.ax.set_ylim(*ylim)' in text
