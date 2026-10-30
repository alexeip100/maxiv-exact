"""Regression wiring for bulk free/fixed peak controls."""
from pathlib import Path


def test_master_header_is_tri_state_and_connected():
    source = Path('src/maxiv_exact/widgets/fluorescence_map_dialog.py').read_text()
    assert 'class _PeakToggleHeader(QHeaderView)' in source
    assert 'Qt.CheckState.PartiallyChecked' in source
    assert 'self.peak_header.toggleColumn.connect(self._set_all_peak_freedom)' in source
    assert 'self._sync_peak_header()' in source
    assert "p[key]=bool(checked)" in source
