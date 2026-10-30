"""Source-level guard for GUI validation (PyQt6 is optional in headless CI)."""
from pathlib import Path


def test_peak_editor_rejects_invalid_values_and_restores_ui():
    src = (Path(__file__).resolve().parents[1] / 'src/maxiv_exact/widgets/fluorescence_map_dialog.py').read_text(encoding='utf-8')
    method = src.split('    def _edit_peaks(self,item):', 1)[1].split('    def add_peak(self):', 1)[0]
    assert "if val<0:raise ValueError('Peak area cannot be negative.')" in method
    assert "if val<=0:raise ValueError('FWHM must be greater than zero.')" in method
    assert 'if not math.isfinite(val):' in method
    assert "raise ValueError('Peak center must lie within the detector range.')" in method
    assert 'self._populate_peaks()' in method
    assert "self.status.setText(f'Invalid peak parameter: {ex}')" in method
