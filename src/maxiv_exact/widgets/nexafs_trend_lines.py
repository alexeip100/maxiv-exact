"""Display-only line segments for NEXAFS trends."""

import numpy as np
from scipy.interpolate import PchipInterpolator


def trend_lines(x, y, mask, *, smooth=False):
    """Yield sorted, finite segments. Missing X and duplicate X are breaks.

    A missing X has no position on the plot, so split at that acquisition
    row before sorting. Retain invalid Y rows during sorting to break the
    curve at their known X positions. Markers are drawn separately.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    known_x = np.flatnonzero(np.isfinite(x))
    valid = np.asarray(mask, dtype=bool) & np.isfinite(y)
    positions, counts = np.unique(x[known_x], return_counts=True)
    barriers = np.union1d(positions[counts > 1], x[known_x[~valid[known_x]]])
    for block in np.split(known_x, np.flatnonzero(np.diff(known_x) > 1) + 1):
        kept = block[valid[block] & ~np.isin(x[block], barriers)]
        order = kept[np.argsort(x[kept], kind="stable")]
        # A known invalid point can sit between samples even when it is
        # in a different acquisition block.
        groups = np.searchsorted(barriers, x[order])
        for run in np.split(order, np.flatnonzero(np.diff(groups)) + 1):
            if run.size < 2:
                continue
            xx, yy = x[run], y[run]
            if smooth and run.size >= 3:
                try:
                    with np.errstate(over="raise", invalid="raise", divide="raise"):
                        dense = np.linspace(xx[0], xx[-1], min(512, max(64, 12 * run.size)))
                        dense = np.unique(np.r_[dense, xx])
                        curve = PchipInterpolator(xx, yy, extrapolate=False)(dense)
                    if np.isfinite(curve).all():
                        yield dense, curve
                        continue
                except (ValueError, FloatingPointError):
                    pass
            yield xx, yy
