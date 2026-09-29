from pathlib import Path


def _source(name: str) -> str:
    root = Path(__file__).resolve().parents[1] / "src" / "maxiv_exact"
    return (root / name).read_text(encoding="utf-8")


def test_clear_plotted_button_uses_confirmation_handler():
    ui = _source("ui.py")
    assert "clear_plotted_data_button.clicked.connect(self.confirm_clear_plotted_data)" in ui


def test_clear_plotted_confirmation_matches_reference_behavior():
    src = _source("plotting/mixin_raw_plot.py")
    assert '"Clear plotted curves"' in src
    assert '"Do you want to clear all plotted curves?"' in src
    assert "QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel" in src
    assert "QMessageBox.StandardButton.Cancel" in src
    assert "if answer == QMessageBox.StandardButton.Ok:" in src
