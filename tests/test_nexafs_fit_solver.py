"""Regression checks for the NEXAFS fitting objective and constraints."""

from dataclasses import replace

import numpy as np
import pytest

from maxiv_exact.nexafs_fit.group import GroupBGSettings, ProcessedGroup, ProcessedSpectrum
from maxiv_exact.nexafs_fit.model import (
    FitComponent, FitModel, Gaussian, IPStep, ParameterMode, StepForm, evaluate_model,
)
from maxiv_exact.nexafs_fit.solver import (
    FitCancelled, _Problem, _samples, fit_pass1, fit_pass2, fit_reference,
)


def _group(grids, components):
    spectra = tuple(
        ProcessedSpectrum(str(i), f"Scan {i}", x, evaluate_model(x, values), (x[0], x[-1]))
        for i, (x, values) in enumerate(zip(grids, components))
    )
    return ProcessedGroup("synthetic", GroupBGSettings(2, 0.15, False, None), spectra)


def test_reference_and_pass1_recover_areas_and_heights_with_fixed_shapes():
    grids = [np.linspace(280, 310, 121)] * 3
    truth = [
        (Gaussian(288, 2.5, a), Gaussian(289.1, 2.8, b), IPStep(294, 2.1, h, StepForm.ARCTAN))
        for a, b, h in [(0.6, 0.2, 0.05), (0.2, 0.65, 0.07), (0.4, 0.4, 0.03)]
    ]
    group = _group(grids, truth)
    model = FitModel((
        FitComponent("peak A", Gaussian(288, 2.5, 0.1)),
        FitComponent("peak B", Gaussian(289.1, 2.8, 0.1)),
        FitComponent("IP", IPStep(294, 2.1, 0.01, StepForm.ARCTAN)),
    ), (284, 307))

    reference = fit_reference(group, model)
    assert reference.spectra[0].diagnostics.converged
    a, b, ip = reference.spectra[0].components
    assert (a.area, b.area, ip.height) == pytest.approx((0.4, 1.25 / 3, 0.05))
    individual = fit_reference(group, model, spectrum_key="1").spectra[0]
    assert individual.components[1].area == pytest.approx(0.65)

    result = fit_pass1(group, model, reference=reference)
    for row, expected in zip(result.spectra, truth):
        assert row.diagnostics.converged
        assert row.diagnostics.rms < 1e-12
        assert row.energy.min() >= 284 and row.energy.max() <= 307
        a, b, ip = row.components
        assert (a.area, b.area, ip.height) == pytest.approx((expected[0].area, expected[1].area, expected[2].height))
        assert (a.center, a.fwhm, ip.fwhm) == (288, 2.5, 2.1)
        np.testing.assert_array_equal(row.residual, row.observed - row.prediction)
    assert model.components[0].initial.area == 0.1


def test_global_nonlinear_fit_recovers_shared_and_independent_shapes_on_native_grids():
    grids = [280 + 28 * np.linspace(0, 1, n)**power for n, power in [(149, 1), (203, 1.4), (296, 0.8)]]
    truth = [
        (Gaussian(288.1, 2.2, 0.45 + 0.08 * i), Gaussian(289.2 + 0.18 * i, 2.7, 0.3 - 0.03 * i),
         IPStep(291.8, 2.4, 0.055), IPStep(299.3, 3.5, 0.02 + 0.004 * i, StepForm.ARCTAN))
        for i in range(3)
    ]
    group = _group(grids, truth)
    model = FitModel((
        FitComponent("A", Gaussian(287.85, 2.4, 0.3), ParameterMode.SHARED, ParameterMode.SHARED,
                     position_bounds=(287.5, 288.5), width_bounds=(1.5, 3.0)),
        FitComponent("B", Gaussian(289.7, 2.7, 0.25), ParameterMode.INDEPENDENT,
                     position_bounds=(288.8, 290.2)),
        FitComponent("IP 1", IPStep(292.2, 2.1, 0.04), ParameterMode.SHARED, ParameterMode.SHARED,
                     amplitude_mode=ParameterMode.SHARED),
        FitComponent("IP 2", IPStep(299.3, 3.5, 0.015, StepForm.ARCTAN)),
    ))
    reference = fit_reference(group, model)
    independent = fit_pass1(group, model, reference=reference)
    for row in independent.spectra:
        assert row.diagnostics.converged
        assert row.diagnostics.rms < 1e-7
    original_residuals = [row.residual.copy() for row in independent.spectra]
    global_result = fit_pass2(group, model, pass1=independent)
    assert global_result.global_diagnostics.converged, global_result.global_diagnostics
    assert global_result.global_diagnostics.rms < 1e-7
    for i, (row, expected) in enumerate(zip(global_result.spectra, truth)):
        np.testing.assert_array_equal(row.energy, grids[i])
        a, b, step, step2 = row.components
        assert (a.center, a.fwhm, a.area) == pytest.approx((expected[0].center, expected[0].fwhm, expected[0].area), abs=3e-5)
        assert (b.center, b.fwhm, b.area) == pytest.approx((expected[1].center, expected[1].fwhm, expected[1].area), abs=3e-5)
        assert (step.position, step.fwhm, step.height) == pytest.approx(
            (expected[2].position, expected[2].fwhm, expected[2].height), abs=3e-5
        )
        assert step2.height == pytest.approx(expected[3].height, abs=3e-5)
        assert a.center == global_result.spectra[0].components[0].center
        assert step.height == global_result.spectra[0].components[2].height
        np.testing.assert_array_equal(independent.spectra[i].residual, original_residuals[i])
        assert not row.residual.flags.writeable


def test_global_linear_fit_uses_mean_squared_residual_per_spectrum():
    # Repeated grid densities must not multiply a scan's weight. Nonuniform
    # sampling is intentionally left native, so the analytic answer uses each
    # scan's own mean squared unit basis rather than a point-count average.
    grids = [280 + 20 * np.linspace(0, 1, n)**power for n, power in [(41, 1), (301, 1.5), (1201, 0.8)]]
    heights = [0.02, 0.07, 0.12]
    group = _group(grids, [(IPStep(291, 2.0, h),) for h in heights])
    model = FitModel((FitComponent("IP", IPStep(291, 2.0, 0), amplitude_mode=ParameterMode.SHARED),))
    result = fit_pass2(group, model)
    unit = IPStep(291, 2.0, 1)
    weights = [np.mean(unit.evaluate(x)**2) for x in grids]
    expected = np.average(heights, weights=weights)
    assert result.global_diagnostics.converged
    assert expected != pytest.approx(np.average(heights, weights=np.array(weights) * [len(x) for x in grids]))
    for row in result.spectra:
        assert row.components[0].height == pytest.approx(expected, abs=1e-10)
    assert result.global_diagnostics.rms == pytest.approx(
        np.sqrt(np.mean([np.mean(row.residual**2) for row in result.spectra]))
    )


def test_degenerate_peaks_and_nonnegative_bounds_are_visible_in_diagnostics():
    grids = [np.linspace(282, 300, 241)] * 3
    group = _group(grids, [(Gaussian(289, 3, 0.4), IPStep(295, 2, -0.08))] * 3)
    model = FitModel((
        FitComponent("A", Gaussian(289, 3, 0.3)),
        FitComponent("duplicate A", Gaussian(289, 3, 0.2)),
        FitComponent("IP", IPStep(295, 2, 0.01)),
    ))
    row = fit_reference(group, model, spectrum_key="0").spectra[0]
    assert row.diagnostics.converged
    assert row.components[-1].height == pytest.approx(0, abs=1e-8)
    assert any("IP height" in hit and "lower bound" in hit for hit in row.diagnostics.bounds_reached)
    assert any("correlated" in warning for warning in row.diagnostics.warnings)
    assert row.diagnostics.condition_number >= 1e6
    assert row.diagnostics.rms > 0
    assert row.diagnostics.status > 0 and row.diagnostics.optimality is not None
    assert row.diagnostics.nit is not None and row.diagnostics.nfev is None


def test_pass1_reports_insufficient_scan_and_global_fit_does_not_drop_it():
    grids = [np.linspace(280, 300, n) for n in (101, 3, 101)]
    group = _group(grids, [(IPStep(292, 2, 0.07),)] * 3)
    model = FitModel((FitComponent("IP", IPStep(292, 2, 0.05)),), (288, 296))
    result = fit_pass1(group, model)
    assert [row.diagnostics.converged for row in result.spectra] == [True, False, True]
    assert "fewer than three" in result.spectra[1].diagnostics.message
    with pytest.raises(ValueError, match="Scan 1"):
        fit_pass2(group, model)
    with pytest.raises(FitCancelled):
        fit_pass1(group, model, cancelled=lambda: True)


@pytest.mark.parametrize("vary_positions", [True, False])
def test_analytic_global_jacobian_matches_finite_differences(vary_positions):
    mode = ParameterMode
    grids = [280 + 25 * np.linspace(0, 1, n)**power for n, power in [(97, 1), (121, 1.3), (140, 0.8)]]
    definitions = (
        FitComponent("A", Gaussian(288, 2.6, .17), mode.SHARED, mode.INDEPENDENT),
        FitComponent("B", Gaussian(289.3, 3.1, .31), mode.INDEPENDENT, mode.FIXED),
        FitComponent("Edge 1", IPStep(291, 2.8, .042), mode.FIXED, mode.SHARED,
                     amplitude_mode=mode.SHARED),
        FitComponent("Edge 2", IPStep(294, 4.1, .021, StepForm.ARCTAN), mode.SHARED, mode.INDEPENDENT),
    )
    if not vary_positions:
        definitions = tuple(replace(spec, position_mode=mode.FIXED) for spec in definitions)
    model = FitModel(definitions)
    group = _group(grids, [tuple(spec.initial for spec in definitions)] * 3)
    scans = [_samples(spectrum) for spectrum in group.spectra]
    problem = _Problem(scans, model, (280, 305), {}, True, None)

    # Every free coordinate is checked in the actual weighted, packed system.
    q = problem.start
    analytic = problem._evaluate(q, jacobian=True).toarray()
    numeric = np.empty_like(analytic)
    for col, value in enumerate(q):
        step = 2e-6 * max(1, abs(value))
        direction = np.zeros_like(q)
        direction[col] = step
        numeric[:, col] = (problem._evaluate(q + direction) - problem._evaluate(q - direction)) / (2 * step)
    np.testing.assert_allclose(analytic, numeric, rtol=2e-6, atol=2e-9)
    relative = np.linalg.norm(analytic - numeric, axis=0) / np.linalg.norm(numeric, axis=0)
    assert np.max(relative) < 2e-7
    amplitude_matrix = problem._evaluate(q, jacobian=True, amplitude_only=True).toarray()
    np.testing.assert_allclose(amplitude_matrix, analytic[:, problem.amplitudes], atol=1e-15)


@pytest.mark.parametrize("points, solver", [(91, "TRF exact (dense)"), (1121, "TRF LSMR (sparse)")])
def test_global_solver_paths_recover_shapes_on_different_jacobian_sizes(points, solver):
    mode = ParameterMode
    grids = [np.linspace(280, 320, points) for _ in range(8)]
    peaks = (286, 290, 295, 302)
    truth = [
        tuple(Gaussian(pos + .01*i, 2 + .025*i, .07 + .005*i) for pos in peaks)
        + (IPStep(305, 2.2, .038), IPStep(312 + .015*i, 2.1, .016, StepForm.ARCTAN))
        for i in range(8)
    ]
    model = FitModel(tuple(
        FitComponent(f"G{i}", Gaussian(center + .1, 2.15, .06), mode.INDEPENDENT, mode.INDEPENDENT)
        for i, center in enumerate(peaks)
    ) + (
        FitComponent("IP1", IPStep(305.1, 2.2, .03), mode.SHARED, mode.INDEPENDENT, amplitude_mode=mode.SHARED),
        FitComponent("IP2", IPStep(312.1, 2, .01, StepForm.ARCTAN), mode.INDEPENDENT, mode.INDEPENDENT),
    ))
    result = fit_pass2(_group(grids, truth), model)
    diagnostics = result.global_diagnostics
    assert diagnostics.solver == solver and diagnostics.converged
    assert diagnostics.status > 0 and diagnostics.nfev > 0 and diagnostics.optimality is not None
    assert diagnostics.rms < 1e-8
    for row, expected in zip(result.spectra, truth):
        assert row.usable and row.diagnostics.status == diagnostics.status
        for fit, target in zip(row.components, expected):
            assert fit.fwhm == pytest.approx(target.fwhm, abs=1e-5)
            if isinstance(fit, Gaussian):
                assert (fit.center, fit.area) == pytest.approx((target.center, target.area), abs=1e-5)
            else:
                assert (fit.position, fit.height) == pytest.approx((target.position, target.height), abs=1e-5)
