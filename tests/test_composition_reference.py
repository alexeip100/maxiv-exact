import numpy as np
import pytest

from maxiv_exact.composition import (
    CompositionError,
    compound_mass_attenuation,
    compound_mass_attenuation_value,
    parse_formula,
)
from maxiv_exact.reference import reference_database


def test_parse_simple_formula_and_mass_fractions():
    db = reference_database()
    comp = parse_formula("Co2O3", db)
    assert comp.amounts == {"Co": 2.0, "O": 3.0}
    assert sum(comp.atomic_fractions.values()) == pytest.approx(1.0)
    assert sum(comp.mass_fractions.values()) == pytest.approx(1.0)
    expected = 2 * db.element_info("Co").molar_mass_g_mol + 3 * db.element_info("O").molar_mass_g_mol
    assert comp.molar_mass_g_mol == pytest.approx(expected)


def test_parse_parentheses_and_fractional_stoichiometry():
    db = reference_database()
    sulfate = parse_formula("Al2(SO4)3", db)
    assert sulfate.amounts == {"Al": 2.0, "S": 3.0, "O": 12.0}
    mixed = parse_formula("La0.7Sr0.3MnO3", db)
    assert mixed.amounts["La"] == pytest.approx(0.7)
    assert mixed.amounts["Sr"] == pytest.approx(0.3)
    assert mixed.amounts["Mn"] == pytest.approx(1.0)
    assert mixed.amounts["O"] == pytest.approx(3.0)


def test_invalid_formula_is_rejected():
    db = reference_database()
    for formula in ("", "Co0O3", "Xx2O3", "Al2(SO4", "Co2O3+"):
        with pytest.raises(CompositionError):
            parse_formula(formula, db)


def test_compound_value_matches_explicit_mass_fraction_sum():
    db = reference_database()
    comp = parse_formula("Co2O3", db)
    energy = 800.0
    expected = sum(
        w * db.interpolate(el, "chantler", "mu_total", energy)
        for el, w in comp.mass_fractions.items()
    )
    actual = compound_mass_attenuation_value(db, comp, "mu_total", energy)
    assert actual == pytest.approx(expected, rel=1e-12)


def test_compound_curve_is_finite_positive_and_contains_constituent_grid_points():
    db = reference_database()
    curve = compound_mass_attenuation(
        db, "Co2O3", "mu_photo", energy_min_eV=100.0, energy_max_eV=2500.0
    )
    assert curve.formula == "Co2O3"
    assert curve.quantity == "mu_photo_cm2_g"
    assert curve.units == "cm^2/g"
    assert np.all(np.diff(curve.energy_eV) > 0)
    assert np.all(np.isfinite(curve.values))
    assert np.all(curve.values > 0)
    assert curve.energy_eV[0] >= 100.0
    assert curve.energy_eV[-1] <= 2500.0


def test_compound_only_accepts_mass_attenuation_quantities():
    db = reference_database()
    with pytest.raises(Exception):
        compound_mass_attenuation_value(db, "Co2O3", "f2", 800.0)


def test_lithium_compound_mu_photo_does_not_crash():
    db = reference_database()
    curve = compound_mass_attenuation(
        db, "LiFePO4", "mu_photo", energy_min_eV=1.1, energy_max_eV=2500.0
    )
    assert curve.formula == "LiFePO4"
    assert np.all(np.isfinite(curve.values))
    assert np.all(curve.values >= 0.0)
    value = compound_mass_attenuation_value(db, "LiFePO4", "mu_photo", 100.0)
    assert np.isfinite(value)
    assert value > 0.0
