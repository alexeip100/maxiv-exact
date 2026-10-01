from __future__ import annotations

import numpy as np
import pytest

from maxiv_exact.reference import (
    EnergyOutOfRangeError,
    ReferenceDatabase,
    UnknownQuantityError,
)


@pytest.fixture(scope="module")
def db():
    return ReferenceDatabase()


def test_database_has_both_sources_for_all_92_elements(db):
    elements = db.list_elements()
    assert len(elements) == 92
    assert elements[0] == "H"
    assert elements[-1] == "U"
    assert all(db.sources_for(el) == ("henke", "chantler") for el in elements)


def test_element_and_source_metadata(db):
    fe = db.element_info("fe")
    assert fe.symbol == "Fe"
    assert fe.atomic_number == 26
    assert fe.molar_mass_g_mol == pytest.approx(55.845)
    chantler = db.source_metadata("chantler")
    assert chantler["xraydb_release"] == "4.5.8"
    henke = db.source_metadata("henke")
    assert "CXRO" in henke["display_name"]


def test_quantity_availability_is_source_explicit(db):
    assert db.quantities("O", "henke") == ("f1", "f2")
    assert db.quantities("O", "chantler") == (
        "f1", "f2", "mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g"
    )
    with pytest.raises(UnknownQuantityError):
        db.raw_curve("O", "henke", "mu_total")


def test_raw_henke_f1_preserves_sentinel_but_plot_curve_masks_it(db):
    raw = db.raw_curve("O", "henke", "f1")
    assert np.any(raw.values == -9999.0)
    plotted = db.curve("O", "henke", "f1")
    assert not np.any(plotted.values == -9999.0)
    assert np.any(np.isnan(plotted.values))


def test_plot_curve_keeps_raw_er_energy_quirks(db):
    curve = db.curve("Er", "henke", "f2")
    assert np.any(np.diff(curve.energy_eV) == 0)
    assert np.any(np.diff(curve.energy_eV) < 0)
    diagnostics = db.diagnostics("Er", "henke")
    assert len(diagnostics["source_duplicate_energy_indices"]) == 3
    assert len(diagnostics["source_decreasing_energy_indices"]) == 1


def test_interpolation_curve_is_strictly_increasing(db):
    curve = db.interpolation_curve("Er", "henke", "f2")
    assert np.all(np.diff(curve.energy_eV) > 0)


def test_interpolation_reproduces_tabulated_chantler_values(db):
    curve = db.interpolation_curve("Fe", "chantler", "mu_total")
    idx = len(curve.energy_eV) // 2
    energy = curve.energy_eV[idx]
    expected = curve.values[idx]
    assert db.interpolate("Fe", "chantler", "mu_total", energy) == pytest.approx(expected)


def test_f1_auto_interpolation_is_linear_and_vectorized(db):
    curve = db.interpolation_curve("O", "chantler", "f1")
    i = len(curve.energy_eV) // 3
    e0, e1 = curve.energy_eV[i:i+2]
    y0, y1 = curve.values[i:i+2]
    mid = (e0 + e1) / 2
    expected = (y0 + y1) / 2
    assert db.interpolate("O", "chantler", "f1", mid) == pytest.approx(expected)
    values = db.interpolate("O", "chantler", "f1", [e0, e1])
    np.testing.assert_allclose(values, [y0, y1])


def test_no_extrapolation(db):
    curve = db.interpolation_curve("C", "chantler", "f2")
    with pytest.raises(EnergyOutOfRangeError):
        db.interpolate("C", "chantler", "f2", curve.energy_eV[-1] + 1.0)


def test_soft_xray_limit_is_metadata_not_truncation(db):
    meta = db.database_metadata()
    assert meta["exact_soft_xray_guide_max_eV"] == pytest.approx(2500.0)
    curve = db.raw_curve("Fe", "henke", "f2")
    assert curve.energy_eV[-1] > 2500.0


def test_chantler_raw_f1_is_fprime_but_user_curve_is_full_f1(db):
    raw = db.raw_curve("Co", "chantler", "f1")
    shown = db.curve("Co", "chantler", "f1")
    assert raw.energy_eV.shape == shown.energy_eV.shape
    assert shown.values == pytest.approx(raw.values + 27.0)


def test_chantler_interpolated_f1_uses_full_factor(db):
    raw = db.raw_curve("Co", "chantler", "f1")
    i = len(raw.energy_eV) // 2
    energy = float(raw.energy_eV[i])
    # At an exact source point away from duplicate handling, user-facing f1
    # should be the stored anomalous correction plus atomic number Z=27.
    assert db.interpolate("Co", "chantler", "f1", energy) == pytest.approx(float(raw.values[i]) + 27.0)


def test_li_chantler_zero_threshold_interpolation_is_supported(db):
    raw = db.interpolation_curve("Li", "chantler", "mu_photo")
    zero_idx = np.where(raw.values == 0.0)[0]
    assert len(zero_idx) > 0
    i = int(zero_idx[-1])
    assert raw.values[i] == 0.0
    # Exact source zero must remain zero.
    assert db.interpolate("Li", "chantler", "mu_photo", raw.energy_eV[i]) == pytest.approx(0.0)
    # The interval that crosses from zero to positive must be finite/non-negative.
    e_mid = 0.5 * (raw.energy_eV[i] + raw.energy_eV[i + 1])
    value = db.interpolate("Li", "chantler", "mu_photo", e_mid)
    assert np.isfinite(value)
    assert value >= 0.0
