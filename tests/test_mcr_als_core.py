import numpy as np
import pytest

from maxiv_exact.decomposition.mcr_als_core import (
    align_mcr_solution_to_reference,
    component_bounds_are_trivial,
    estimate_local_concentration_stability,
    make_random_s_init,
    mcr_als,
    perturb_initial_s,
    project_rows_to_bounded_simplex,
    project_vector_to_bounded_simplex,
    summarize_bound_activity,
    validate_component_bounds,
)


def test_component_bounds_validation_rejects_impossible_closure():
    too_low = validate_component_bounds([0.0, 0.0, 0.0], [0.2, 0.2, 0.2])
    too_high = validate_component_bounds([0.5, 0.5, 0.5], [1.0, 1.0, 1.0])
    assert not too_low.valid
    assert "upper" in too_low.message.lower()
    assert not too_high.valid
    assert "lower" in too_high.message.lower()




def test_full_component_bounds_are_trivial():
    assert component_bounds_are_trivial([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    assert not component_bounds_are_trivial([0.0, 0.0, 0.0], [0.5, 1.0, 1.0])


def test_full_bounds_do_not_change_projected_closed_vector():
    row = np.array([0.2, 0.3, 0.5])
    projected = project_vector_to_bounded_simplex(
        row,
        lower=[0.0, 0.0, 0.0],
        upper=[1.0, 1.0, 1.0],
    )
    assert np.allclose(projected, row)


def test_mcr_als_full_bounds_match_closure_only():
    X = np.array(
        [
            [1.0, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.1, 0.0],
            [0.2, 0.6, 0.4, 0.1],
            [0.0, 0.2, 0.8, 0.5],
        ]
    )
    base = mcr_als(X, k=2, max_iter=8, tol=0.0, closure=True)
    bounded = mcr_als(
        X,
        k=2,
        max_iter=8,
        tol=0.0,
        closure=True,
        component_bounds=([0.0, 0.0], [1.0, 1.0]),
        return_diagnostics=True,
    )
    C0, S0, err0, n_iter0, conv0 = base
    C1, S1, err1, n_iter1, conv1, diagnostics = bounded
    assert diagnostics["bounds_active"] is False
    assert np.allclose(C1, C0)
    assert np.allclose(S1, S0)
    assert np.isclose(err1, err0)
    assert n_iter1 == n_iter0
    assert conv1 == conv0


def test_project_vector_to_bounded_simplex_respects_closure_and_bounds():
    projected = project_vector_to_bounded_simplex(
        [0.8, 0.15, 0.05],
        lower=[0.0, 0.0, 0.0],
        upper=[0.22, 1.0, 1.0],
    )
    assert np.isclose(projected.sum(), 1.0)
    assert np.all(projected >= -1e-12)
    assert projected[0] <= 0.22 + 1e-12


def test_project_rows_to_bounded_simplex_handles_multiple_spectra():
    C = np.array([[2.0, 1.0, 0.0], [0.9, 0.05, 0.05]])
    projected = project_rows_to_bounded_simplex(
        C,
        lower=np.array([0.0, 0.1, 0.0]),
        upper=np.array([0.5, 0.9, 0.9]),
    )
    assert projected.shape == C.shape
    assert np.allclose(projected.sum(axis=1), 1.0)
    assert np.all(projected[:, 0] <= 0.5 + 1e-12)
    assert np.all(projected[:, 1] >= 0.1 - 1e-12)


def test_bound_activity_summary_ignores_trivial_default_bounds():
    C = np.array([[0.22, 0.78], [0.22, 0.78], [0.10, 0.90]])
    activity = summarize_bound_activity(
        C,
        lower=[0.0, 0.0],
        upper=[0.22, 1.0],
        component_names=["Comp 1", "Comp 2"],
        severe_fraction=0.5,
    )
    assert activity.upper_hits.tolist() == [2, 0]
    assert activity.severe
    assert "Comp 1 max 22.0%" in activity.message
    assert "Comp 2" not in activity.message


def test_mcr_als_legacy_return_format_is_unchanged():
    X = np.array(
        [
            [1.0, 0.2, 0.0],
            [0.2, 1.0, 0.2],
            [0.0, 0.2, 1.0],
        ]
    )
    result = mcr_als(X, k=2, max_iter=3, tol=0.0, closure=True)
    assert len(result) == 5
    C, S, err, n_iter, converged = result
    assert C.shape == (3, 2)
    assert S.shape == (2, 3)
    assert np.all(C >= 0)
    assert np.all(S >= 0)
    assert np.allclose(C.sum(axis=1), 1.0)
    assert err >= 0
    assert n_iter == 3
    assert converged is False


def test_mcr_als_can_return_bound_diagnostics_when_requested():
    X = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.8, 0.2, 0.0],
            [0.6, 0.4, 0.0],
        ]
    )
    C, S, err, n_iter, converged, diagnostics = mcr_als(
        X,
        k=2,
        max_iter=4,
        tol=0.0,
        closure=True,
        component_bounds=([0.0, 0.0], [0.3, 1.0]),
        return_diagnostics=True,
    )
    assert np.allclose(C.sum(axis=1), 1.0)
    assert np.all(C[:, 0] <= 0.3 + 1e-12)
    assert diagnostics["bounds_active"] is True
    assert diagnostics["bound_activity"].n_samples == 3


def test_mcr_als_random_seed_is_reproducible():
    X = np.array(
        [
            [1.0, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.1, 0.0],
            [0.2, 0.6, 0.4, 0.1],
            [0.0, 0.2, 0.8, 0.5],
        ]
    )
    a = mcr_als(X, k=2, max_iter=4, tol=0.0, closure=True, random_seed=7)
    b = mcr_als(X, k=2, max_iter=4, tol=0.0, closure=True, random_seed=7)
    assert np.allclose(a[0], b[0])
    assert np.allclose(a[1], b[1])
    assert np.isclose(a[2], b[2])
    assert a[3:] == b[3:]


def test_mcr_als_random_seed_changes_random_start():
    X = np.array(
        [
            [1.0, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.1, 0.0],
            [0.2, 0.6, 0.4, 0.1],
            [0.0, 0.2, 0.8, 0.5],
        ]
    )
    a = mcr_als(X, k=2, max_iter=1, tol=0.0, closure=True, random_seed=1)
    b = mcr_als(X, k=2, max_iter=1, tol=0.0, closure=True, random_seed=2)
    assert not np.allclose(a[1], b[1])


def test_make_random_s_init_is_reproducible():
    a = make_random_s_init(2, 5, random_seed=11)
    b = make_random_s_init(2, 5, random_seed=11)
    c = make_random_s_init(2, 5, random_seed=12)
    assert a.shape == (2, 5)
    assert np.allclose(a, b)
    assert not np.allclose(a, c)


def test_perturb_initial_s_keeps_shape_and_nonnegative_values():
    S0 = np.array([[1.0, 0.5, 0.0], [0.2, 0.3, 0.4]])
    perturbed = perturb_initial_s(S0, perturb_fraction=0.05, random_seed=3)
    assert perturbed.shape == S0.shape
    assert np.all(perturbed >= 0.0)
    assert not np.allclose(perturbed, S0)


def test_align_mcr_solution_to_reference_reorders_components():
    S_ref = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    S_run = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    C_run = np.array([[0.2, 0.8], [0.3, 0.7]])
    C_aligned, S_aligned, perm, scores = align_mcr_solution_to_reference(C_run, S_run, S_ref)
    assert perm == [1, 0]
    assert np.allclose(S_aligned, S_ref)
    assert np.allclose(C_aligned, C_run[:, [1, 0]])
    assert np.all(scores > 0.99)


def test_estimate_local_concentration_stability_returns_sigma_matrix():
    X = np.array(
        [
            [1.0, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.1, 0.0],
            [0.2, 0.6, 0.4, 0.1],
            [0.0, 0.2, 0.8, 0.5],
        ]
    )
    S0 = make_random_s_init(2, X.shape[1], random_seed=5)
    C_ref, S_ref, *_ = mcr_als(X, k=2, S_init=S0, max_iter=4, tol=0.0, closure=True)
    summary = estimate_local_concentration_stability(
        X,
        k=2,
        S_init=S0,
        S_ref=S_ref,
        n_runs=3,
        perturb_fraction=0.02,
        first_seed=100,
        max_iter=4,
        tol=0.0,
        closure=True,
    )
    assert summary.C_std.shape == C_ref.shape
    assert summary.C_mean.shape == C_ref.shape
    assert summary.n_runs == 3
    assert summary.max_std >= 0.0
    assert "Local stability" in summary.message


def test_stability_estimator_reports_progress_callback():
    X = np.array(
        [
            [1.0, 0.2, 0.0, 0.0],
            [0.7, 0.3, 0.1, 0.0],
            [0.2, 0.6, 0.4, 0.1],
            [0.0, 0.2, 0.8, 0.5],
        ]
    )
    S0 = make_random_s_init(2, X.shape[1], random_seed=5)
    _C_ref, S_ref, *_ = mcr_als(X, k=2, S_init=S0, max_iter=2, tol=0.0, closure=True)
    calls = []

    def cb(done, total):
        calls.append((done, total))

    estimate_local_concentration_stability(
        X,
        k=2,
        S_init=S0,
        S_ref=S_ref,
        n_runs=3,
        perturb_fraction=0.02,
        first_seed=100,
        max_iter=2,
        tol=0.0,
        closure=True,
        progress_callback=cb,
    )
    assert calls == [(1, 3), (2, 3), (3, 3)]
