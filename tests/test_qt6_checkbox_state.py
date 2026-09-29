"""Regression guard for PyQt6 QCheckBox.stateChanged integer states."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "maxiv_exact"


def test_checkbox_handlers_use_qt6_state_helper():
    targets = [
        PKG / "ui.py",
        PKG / "processing.py",
        PKG / "plotting" / "mixin_waterfall.py",
        PKG / "plotting" / "mixin_group_bg.py",
        PKG / "widgets" / "curve_item.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "is_checked_state" in text, path

    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    assert "checked = is_checked_state(state)" in ui
