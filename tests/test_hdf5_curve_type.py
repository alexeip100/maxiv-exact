import numpy as np
from maxiv_exact.hdf5_curve_type import is_measurement_path, is_plottable_dtype, raw_curve_axis


def test_measurement_vs_metadata():
    assert is_measurement_path("entry5270/measurement/pcap_energy_av")
    assert not is_measurement_path("Scan_5270/Metadata/I0/READ/value")
    assert not is_measurement_path("entry5270/plot_1/data")


def test_dtype_filter():
    for dtype in ("float64", "int32", "uint16", "bool"):
        assert is_plottable_dtype(dtype)
    for dtype in ("S8", "complex64", "object"):
        assert not is_plottable_dtype(dtype)


def test_generic_dataset_uses_index_even_if_lookup_available():
    def invalid():
        raise AssertionError("energy lookup must not run")
    np.testing.assert_array_equal(raw_curve_axis("Scan_5270/Metadata/value", 3, invalid), [0, 1, 2])


def test_measurement_uses_original_energy_lookup():
    np.testing.assert_allclose(raw_curve_axis("entry5270/measurement/channel", 2,
        lambda: np.array([840.1, 840.2])), [840.1, 840.2])
