"""PFY self-absorption helpers for the EXACT 2.5.3 development series.

The functions in this module are deliberately GUI-free.  The current model
supports a thick, homogeneous sample with either a single physical
fluorescence energy or a fixed Gaussian fluorescence-energy distribution.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np
from scipy.optimize import brentq


class SelfAbsorptionError(ValueError):
    """Raised when self-absorption correction inputs are invalid."""


@dataclass(frozen=True)
class GeometryResult:
    alpha_deg: float
    gamma_deg: float
    beta_deg: float
    factor: float


@dataclass(frozen=True)
class CalibrationResult:
    scale_c: float
    y: np.ndarray
    y_max: float
    condition_amplification_max: float


@dataclass(frozen=True)
class GaussianEmissionProfile:
    center_eV: float
    fwhm_eV: float
    energy_eV: np.ndarray
    weights: np.ndarray


def flexpes_geometry(alpha_deg: float, gamma_deg: float = 30.0) -> GeometryResult:
    """Return beta and G=sin(alpha)/sin(beta) for the present FlexPES geometry."""
    alpha = math.radians(float(alpha_deg))
    gamma = math.radians(float(gamma_deg))
    if not (0.0 < alpha < math.pi / 2.0):
        raise SelfAbsorptionError("Incidence angle alpha must be between 0 and 90 degrees (exclusive).")
    if not (0.0 <= abs(gamma) < math.pi / 2.0):
        raise SelfAbsorptionError("Detector-plane tilt gamma must satisfy |gamma| < 90 degrees.")
    sin_beta = math.cos(alpha) * math.cos(gamma)
    if sin_beta <= 0.0 or sin_beta >= 1.0:
        raise SelfAbsorptionError("Geometry gives an invalid fluorescence exit angle beta.")
    beta = math.asin(sin_beta)
    factor = math.sin(alpha) / sin_beta
    return GeometryResult(float(alpha_deg), float(gamma_deg), math.degrees(beta), factor)


def gaussian_emission_profile(center_eV: float, fwhm_eV: float, *, points: int = 161, sigma_span: float = 4.0) -> GaussianEmissionProfile:
    """Return a normalized Gaussian physical fluorescence-energy distribution.

    ``fwhm_eV`` describes the physical emission distribution *before* detector
    broadening.  It must not be set to the SDD pulse-height resolution.
    """
    center = float(center_eV)
    fwhm = float(fwhm_eV)
    if not np.isfinite(center) or center <= 0:
        raise SelfAbsorptionError("Gaussian fluorescence center must be positive and finite.")
    if not np.isfinite(fwhm) or fwhm <= 0:
        raise SelfAbsorptionError("Gaussian fluorescence FWHM must be positive and finite.")
    n = max(21, int(points))
    if n % 2 == 0:
        n += 1
    sigma = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    span = max(2.0, float(sigma_span)) * sigma
    e = np.linspace(center - span, center + span, n)
    if np.any(e <= 0):
        raise SelfAbsorptionError("Gaussian fluorescence distribution extends to non-positive photon energy.")
    z = (e - center) / sigma
    w = np.exp(-0.5 * z * z)
    w /= np.sum(w)
    return GaussianEmissionProfile(center, fwhm, e, w)


def denominator_term(mu_bg, mu_f: float, geometry_factor: float):
    mu_bg = np.asarray(mu_bg, dtype=float)
    mu_f = float(mu_f)
    g = float(geometry_factor)
    if not np.isfinite(mu_f) or mu_f <= 0:
        raise SelfAbsorptionError("mu_f must be a positive finite attenuation coefficient.")
    if not np.isfinite(g) or g <= 0:
        raise SelfAbsorptionError("Geometry factor must be positive and finite.")
    out = mu_bg + g * mu_f
    if not np.all(np.isfinite(out)) or np.any(out <= 0):
        raise SelfAbsorptionError("The attenuation denominator contains non-positive or non-finite values.")
    return out


def forward_fraction_single(mu_x, mu_bg, mu_f: float, geometry_factor: float):
    """Dimensionless thick-sample PFY fraction for one fluorescence energy."""
    mu_x = np.asarray(mu_x, dtype=float)
    d = denominator_term(mu_bg, mu_f, geometry_factor)
    denom = mu_x + d
    if np.any(denom <= 0):
        raise SelfAbsorptionError("Forward-model denominator is non-positive.")
    return mu_x / denom


def forward_thick(mu_x, mu_bg, mu_f: float, geometry_factor: float, scale_c: float = 1.0):
    """Thick-sample, one-channel PFY forward model."""
    c = float(scale_c)
    if not np.isfinite(c) or c <= 0:
        raise SelfAbsorptionError("Scale C must be positive and finite.")
    return c * forward_fraction_single(mu_x, mu_bg, mu_f, geometry_factor)


def _validate_distribution(mu_f_values, weights, geometry_factor: float):
    mu_f = np.asarray(mu_f_values, dtype=float).ravel()
    w = np.asarray(weights, dtype=float).ravel()
    if mu_f.size < 2 or mu_f.shape != w.shape:
        raise SelfAbsorptionError("Fluorescence attenuation values and distribution weights must be matching arrays.")
    if not np.all(np.isfinite(mu_f)) or np.any(mu_f <= 0):
        raise SelfAbsorptionError("Fluorescence attenuation distribution contains invalid values.")
    if not np.all(np.isfinite(w)) or np.any(w < 0) or np.sum(w) <= 0:
        raise SelfAbsorptionError("Fluorescence distribution weights are invalid.")
    g = float(geometry_factor)
    if not np.isfinite(g) or g <= 0:
        raise SelfAbsorptionError("Geometry factor must be positive and finite.")
    w = w / np.sum(w)
    return mu_f, w, g


def forward_fraction_distribution(mu_x, mu_bg, mu_f_values, weights, geometry_factor: float):
    r"""Dimensionless thick-sample PFY fraction for a fixed emission distribution.

    .. math::
       q(E)=\mu_X(E)\int \frac{S(E_f)}{\mu_X(E)+\mu_{bg}(E)+G\mu(E_f)}\,dE_f.
    """
    x = np.asarray(mu_x, dtype=float)
    bg = np.asarray(mu_bg, dtype=float)
    if x.shape != bg.shape:
        raise SelfAbsorptionError("mu_X and mu_bg must have matching shapes.")
    mu_f, w, g = _validate_distribution(mu_f_values, weights, geometry_factor)
    d = bg[..., None] + g * mu_f[None, ...]
    denom = x[..., None] + d
    if np.any(denom <= 0):
        raise SelfAbsorptionError("Distribution forward-model denominator is non-positive.")
    return x * np.sum(w[None, ...] / denom, axis=-1)


def forward_thick_distribution(mu_x, mu_bg, mu_f_values, weights, geometry_factor: float, scale_c: float = 1.0):
    c = float(scale_c)
    if not np.isfinite(c) or c <= 0:
        raise SelfAbsorptionError("Scale C must be positive and finite.")
    return c * forward_fraction_distribution(mu_x, mu_bg, mu_f_values, weights, geometry_factor)


def fit_scale_constant(signal, q, mask=None) -> float:
    """Least-squares fit of signal = C*q over a calibration mask."""
    signal = np.asarray(signal, dtype=float)
    q = np.asarray(q, dtype=float)
    if signal.shape != q.shape:
        raise SelfAbsorptionError("Signal and calibration reference must have the same shape.")
    valid = np.isfinite(signal) & np.isfinite(q) & (q > 0)
    if mask is not None:
        valid &= np.asarray(mask, dtype=bool)
    if np.count_nonzero(valid) < 2:
        raise SelfAbsorptionError("Calibration region contains too few valid points.")
    den = float(np.dot(q[valid], q[valid]))
    if den <= 0 or not np.isfinite(den):
        raise SelfAbsorptionError("Calibration reference has zero/invalid norm.")
    c = float(np.dot(q[valid], signal[valid]) / den)
    if not np.isfinite(c) or c <= 0:
        raise SelfAbsorptionError("Calibration produced a non-positive or non-finite scale C.")
    return c


def calibrate(signal, q, mask=None) -> CalibrationResult:
    c = fit_scale_constant(signal, q, mask=mask)
    signal = np.asarray(signal, dtype=float)
    y = signal / c
    finite = np.isfinite(y)
    y_max = float(np.nanmax(y[finite])) if np.any(finite) else float("nan")
    if np.any(finite & (y >= 1.0)):
        amp = float("inf")
    else:
        amp = float(np.nanmax(1.0 / np.maximum(1.0 - y[finite], 1e-15))) if np.any(finite) else float("nan")
    return CalibrationResult(c, y, y_max, amp)


def invert_thick(signal, scale_c: float, mu_bg, mu_f: float, geometry_factor: float):
    """Analytic inversion of the single-energy thick-sample model."""
    signal = np.asarray(signal, dtype=float)
    c = float(scale_c)
    if not np.isfinite(c) or c <= 0:
        raise SelfAbsorptionError("Scale C must be positive and finite.")
    d = denominator_term(mu_bg, mu_f, geometry_factor)
    y = signal / c
    out = np.full_like(y, np.nan, dtype=float)
    ok = np.isfinite(y) & np.isfinite(d) & (y >= 0.0) & (y < 1.0)
    out[ok] = d[ok] * y[ok] / (1.0 - y[ok])
    return out


def invert_thick_distribution(signal, scale_c: float, mu_bg, mu_f_values, weights, geometry_factor: float):
    """Numerically invert the fixed-distribution thick-sample model point by point."""
    signal = np.asarray(signal, dtype=float)
    bg = np.asarray(mu_bg, dtype=float)
    if signal.shape != bg.shape:
        raise SelfAbsorptionError("Signal and mu_bg must have matching shapes.")
    c = float(scale_c)
    if not np.isfinite(c) or c <= 0:
        raise SelfAbsorptionError("Scale C must be positive and finite.")
    mu_f, w, g = _validate_distribution(mu_f_values, weights, geometry_factor)
    y = signal / c
    out = np.full_like(y, np.nan, dtype=float)
    d_all = bg[..., None] + g * mu_f[None, ...]

    for i in range(y.size):
        yi = float(y.flat[i])
        if not np.isfinite(yi) or yi < 0.0 or yi >= 1.0:
            continue
        if yi == 0.0:
            out.flat[i] = 0.0
            continue
        di = np.asarray(d_all.reshape((-1, mu_f.size))[i], dtype=float)
        dmax = float(np.max(di))
        # x = dmax*y/(1-y) is a guaranteed upper bracket because all d_j <= dmax.
        hi = dmax * yi / max(1.0 - yi, 1e-15)
        hi = max(hi, 1e-12)

        def f(x):
            return x * float(np.sum(w / (x + di))) - yi

        try:
            out.flat[i] = brentq(f, 0.0, hi, xtol=1e-10, rtol=1e-10, maxiter=100)
        except ValueError:
            # Numerical safety fallback: enlarge the upper bracket.
            hi2 = max(hi * 10.0, dmax * 10.0)
            try:
                out.flat[i] = brentq(f, 0.0, hi2, xtol=1e-10, rtol=1e-10, maxiter=150)
            except ValueError:
                pass
    return out


def relative_condition_amplification_distribution(mu_x, mu_bg, mu_f_values, weights, geometry_factor: float):
    """Return the local relative inversion amplification for a distribution model.

    For a single fluorescence energy this reduces exactly to ``1/(1-y)``.
    """
    x = np.asarray(mu_x, dtype=float)
    bg = np.asarray(mu_bg, dtype=float)
    mu_f, w, g = _validate_distribution(mu_f_values, weights, geometry_factor)
    d = bg[..., None] + g * mu_f[None, ...]
    denom = x[..., None] + d
    q = x * np.sum(w[None, ...] / denom, axis=-1)
    deriv = np.sum(w[None, ...] * d / (denom * denom), axis=-1)
    amp = np.full_like(x, np.nan, dtype=float)
    ok = np.isfinite(x) & (x > 0) & np.isfinite(q) & (q >= 0) & np.isfinite(deriv) & (deriv > 0)
    amp[ok] = q[ok] / (x[ok] * deriv[ok])
    amp[(x == 0) & np.isfinite(x)] = 1.0
    return amp


def correction_strength_label(y_max: float) -> str:
    """Coarse diagnostic label, intentionally conservative for development builds."""
    if not np.isfinite(y_max):
        return "invalid"
    if y_max >= 1.0:
        return "unreliable / singular"
    if y_max >= 0.8:
        return "very strong"
    if y_max >= 0.5:
        return "strong"
    if y_max >= 0.25:
        return "moderate"
    return "weak"
