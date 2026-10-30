"""Regression for 2.6.1: synthetic curves are Processed Data compatible."""
from maxiv_exact.hdf5_curve_type import is_processed_xas_path


def test_existing_synthetic_curve_paths_are_processable():
    assert is_processed_xas_path("__SUM__/FL1/area")
    assert is_processed_xas_path("__SUM__/FL2/area")
    assert is_processed_xas_path("__SUM__/7/area")
    assert is_processed_xas_path("entry5270/measurement/I0")

def test_generic_metadata_remains_raw_only():
    assert not is_processed_xas_path("Scan_5270/Metadata/I0/READ/value")
    assert not is_processed_xas_path("other/data")

def test_processed_plot_uses_classification():
    from pathlib import Path
    source = Path("src/maxiv_exact/plotting/mixin_processed_plot.py").read_text()
    assert "not is_processed_xas_path(str(key).split" in source


def test_pass_action_uses_same_eligibility_as_processed_plot():
    from pathlib import Path
    source = Path("src/maxiv_exact/plotting/mixin_raw_plot.py").read_text()
    guard = source.split("def pass_to_plotted_no_clear(self):", 1)[1].split("if self.chk_sum.isChecked():", 1)[0]
    assert "not is_processed_xas_path(str(k).split" in guard
    assert "not is_measurement_path(str(k).split" not in guard

def test_transfer_key_eligible_for_processed_and_pass():
    source = "C:/data/XAS_SH1_spectrum_for_entry5270.h5"
    keys = [f"{source}##__SUM__/FL1/area", f"{source}##__SUM__/FL2/area"]
    assert all(is_processed_xas_path(k.split("##", 1)[1]) for k in keys)
    assert not is_processed_xas_path("Scan_5270/Metadata/I0/READ/value")
