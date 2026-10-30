"""Verify modeless Help windows close with the main EXACT window."""
from pathlib import Path


def test_main_close_closes_help_and_whats_new():
    src = (Path(__file__).resolve().parents[1] / "src/maxiv_exact/ui.py").read_text(encoding="utf-8")
    close_section = src.split("    def closeEvent(self, event):", 1)[1].split("    def open_fl_map_dialog", 1)[0]
    assert '"_help_dialog", "_whats_new_dialog"' in close_section
    assert "window.close()" in close_section
