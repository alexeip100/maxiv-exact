"""Descriptions and text formatting for HDF5 structure metadata."""
from contextlib import closing
from math import isfinite, prod

import h5py
import numpy as np

from .hdf5_curve_type import is_plottable_dtype


def describe_tree_object(obj):
    group = isinstance(obj, h5py.Group)
    dataset = isinstance(obj, h5py.Dataset)
    return {
        # The file-loading subprocess can be newer than an already-open viewer.
        "kind": "group" if group else "dataset" if dataset else "other",
        "has_children": group and bool(len(obj)),
        "has_attributes": obj is not None and bool(len(obj.attrs)),
        "is_1d_dataset": dataset and obj.ndim == 1 and is_plottable_dtype(obj.dtype),
        "is_text_dataset": dataset and h5py.check_string_dtype(obj.dtype) is not None,
    }


def format_hdf5_value(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, h5py.Empty):
        return f"Empty ({value.dtype})"
    if isinstance(value, np.ndarray):
        return np.array2string(value, threshold=value.size, precision=None,
                               formatter={"all": format_hdf5_value})
    return str(value)


def compact_text(value, limit=160):
    line = " ".join(value[:limit + 1].split())
    return line[:limit-1] + "…" if len(value) > limit else line


def attribute_preview(attributes, name):
    # HDF5 reads attributes as whole values. Check metadata before fetching.
    with closing(attributes.get_id(name)) as attribute:
        shape = attribute.shape
        if ((shape and prod(shape) > 128) or attribute.get_storage_size() > 64 * 1024):
            label = f"{attribute.dtype} array {shape}" if shape else str(attribute.dtype)
            return f"{label} (double-click to read)"
    return format_hdf5_value(attributes[name])


_IDENTIFICATION_FIELDS = {
    "electronic_environment": "Electronic environment",
    "sample": "Sample",
    "detector": "Detection mode",
    "curation_note": "Curation note",
    "energy_resolution": "Energy resolution",
    "photon_energy_calibration": "Photon energy calibration",
    "absolute_energy_uncertainty": "Absolute energy uncertainty",
    "measured_L3_maximum_eV": "L₃ absorption maximum (eV)",
    "measured_L2_maximum_eV": "L₂ absorption maximum (eV)",
}
_SOURCE_FIELDS = {
    "figure": "Figure / panel / trace",
    "beamline": "Beamline",
    "sample_preparation": "Sample preparation",
    "measurement_conditions": "Measurement conditions",
}
_CITATION_FIELDS = ("authors", "year", "title", "journal", "doi", "source_url")


def is_literature_spectrum(obj):
    """Recognize spectrum groups in the master and curated literature schema."""
    parts = obj.name.strip("/").split("/")
    return (
        isinstance(obj, h5py.Group)
        and len(parts) == 5
        and parts[0] == "spectra"
        and parts[-1].isascii()
        and parts[-1].isdecimal()
        and obj.file.attrs.get("database_role") in ("master", "curated")
        and obj.file.attrs.get("master_database_version") == "2.0"
    )


def _nonzero_shift(attrs):
    try:
        shift = float(attrs.get("proposed_energy_shift_eV", 0))
        return shift if isfinite(shift) and shift else None
    except (TypeError, ValueError, OverflowError):
        return None


def literature_attribute_groups(attrs):
    """Return labelled rows as (display label, attribute name, summary name)."""
    names = set(attrs)
    shown = set()

    def rows(fields):
        for key, label in fields.items():
            if key in names:
                shown.add(key)
                yield label, key, None

    identify = list(rows(_IDENTIFICATION_FIELDS))
    if _nonzero_shift(attrs) is not None:
        identify.append(("Curator-proposed energy shift", None, "shift"))

    source = []
    if names.intersection(_CITATION_FIELDS):
        source.append(("Citation", None, "citation"))
        shown.update(_CITATION_FIELDS)
    source.extend(rows(_SOURCE_FIELDS))

    # Raw shift fields also retain the exact values and their provenance.
    details = [(name, name, None) for name in sorted(names - shown)]
    return (
        ("Identify spectrum", identify, True),
        ("Source", source, False),
        ("Digitization and processing", details, False),
    )


def literature_attribute_summary(attrs, summary, *, preview=False):
    def value(key):
        if key not in attrs:
            return ""
        return (attribute_preview(attrs, key) if preview
                else format_hdf5_value(attrs[key])).strip()

    if summary == "citation":
        authors, year, title, journal, doi, url = map(value, _CITATION_FIELDS)
        credited = " ".join(part for part in (authors, f"({year})" if year else "") if part)
        return "\n".join(part for part in (
            title, credited, journal, f"DOI: {doi}" if doi else "",
            f"Source: {url}" if url else "",
        ) if part)

    shift = _nonzero_shift(attrs)
    if shift is None:
        return "No curator-proposed energy shift."
    applied = bool(attrs.get("proposed_energy_shift_applied", False))
    number = f"{shift:+g}" if not shift.is_integer() else f"{shift:+.1f}"
    return f"{number.replace('-', '−')} eV · {'applied' if applied else 'currently off'}"
