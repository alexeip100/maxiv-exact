"""Classification of individually selected one-dimensional HDF5 curves.

Generic datasets are raw-view-only; only established measurement datasets can
enter the XAS processing workflow.  This module has no Qt dependency.
"""
from __future__ import annotations

import h5py
import numpy as np


def is_measurement_path(path: str) -> bool:
    return "measurement" in str(path).strip("/").split("/")


def is_derived_spectrum_path(path: str) -> bool:
    return str(path).lstrip("/").startswith(("__SUM__/", "__DIFF__/"))


def is_processed_xas_path(path: str) -> bool:
    """Allow real measurement curves and existing synthetic XAS curves.

    Synthetic records are created by EXACT (sums and FA transfers), carry
    independently cached energy axes, and are not generic HDF5 metadata.
    """
    return is_measurement_path(path) or is_derived_spectrum_path(path)


def is_plottable_dtype(dtype) -> bool:
    """Only real-valued numeric and boolean arrays can be drawn as 1D curves."""
    return np.dtype(dtype).kind in ("i", "u", "f", "b")


def raw_curve_axis(path: str, length: int, energy_lookup):
    """Use the existing XAS lookup only for measurement channels."""
    if not is_measurement_path(path):
        return np.arange(length, dtype=float)
    return np.asarray(energy_lookup(), dtype=float)


def _attribute_text(value):
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    return value.strip() if isinstance(value, str) else ""


def paired_raw_axis(file, y_path: str, length: int):
    """Return the stored sibling x, axis label, and stored spectrum title."""
    parent, _, name = y_path.strip("/").rpartition("/")
    if name != "y":
        return None
    group = file[parent] if parent else file
    x = group.get("x")
    y = group.get("y")
    if not all(isinstance(ds, h5py.Dataset) and ds.shape == (length,)
               and ds.dtype.kind in "iuf" for ds in (x, y)):
        return None
    values = x[()]
    if not length or not np.isfinite(values).all():
        return None

    units = _attribute_text(x.attrs.get("units", x.attrs.get("unit", group.attrs.get("x_units", ""))))
    # The existing reference-library format stores photon-energy axes in eV.
    library_record = (
        parent.startswith("spectra/") and parent.count("/") == 1
        and _attribute_text(file.attrs.get("library_version")) == "1.0"
        and _attribute_text(file.attrs.get("created_with")) in {"maxiv_exact", "flexpes_nexafs"}
    )
    if units.casefold() == "ev" or (not units and library_record):
        label = "Photon energy (eV)"
    else:
        label = f"X ({units})" if units else "X"
    title = next((text for attrs in (group.attrs, y.attrs)
                  for field in ("label", "title", "name")
                  if (text := _attribute_text(attrs.get(field)))), "")
    return values, label, title or group.name
