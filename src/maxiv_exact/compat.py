"""Small numerical helpers shared across processing modules."""

from __future__ import annotations

import numpy as np


def trapezoid(y, x=None, dx: float = 1.0, axis: int = -1):
    """Integrate using NumPy's supported trapezoidal-rule API."""
    return np.trapezoid(y, x=x, dx=dx, axis=axis)
