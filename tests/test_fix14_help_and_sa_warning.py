"""Regression checks for Fix 14 help coverage and the experimental SA gate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "maxiv_exact"


def test_first_time_fluorescence_help_covers_core_workflows():
    controls = (ROOT / "docs" / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (ROOT / "docs" / "usage_workflows.md").read_text(encoding="utf-8")
    for term in ("FL Map Analysis", "pcap_energy_av", "mono_traj_energy", "ROI ± ch", "Pass 2", "Send ROI spectrum to Processed Data", "Send fitted spectra to Processed Data"):
        assert term in controls, term
    for term in ("First map: measured ROI spectra", "Fit fluorescence peaks across the map", "Inspect other 1D HDF5 datasets", "not automatically", "work in progress"):
        assert term in workflows, term


def test_sa_confirmation_cancels_before_opening_dialog():
    source = (ROOT / "self_absorption_controller.py").read_text(encoding="utf-8")
    func = source.split("    def open_self_absorption_dialog(self):", 1)[1].split("    def _remove_self_absorption_window", 1)[0]
    assert "QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel" in func
    assert "QMessageBox.StandardButton.Cancel" in func
    assert func.index("confirmation = QMessageBox.question") < func.index("key = self._self_absorption_visible_keys()[0]")
    assert "if confirmation != QMessageBox.StandardButton.Ok:" in func
