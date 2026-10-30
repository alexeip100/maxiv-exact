"""Reusable, NumPy-only experimental pre-edge background fitting.

The optional end-slope constraint matches the algorithm in the existing
Processed Data ``_apply_automatic_bg_new`` method: least squares to the
pre-edge with one weighted derivative row at the final scan energy.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class BackgroundSlopeDiagnostic:
    tail_slope: float
    fitted_end_slope: float
    tail_fraction: float
    slope_constrained: bool
    preedge_points: int
    tail_points: int


def fit_experimental_background(x, y, fraction: float, degree: int, *, match_tail_slope: bool = False,
                                tail_fraction: float = 0.05):
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError("Energy and signal arrays must match")
    good = np.isfinite(x) & np.isfinite(y)
    xf = x[good]; yf = y[good]
    if xf.size < 3:
        return np.zeros_like(y), BackgroundSlopeDiagnostic(float('nan'), float('nan'), tail_fraction, match_tail_slope, 0, 0)
    # Reproduce main Processed Data selection (floor rather than round).
    m = min(max(1, int(float(fraction) * xf.size)), xf.size - 1)
    deg = min(max(0, int(degree)), m - 1)
    xmin, xmax = float(xf[0]), float(xf[-1])
    span = xmax - xmin
    if span <= 0:
        raise ValueError("Energy axis must increase")
    xp = 2 * (xf - xmin) / span - 1
    a = np.vander(xp[:m], deg + 1)
    b = yf[:m]
    tail_start = max(m+1, int((1.0-tail_fraction)*xf.size))
    if tail_start >= xf.size-1:
        tail_start = max(xf.size-2, 0)
    xt, yt = xf[tail_start:], yf[tail_start:]
    measured_slope = float(np.polyfit(xt, yt, 1)[0]) if xt.size >= 2 else 0.0
    if match_tail_slope:
        powers = np.arange(deg, -1, -1, dtype=float)
        deriv_row = np.where(powers > 0, powers * (xp[-1] ** np.maximum(powers-1, 0)), 0.)
        # Same median-row-norm weight as Processed Data.
        weight = float(np.median(np.linalg.norm(a, axis=1)))
        if not np.isfinite(weight) or weight <= 0: weight = 1.
        a = np.vstack((a, weight * deriv_row))
        b = np.r_[b, weight * measured_slope * span/2]
    coeff, *_ = np.linalg.lstsq(a, b, rcond=None)
    if not np.all(np.isfinite(coeff)):
        raise ValueError("Experimental BG coefficients are non-finite")
    all_xp = 2*(x-xmin)/span-1
    bg = np.polyval(coeff, all_xp)
    end_slope = float(np.polyval(np.polyder(coeff), 1.0) * 2/span) if deg else 0.
    return bg, BackgroundSlopeDiagnostic(measured_slope, end_slope, tail_fraction,
                                         bool(match_tail_slope), m, int(xt.size))
