from pathlib import Path


def _treeviews_source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "src" / "flexpes_nexafs" / "ui_treeviews.py").read_text(encoding="utf-8")


def test_tree_icons_do_not_pass_matplotlib_tuple_directly_to_qcolor():
    text = _treeviews_source()
    assert "pixmap.fill(QColor(color))" not in text
    assert "_qcolor_from_curve_color(color)" in text


def test_tree_color_conversion_supports_rgb_and_rgba_sequences():
    text = _treeviews_source()
    assert "isinstance(color, (tuple, list, np.ndarray))" in text
    assert "QColor.fromRgbF" in text
    assert "len(values) not in (3, 4)" in text


def test_both_raw_and_processed_tree_paths_use_safe_color_conversion():
    text = _treeviews_source()
    assert text.count("qcolor = _qcolor_from_curve_color(color)") == 2
    assert text.count("if color is not None:") >= 2
