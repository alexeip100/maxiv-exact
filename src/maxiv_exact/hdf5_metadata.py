"""Descriptions and text formatting for HDF5 structure metadata."""
from contextlib import closing
from math import prod

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
