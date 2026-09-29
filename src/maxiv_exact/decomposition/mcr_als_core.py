"""Numerical helpers for MCR-ALS decomposition.

This module intentionally contains no Qt code so the MCR-ALS core can be
unit-tested without launching the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from itertools import permutations

import numpy as np

try:  # pragma: no cover - exercised implicitly when scipy is installed
    from scipy.optimize import nnls as sp_nnls

    HAVE_SCIPY = True
except Exception:  # pragma: no cover - fallback path depends on environment
    sp_nnls = None
    HAVE_SCIPY = False


@dataclass(frozen=True)
class BoundsValidation:
    """Result of validating component fraction bounds."""

    valid: bool
    message: str = ""


@dataclass(frozen=True)
class BoundActivity:
    """How often fitted component fractions reached their bounds."""

    lower_hits: np.ndarray
    upper_hits: np.ndarray
    n_samples: int
    severe: bool
    message: str


@dataclass(frozen=True)
class StabilitySummary:
    """Run-to-run stability of MCR-ALS concentration profiles."""

    C_mean: np.ndarray
    C_std: np.ndarray
    n_runs: int
    median_std: float
    max_std: float
    mean_match_score: float
    message: str


def nnls_solve(A, b):
    """Solve non-negative least squares: min_x ||Ax - b||^2, x >= 0."""
    if HAVE_SCIPY:
        x, _ = sp_nnls(A, b)
        return x

    # Fallback: Tikhonov-regularized least squares + projection. This is less
    # exact than scipy.optimize.nnls but preserves the non-negative contract.
    A = np.asarray(A, dtype=float)
    b = np.asarray(b, dtype=float)
    AtA = A.T @ A + 1e-10 * np.eye(A.shape[1])
    Atb = A.T @ b
    x = np.linalg.solve(AtA, Atb)
    return np.maximum(x, 0.0)


def tikhonov_smooth_matrix(S, lam=0.0):
    """Simple 1D Tikhonov smoothing on each row of S."""
    S = np.asarray(S, dtype=float)
    lam = float(lam)
    if lam <= 0.0:
        return S

    k, m = S.shape
    S_sm = S.copy()
    for r in range(k):
        y = S[r]
        if m < 3:
            continue
        main = (1 + 2 * lam) * np.ones(m)
        off = (-lam) * np.ones(m - 1)
        cprime = np.zeros(m - 1)
        dprime = np.zeros(m)
        cprime[0] = off[0] / main[0]
        dprime[0] = y[0] / main[0]
        for i in range(1, m - 1):
            denom = main[i] - off[i - 1] * cprime[i - 1]
            cprime[i] = off[i] / denom
            dprime[i] = (y[i] - off[i - 1] * dprime[i - 1]) / denom
        denom = main[m - 1] - off[m - 2] * cprime[m - 2]
        dprime[m - 1] = (y[m - 1] - off[m - 2] * dprime[m - 2]) / denom
        x = np.zeros(m)
        x[m - 1] = dprime[m - 1]
        for i in range(m - 2, -1, -1):
            x[i] = dprime[i] - cprime[i] * x[i + 1]
        S_sm[r] = np.maximum(x, 0.0)
    return S_sm


def _as_1d_bounds(values: Iterable[float], k: int, name: str) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    if arr.shape != (k,):
        raise ValueError(f"{name} must contain exactly {k} values.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain only finite numbers.")
    return arr


def validate_component_bounds(lower, upper, k: int | None = None, target_sum: float = 1.0) -> BoundsValidation:
    """Validate fractional component bounds for closure-constrained C rows.

    Bounds must be fractions, not percentages. For example, 22% is 0.22.
    """
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    if k is None:
        if lower.shape != upper.shape or lower.ndim != 1:
            return BoundsValidation(False, "Lower and upper bounds must be one-dimensional arrays of equal length.")
        k = int(lower.size)
    try:
        lower = _as_1d_bounds(lower, k, "Lower bounds")
        upper = _as_1d_bounds(upper, k, "Upper bounds")
    except ValueError as exc:
        return BoundsValidation(False, str(exc))

    if target_sum <= 0 or not np.isfinite(target_sum):
        return BoundsValidation(False, "Target sum must be a positive finite number.")
    if np.any(lower < 0.0) or np.any(upper < 0.0):
        return BoundsValidation(False, "Component bounds must not be negative.")
    if np.any(lower > upper):
        return BoundsValidation(False, "Each lower bound must be smaller than or equal to its upper bound.")
    if lower.sum() - target_sum > 1e-12:
        return BoundsValidation(False, "The sum of lower bounds is larger than the closure total.")
    if target_sum - upper.sum() > 1e-12:
        return BoundsValidation(False, "The sum of upper bounds is smaller than the closure total.")
    return BoundsValidation(True, "")




def component_bounds_are_trivial(lower, upper, *, target_sum: float = 1.0, tol: float = 1e-12) -> bool:
    """Return True when bounds add no restriction beyond closure/non-negativity."""
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    return (
        lower.ndim == 1
        and upper.shape == lower.shape
        and np.allclose(lower, 0.0, atol=tol, rtol=0.0)
        and np.allclose(upper, target_sum, atol=tol, rtol=0.0)
    )

def project_vector_to_bounded_simplex(v, lower, upper, target_sum: float = 1.0, *, tol: float = 1e-12) -> np.ndarray:
    """Project one vector onto lower <= x <= upper and sum(x)=target_sum.

    The projection is the Euclidean projection onto a bounded simplex. Bounds
    are interpreted as fractions when target_sum is 1.
    """
    v = np.asarray(v, dtype=float)
    if v.ndim != 1:
        raise ValueError("v must be a one-dimensional vector.")
    k = int(v.size)
    lower = _as_1d_bounds(lower, k, "Lower bounds")
    upper = _as_1d_bounds(upper, k, "Upper bounds")
    validation = validate_component_bounds(lower, upper, k=k, target_sum=target_sum)
    if not validation.valid:
        raise ValueError(validation.message)

    # If the input already satisfies closure and bounds, the projection must be
    # exactly neutral. This is especially important for full 0–100% bounds,
    # which should behave identically to ordinary closure normalization.
    if (
        abs(float(v.sum()) - target_sum) <= tol
        and np.all(v >= lower - tol)
        and np.all(v <= upper + tol)
    ):
        return np.clip(v.copy(), lower, upper)

    # If all components are fixed, return the unique feasible point.
    if np.allclose(lower, upper, atol=tol, rtol=0.0):
        out = lower.copy()
        if abs(out.sum() - target_sum) > 1e-9:
            raise ValueError("Fixed bounds do not satisfy the requested closure total.")
        return out

    # The projected solution has form clip(v - theta, lower, upper). Find theta.
    lo = float(np.min(v - upper))
    hi = float(np.max(v - lower))
    for _ in range(100):
        theta = 0.5 * (lo + hi)
        x = np.clip(v - theta, lower, upper)
        s = float(x.sum())
        if abs(s - target_sum) <= tol:
            return x
        if s > target_sum:
            lo = theta
        else:
            hi = theta

    x = np.clip(v - 0.5 * (lo + hi), lower, upper)
    # Remove tiny numerical closure errors by distributing within free capacity.
    diff = target_sum - float(x.sum())
    if abs(diff) > tol:
        if diff > 0:
            cap = upper - x
        else:
            cap = x - lower
        total_cap = float(cap.sum())
        if total_cap > 0:
            x += diff * cap / total_cap
    return np.clip(x, lower, upper)


def project_rows_to_bounded_simplex(C, lower, upper, target_sum: float = 1.0) -> np.ndarray:
    """Project every row of C onto bounded closure constraints."""
    C = np.asarray(C, dtype=float)
    if C.ndim != 2:
        raise ValueError("C must be a two-dimensional matrix.")
    out = np.zeros_like(C, dtype=float)
    for i in range(C.shape[0]):
        out[i, :] = project_vector_to_bounded_simplex(C[i, :], lower, upper, target_sum=target_sum)
    return out


def summarize_bound_activity(
    C,
    lower,
    upper,
    *,
    component_names: list[str] | None = None,
    hit_tol: float = 1e-8,
    severe_fraction: float = 0.5,
) -> BoundActivity:
    """Summarize how often component bounds are active in C."""
    C = np.asarray(C, dtype=float)
    if C.ndim != 2:
        raise ValueError("C must be a two-dimensional matrix.")
    n_samples, k = C.shape
    lower = _as_1d_bounds(lower, k, "Lower bounds")
    upper = _as_1d_bounds(upper, k, "Upper bounds")
    if component_names is None:
        component_names = [f"C{i + 1}" for i in range(k)]

    lower_hits = np.count_nonzero(C <= lower.reshape(1, -1) + hit_tol, axis=0)
    upper_hits = np.count_nonzero(C >= upper.reshape(1, -1) - hit_tol, axis=0)

    lines = []
    severe = False
    for idx, name in enumerate(component_names):
        # Ignore trivial 0% and 100% defaults in the user-facing summary.
        if lower[idx] > hit_tol and lower_hits[idx] > 0:
            frac = lower_hits[idx] / max(n_samples, 1)
            lines.append(f"{name} min {100 * lower[idx]:.1f}% active in {lower_hits[idx]} / {n_samples} spectra")
            severe = severe or frac >= severe_fraction
        if upper[idx] < 1.0 - hit_tol and upper_hits[idx] > 0:
            frac = upper_hits[idx] / max(n_samples, 1)
            lines.append(f"{name} max {100 * upper[idx]:.1f}% active in {upper_hits[idx]} / {n_samples} spectra")
            severe = severe or frac >= severe_fraction

    message = "; ".join(lines) if lines else "Component bounds were not active."
    return BoundActivity(
        lower_hits=lower_hits,
        upper_hits=upper_hits,
        n_samples=n_samples,
        severe=severe,
        message=message,
    )


def make_random_s_init(k: int, n_features: int, random_seed: int | None = 0) -> np.ndarray:
    """Create the reproducible random S initialization used by MCR-ALS."""
    rng = np.random.default_rng(random_seed)
    return np.maximum(rng.random((int(k), int(n_features))), 1e-12)


def perturb_initial_s(S_init, perturb_fraction: float = 0.05, random_seed: int | None = 0) -> np.ndarray:
    """Return a non-negative local perturbation of an initial S matrix.

    perturb_fraction is a relative scale: 0.05 means roughly 5% random
    multiplicative perturbation of the selected initial spectra.
    """
    S_init = np.asarray(S_init, dtype=float)
    if S_init.ndim != 2:
        raise ValueError("S_init must be a two-dimensional matrix.")
    p = max(float(perturb_fraction), 0.0)
    if p <= 0.0:
        return np.maximum(S_init.copy(), 1e-12)
    rng = np.random.default_rng(random_seed)
    multiplicative = 1.0 + p * rng.normal(size=S_init.shape)
    # Small additive term lets zero/near-zero points move slightly while keeping
    # the perturbation dominated by the selected initial guess.
    positive = S_init[S_init > 0]
    amp = float(np.median(positive)) if positive.size else 1.0
    additive = 0.05 * p * amp * rng.normal(size=S_init.shape)
    return np.maximum(S_init * multiplicative + additive, 1e-12)


def _component_similarity_matrix(S_ref, S_run) -> np.ndarray:
    """Cosine-similarity matrix between reference and run component spectra."""
    S_ref = np.asarray(S_ref, dtype=float)
    S_run = np.asarray(S_run, dtype=float)
    if S_ref.ndim != 2 or S_run.ndim != 2 or S_ref.shape != S_run.shape:
        raise ValueError("S_ref and S_run must have the same 2D shape.")
    k = S_ref.shape[0]
    sim = np.zeros((k, k), dtype=float)
    for i in range(k):
        a = S_ref[i]
        na = float(np.linalg.norm(a))
        for j in range(k):
            b = S_run[j]
            nb = float(np.linalg.norm(b))
            if na <= 0.0 or nb <= 0.0:
                sim[i, j] = 0.0
            else:
                sim[i, j] = float(np.dot(a, b) / (na * nb))
    return sim


def match_components_by_spectra(S_ref, S_run) -> tuple[list[int], np.ndarray]:
    """Match run components to reference components by spectral similarity.

    Returns a permutation where column i of the returned solution should use
    component permutation[i] from the run to match reference component i.
    """
    sim = _component_similarity_matrix(S_ref, S_run)
    k = sim.shape[0]
    if k <= 8:
        best_perm = None
        best_score = -np.inf
        for perm in permutations(range(k)):
            score = float(sum(sim[i, perm[i]] for i in range(k)))
            if score > best_score:
                best_score = score
                best_perm = perm
        perm = list(best_perm)
    else:
        # Conservative greedy fallback for unusually large k.
        perm = [-1] * k
        unused = set(range(k))
        for i in range(k):
            j = max(unused, key=lambda col: sim[i, col])
            perm[i] = j
            unused.remove(j)
    scores = np.array([sim[i, perm[i]] for i in range(k)], dtype=float)
    return perm, scores


def align_mcr_solution_to_reference(C_run, S_run, S_ref):
    """Reorder a run's C and S so components match reference S rows."""
    C_run = np.asarray(C_run, dtype=float)
    S_run = np.asarray(S_run, dtype=float)
    perm, scores = match_components_by_spectra(S_ref, S_run)
    return C_run[:, perm], S_run[perm, :], perm, scores


def summarize_concentration_stability(C_stack, *, component_names: list[str] | None = None) -> StabilitySummary:
    """Summarize run-to-run concentration scatter from an aligned C stack."""
    C_stack = np.asarray(C_stack, dtype=float)
    if C_stack.ndim != 3:
        raise ValueError("C_stack must have shape (n_runs, n_samples, k).")
    n_runs, _n_samples, k = C_stack.shape
    if n_runs < 1:
        raise ValueError("At least one stability run is required.")
    if component_names is None:
        component_names = [f"C{i + 1}" for i in range(k)]
    ddof = 1 if n_runs > 1 else 0
    C_mean = np.mean(C_stack, axis=0)
    C_std = np.std(C_stack, axis=0, ddof=ddof)
    median_std = float(np.nanmedian(C_std))
    max_std = float(np.nanmax(C_std))
    comp_max = np.nanmax(C_std, axis=0)
    comp_text = ", ".join(
        f"{component_names[i]} max σ={100.0 * comp_max[i]:.2f}%" for i in range(k)
    )
    message = f"Local stability: median σ(C)={100.0 * median_std:.2f}%, max σ(C)={100.0 * max_std:.2f}%"
    if comp_text:
        message += f" ({comp_text})"
    return StabilitySummary(
        C_mean=C_mean,
        C_std=C_std,
        n_runs=int(n_runs),
        median_std=median_std,
        max_std=max_std,
        mean_match_score=float("nan"),
        message=message,
    )


def estimate_local_concentration_stability(
    X,
    *,
    k: int,
    S_init,
    S_ref,
    n_runs: int = 20,
    perturb_fraction: float = 0.05,
    first_seed: int = 1000,
    max_iter: int = 500,
    tol: float = 1e-7,
    closure: bool = True,
    smooth: bool = False,
    smooth_lambda: float = 0.0,
    component_bounds=None,
    progress_callback=None,
) -> StabilitySummary:
    """Estimate local MCR concentration stability around a selected initialization."""
    X = np.asarray(X, dtype=float)
    S_init = np.asarray(S_init, dtype=float)
    S_ref = np.asarray(S_ref, dtype=float)
    n_runs = int(n_runs)
    if n_runs < 1:
        raise ValueError("n_runs must be at least 1.")
    C_runs = []
    match_scores = []
    for i in range(n_runs):
        S0 = perturb_initial_s(S_init, perturb_fraction=perturb_fraction, random_seed=int(first_seed) + i)
        C_i, S_i, _err_i, _n_iter_i, _conv_i = mcr_als(
            X,
            k=k,
            S_init=S0,
            max_iter=max_iter,
            tol=tol,
            closure=closure,
            smooth=smooth,
            smooth_lambda=smooth_lambda,
            component_bounds=component_bounds,
        )
        C_aligned, _S_aligned, _perm, scores = align_mcr_solution_to_reference(C_i, S_i, S_ref)
        C_runs.append(C_aligned)
        match_scores.append(scores)
        if progress_callback is not None:
            progress_callback(i + 1, n_runs)
    C_stack = np.stack(C_runs, axis=0)
    summary = summarize_concentration_stability(C_stack)
    mean_match = float(np.nanmean(np.asarray(match_scores, dtype=float))) if match_scores else float("nan")
    return StabilitySummary(
        C_mean=summary.C_mean,
        C_std=summary.C_std,
        n_runs=summary.n_runs,
        median_std=summary.median_std,
        max_std=summary.max_std,
        mean_match_score=mean_match,
        message=summary.message + (f"; mean match={mean_match:.3f}" if np.isfinite(mean_match) else ""),
    )


def mcr_als(
    X,
    k,
    S_init=None,
    max_iter=500,
    tol=1e-7,
    closure=True,
    smooth=False,
    smooth_lambda=0.0,
    component_bounds=None,
    random_seed=0,
    return_diagnostics=False,
):
    """Basic MCR-ALS with non-negativity and optional closure/smoothing.

    Parameters
    ----------
    X : array, shape (n_samples, n_energies)
        Non-negative data matrix.
    k : int
        Number of components.
    component_bounds : None or tuple(lower, upper)
        Optional fractional bounds for rows of C. Bounds are applied only when
        closure is True. For example, 22% is passed as 0.22.
    random_seed : int or None
        Seed used only when S_init is None. The default 0 preserves
        reproducible legacy random starts.
    return_diagnostics : bool
        If True, return a sixth item containing diagnostic metadata.

    Returns
    -------
    C, S, err, n_iter, converged
        Default legacy return format.
    C, S, err, n_iter, converged, diagnostics
        Returned when return_diagnostics is True.
    """
    X = np.asarray(X, dtype=float)
    n, m = X.shape
    k = int(k)
    if S_init is None:
        S = make_random_s_init(k, m, random_seed=random_seed)
    else:
        S = np.maximum(np.asarray(S_init, dtype=float).copy(), 1e-12)
    C = np.zeros((n, k))

    lower = upper = None
    bounds_active = bool(component_bounds is not None and closure)
    if bounds_active:
        lower, upper = component_bounds
        lower = _as_1d_bounds(lower, k, "Lower bounds")
        upper = _as_1d_bounds(upper, k, "Upper bounds")
        validation = validate_component_bounds(lower, upper, k=k, target_sum=1.0)
        if not validation.valid:
            raise ValueError(validation.message)
        # Full 0–100% bounds are not an additional constraint. Treat them as
        # inactive so checking the GUI box with defaults cannot change the fit.
        if component_bounds_are_trivial(lower, upper, target_sum=1.0):
            bounds_active = False

    prev = np.inf
    converged = False
    err = np.inf
    for it in range(max_iter):
        # Update C by row-wise NNLS on S^T.
        for i in range(n):
            C[i, :] = nnls_solve(S.T, X[i, :])
        C = np.maximum(C, 0.0)
        if closure:
            # Preserve the original closure behavior first. Component bounds are
            # then applied only as an additional restriction to already normalized
            # fractions. Therefore full 0–100% bounds are neutral.
            rs = C.sum(axis=1, keepdims=True)
            rs[rs == 0] = 1.0
            C = C / rs
            if bounds_active:
                C = project_rows_to_bounded_simplex(C, lower, upper, target_sum=1.0)

        # Update S by column-wise NNLS on C.
        S_new = np.zeros_like(S)
        for j in range(m):
            S_new[:, j] = nnls_solve(C, X[:, j])
        S = np.maximum(S_new, 0.0)

        if smooth and smooth_lambda > 0.0:
            S = tikhonov_smooth_matrix(S, lam=smooth_lambda)

        Xhat = C @ S
        err = float(np.sqrt(np.mean((X - Xhat) ** 2)))
        if abs(prev - err) < tol:
            converged = True
            break
        prev = err

    diagnostics = {
        "bounds_active": bounds_active,
        "bound_activity": summarize_bound_activity(C, lower, upper) if bounds_active else None,
    }
    if return_diagnostics:
        return C, S, err, it + 1, converged, diagnostics
    return C, S, err, it + 1, converged


def rmse_per_sample(X, Xhat):
    """Return RMSE for each sample/spectrum."""
    X = np.asarray(X, dtype=float)
    Xhat = np.asarray(Xhat, dtype=float)
    return np.sqrt(((Xhat - X) ** 2).mean(axis=1))


def mean_residual_vs_energy(X, Xhat):
    """Return mean residual as a function of energy."""
    X = np.asarray(X, dtype=float)
    Xhat = np.asarray(Xhat, dtype=float)
    return (X - Xhat).mean(axis=0)
