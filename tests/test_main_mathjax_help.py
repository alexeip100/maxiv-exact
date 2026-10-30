"""Regression guards for the independent main Help MathJax migration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'maxiv_exact'


def test_main_help_has_mathjax_and_navigation_contract():
    viewer = (ROOT / 'widgets' / 'mathjax_help_browser.py').read_text(encoding='utf-8')
    mixin = (ROOT / 'plotting' / 'mixin_core.py').read_text(encoding='utf-8')
    assert 'tex-svg-full.js' in viewer
    assert '_read_help_markdown' in viewer
    assert 'scrollToAnchor' in viewer
    assert 'findText(query,flags' in viewer
    assert 'set_base_font' in viewer
    assert "MathJaxHelpBrowser(md_filename" in mixin
    assert 'toc.itemClicked.connect(_jump_to_section)' in mixin
    assert 'QShortcut(QKeySequence("F3")' in mixin
    assert 'QShortcut(QKeySequence("Shift+F3")' in mixin
    assert 'browser.set_base_font(int(px))' in mixin
    assert 'browser.setHtml(get_usage_html(md_filename, px))' not in mixin


def test_mathjax_asset_packaged():
    assert (ROOT / 'resources' / 'mathjax' / 'tex-svg-full.js').stat().st_size > 500_000


def test_whats_new_uses_modeless_mathjax_browser():
    mixin = (ROOT / 'plotting' / 'mixin_core.py').read_text(encoding='utf-8')
    portion = mixin.split('def show_whats_new_info', 1)[1]
    assert 'MathJaxHelpBrowser("CHANGELOG.md"' in portion
    assert 'dlg.setModal(False)' in portion
    assert 'dlg.exec()' not in portion.split('def clear_all_except_plotted', 1)[0]
    assert 'self._whats_new_dialog = dlg' in portion
