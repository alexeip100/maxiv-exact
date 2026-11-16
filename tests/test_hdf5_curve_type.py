import h5py
import numpy as np
import pytest
from maxiv_exact.hdf5_curve_type import is_measurement_path, is_plottable_dtype, paired_raw_axis, raw_curve_axis


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


@pytest.mark.parametrize("x", [None, [1], [1, np.nan], [1, np.inf], [b"a", b"b"], [[1, 2]]])
def test_invalid_sibling_x_falls_back(tmp_path, x):
    with h5py.File(tmp_path / "reference.h5", "w") as file:
        file["y"] = [4, 5]
        if x is not None:
            file["x"] = x
        assert paired_raw_axis(file, "y", 2) is None


def test_pair_preserves_values_order_and_units(tmp_path):
    with h5py.File(tmp_path / "reference.h5", "w") as file:
        file["a/x"] = [530.123456789, 529.1]
        file["a/y"] = [4, 5]
        file["a/x"].attrs["units"] = b"eV"
        file["b/x"] = [12, 17]
        file["b/y"] = [6, 7]
        for path, label in (("a", "Photon energy (eV)"), ("b", "X")):
            x, actual_label, name = paired_raw_axis(file, f"{path}/y", 2)
            np.testing.assert_array_equal(x, file[f"{path}/x"][:])
            assert actual_label == label
            assert name == f"/{path}"
        assert paired_raw_axis(file, "a/x", 2) is None
