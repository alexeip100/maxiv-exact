import numpy as np

from maxiv_exact.self_absorption import (
    calibrate,
    flexpes_geometry,
    forward_fraction_distribution,
    forward_thick,
    forward_thick_distribution,
    gaussian_emission_profile,
    invert_thick,
    invert_thick_distribution,
    relative_condition_amplification_distribution,
)
from maxiv_exact.self_absorption_bg import fit_power_law_background


def test_flexpes_geometry_80_30():
    g = flexpes_geometry(80.0, 30.0)
    assert np.isclose(g.beta_deg, 8.649, atol=0.01)
    assert np.isclose(g.factor, 6.5486, rtol=2e-4)


def test_forward_inverse_round_trip_single_energy():
    e = np.linspace(520.0, 570.0, 101)
    mu_x = 3000.0 + 1800.0 * np.exp(-0.5 * ((e - 530.0) / 1.2) ** 2)
    mu_bg = 4500.0 * (e / 520.0) ** -2.0
    mu_f = 4200.0
    g = 6.5
    c = 4.2e14
    signal = forward_thick(mu_x, mu_bg, mu_f, g, c)
    recovered = invert_thick(signal, c, mu_bg, mu_f, g)
    assert np.allclose(recovered, mu_x, rtol=1e-10, atol=1e-8)


def test_gaussian_profile_is_normalized_and_centered():
    p = gaussian_emission_profile(855.0, 5.0, points=161)
    assert np.isclose(np.sum(p.weights), 1.0, rtol=1e-14)
    assert np.isclose(np.sum(p.weights * p.energy_eV), 855.0, atol=1e-10)
    assert np.isclose(p.fwhm_eV, 5.0)


def test_distribution_constant_mu_f_matches_single_energy():
    e = np.linspace(840.0, 890.0, 101)
    mu_x = 3000.0 + 4000.0 * np.exp(-0.5 * ((e - 853.0) / 1.3) ** 2)
    mu_bg = 2800.0 * (e / 840.0) ** -1.0
    mu_f = 5000.0
    g = 6.5
    p = gaussian_emission_profile(855.0, 5.0)
    mu_f_values = np.full_like(p.energy_eV, mu_f)
    q_dist = forward_fraction_distribution(mu_x, mu_bg, mu_f_values, p.weights, g)
    q_single = forward_thick(mu_x, mu_bg, mu_f, g, 1.0)
    assert np.allclose(q_dist, q_single, rtol=1e-12, atol=1e-14)


def test_distribution_forward_inverse_round_trip_varying_attenuation():
    e = np.linspace(840.0, 890.0, 81)
    mu_x = 2500.0 + 3000.0 * np.exp(-0.5 * ((e - 853.0) / 1.5) ** 2)
    mu_bg = 3000.0 * (e / 840.0) ** -1.2
    p = gaussian_emission_profile(855.0, 5.0, points=121)
    mu_f_values = 3000.0 + 7000.0 / (1.0 + np.exp(-(p.energy_eV - 855.0) / 0.7))
    g = 6.5
    c = 8.0e13
    signal = forward_thick_distribution(mu_x, mu_bg, mu_f_values, p.weights, g, c)
    recovered = invert_thick_distribution(signal, c, mu_bg, mu_f_values, p.weights, g)
    assert np.allclose(recovered, mu_x, rtol=2e-8, atol=1e-6)


def test_distribution_condition_reduces_to_single_result_for_constant_mu_f():
    e = np.linspace(520.0, 570.0, 51)
    mu_x = np.linspace(1000.0, 5000.0, e.size)
    mu_bg = np.full_like(mu_x, 4000.0)
    p = gaussian_emission_profile(525.0, 4.0)
    mu_f_values = np.full_like(p.energy_eV, 4200.0)
    g = 6.5
    q = forward_fraction_distribution(mu_x, mu_bg, mu_f_values, p.weights, g)
    amp = relative_condition_amplification_distribution(mu_x, mu_bg, mu_f_values, p.weights, g)
    assert np.allclose(amp, 1.0 / (1.0 - q), rtol=1e-11, atol=1e-12)


def test_calibration_recovers_scale():
    q = np.linspace(0.07, 0.11, 50)
    c_true = 7.5e12
    signal = c_true * q
    result = calibrate(signal, q)
    assert np.isclose(result.scale_c, c_true, rtol=1e-12)
    assert np.isclose(result.y_max, q.max(), rtol=1e-12)


def test_power_law_fit_recovers_exponent():
    e = np.linspace(500.0, 600.0, 200)
    p_true = 2.15
    mu = 8.3e8 * e ** (-p_true)
    fit = fit_power_law_background(e, mu, fraction=0.2)
    assert np.isclose(fit.exponent, p_true, rtol=1e-10)
    assert fit.rms_relative < 1e-10


def test_experimental_bg_tail_constraint_reproduces_soft_slope():
    from maxiv_exact.experimental_background import fit_experimental_background
    import numpy as np
    x = np.linspace(840, 890, 1001)
    y = 10 + 0.03 * (x - 840) + 0.008 * (x - 840)**2
    y += 20 * np.exp(-0.5*((x-853)/1.2)**2)
    no, d0 = fit_experimental_background(x, y, .12, 2, match_tail_slope=False)
    yes, d1 = fit_experimental_background(x, y, .12, 2, match_tail_slope=True)
    assert d1.slope_constrained and not d0.slope_constrained
    assert np.isfinite(yes).all()
    assert abs(d1.fitted_end_slope - d1.tail_slope) < abs(d0.fitted_end_slope - d0.tail_slope)
    assert np.max(np.abs(yes - no)) > 0.01


def test_experimental_bg_degree_zero_tolerates_end_slope():
    from maxiv_exact.experimental_background import fit_experimental_background
    import numpy as np
    x = np.linspace(10, 20, 101)
    y = x**2
    b, diag = fit_experimental_background(x, y, .12, 0, match_tail_slope=True)
    assert np.allclose(b, b[0])
    assert diag.fitted_end_slope == 0
