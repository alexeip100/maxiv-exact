"""Classification of individually selected one-dimensional HDF5 curves.

Generic datasets are raw-view-only; only established measurement datasets can
enter the XAS processing workflow.  This module has no Qt dependency.
"""
from __future__ import annotations

import numpy as np


def is_measurement_path(path: str) -> bool:
    return "measurement" in str(path).strip("/").split("/")


def is_processed_xas_path(path: str) -> bool:
    """Allow real measurement curves and existing synthetic XAS curves.

    Synthetic records are created by EXACT (sums and FA transfers), carry
    independently cached energy axes, and are not generic HDF5 metadata.
    """
    normalized = str(path).lstrip("/")
    return is_measurement_path(normalized) or normalized.startswith("__SUM__/")


def is_plottable_dtype(dtype) -> bool:
    """Only real-valued numeric and boolean arrays can be drawn as 1D curves."""
    return np.dtype(dtype).kind in ("i", "u", "f", "b")


def raw_curve_axis(path: str, length: int, energy_lookup):
    """Use the existing XAS lookup only for measurement channels."""
    if not is_measurement_path(path):
        return np.arange(length, dtype=float)
    return np.asarray(energy_lookup(), dtype=float)
