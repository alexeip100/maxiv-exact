"""Regression check for compact toolbar formatting without requiring Qt."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'maxiv_exact' / 'widgets'


def test_toolbar_coordinate_formatter():
    tree = ast.parse((ROOT / 'fluorescence_toolbar.py').read_text(encoding='utf-8'))
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'single_line_coordinates')
    import re
    scope = {'re': re, '_COORDS': re.compile(r'^\s*\(x,\s*y\)\s*=\s*\(([^,]+),\s*([^\)]+)\)\s*$')}
    exec(compile(ast.Module(body=[func], type_ignores=[]), '<format>', 'exec'), scope)
    fmt = scope['single_line_coordinates']
    assert fmt('(x, y) = (880.28, 419)\n[10.0]') == 'X: 880.28   Y: 419   Z: 10.0'
    assert fmt('(x, y) = (880.28, 419)') == 'X: 880.28   Y: 419'
    assert fmt('') == ''


def test_fa_uses_compact_toolbar():
    src = (ROOT / 'fluorescence_map_dialog.py').read_text(encoding='utf-8')
    assert 'FluorescenceToolbar(self.mapcanvas,mapwidget)' in src
    assert 'FluorescenceToolbar(self.speccanvas,right)' in src
