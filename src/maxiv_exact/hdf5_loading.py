"""Small HDF5 file-loading and tree-payload helpers.

These helpers intentionally avoid Qt and h5py imports so they can be tested
without starting the GUI.  GUI modules should use them to keep Open-HDF5,
drag-and-drop, refresh, and tree-item payload handling consistent.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional, Sequence, Tuple

HDF5_EXTENSIONS = (".h5", ".hdf5")
TreePayload = Tuple[str, str]


def _as_text(value) -> str:
    """Convert simple payload fragments to text, preserving invalid bytes."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def normalize_abs_path(path) -> str:
    """Return an absolute local filesystem path string when possible."""
    try:
        return os.path.abspath(_as_text(path))
    except Exception:
        return _as_text(path)


def display_file_name(path) -> str:
    """Return the user-facing file name for a path-like object."""
    text = _as_text(path)
    try:
        return os.path.basename(text) or text
    except Exception:
        return text


def is_supported_hdf5_extension(path) -> bool:
    """Return True if the path has a supported HDF5 extension."""
    try:
        return os.path.splitext(_as_text(path))[1].lower() in HDF5_EXTENSIONS
    except Exception:
        return False


def is_supported_hdf5_file(path) -> bool:
    """Return True for existing local files with supported HDF5 extensions."""
    try:
        p = normalize_abs_path(path)
        return os.path.isfile(p) and is_supported_hdf5_extension(p)
    except Exception:
        return False


def _normalised_known_paths(known_file_paths: Optional[Iterable[str]] = None) -> set[str]:
    if not known_file_paths:
        return set()
    out: set[str] = set()
    try:
        # Accept both dicts and plain iterables.
        iterable = known_file_paths.keys() if isinstance(known_file_paths, dict) else known_file_paths
        for p in iterable:
            try:
                out.add(normalize_abs_path(p))
                out.add(_as_text(p))
            except Exception:
                continue
    except Exception:
        return set()
    return out


def _looks_like_file_path(value, *, known_file_paths: Optional[Iterable[str]] = None, abs_path=None) -> bool:
    """Heuristic for the first element of legacy ``(file, hdf5_path)`` tuples."""
    text = _as_text(value)
    if not text:
        return False
    known = _normalised_known_paths(known_file_paths)
    if abs_path is not None:
        known.add(normalize_abs_path(abs_path))
        known.add(_as_text(abs_path))
    try:
        if text in known or normalize_abs_path(text) in known:
            return True
    except Exception:
        if text in known:
            return True
    lower = text.lower()
    return (
        lower.endswith(HDF5_EXTENSIONS)
        or os.path.sep in text
        or (os.path.altsep is not None and os.path.altsep in text)
    )


def normalize_hdf5_path(
    value,
    *,
    known_file_paths: Optional[Iterable[str]] = None,
    abs_path=None,
    strip_outer_slashes: bool = False,
) -> str:
    """Return a safe HDF5-relative path string from legacy/tree payloads.

    Tree items normally store ``(abs_path, hdf5_path)``.  A few older or
    refresh-related code paths may accidentally pass that whole tuple where only
    the HDF5 path is expected.  In the standard two-item case this function keeps
    the second element.
    """
    try:
        current = value
        for _ in range(4):
            if current is None:
                current = ""
                break
            if isinstance(current, bytes):
                current = current.decode("utf-8", errors="replace")
                break
            if isinstance(current, str):
                break
            if isinstance(current, (tuple, list)):
                if not current:
                    current = ""
                    break
                if len(current) >= 2:
                    first, second = current[0], current[1]
                    if _looks_like_file_path(first, known_file_paths=known_file_paths, abs_path=abs_path):
                        current = second
                        continue
                    # Conservative fallback for odd tuple shapes: prefer the
                    # last non-empty value, matching the previous GUI behavior.
                    non_empty = [part for part in current if part not in (None, b"", "")]
                    current = non_empty[-1] if non_empty else ""
                    continue
                current = current[0]
                continue
            current = str(current)
            break
        text = _as_text(current)
        if strip_outer_slashes:
            text = text.strip()
            if text in (".", "/"):
                return ""
            return text.strip("/")
        return text
    except Exception:
        try:
            text = _as_text(value)
            return text.strip().strip("/") if strip_outer_slashes else text
        except Exception:
            return ""


def make_tree_payload(abs_path, hdf5_path="") -> TreePayload:
    """Create the canonical left-tree payload ``(abs_path, hdf5_path)``."""
    abs_norm = normalize_abs_path(abs_path)
    h5_norm = normalize_hdf5_path(hdf5_path, known_file_paths=(abs_norm,), abs_path=abs_norm)
    return abs_norm, h5_norm


def split_tree_payload(payload, *, known_file_paths: Optional[Iterable[str]] = None) -> Optional[TreePayload]:
    """Extract ``(abs_path, hdf5_path)`` from a tree item payload.

    Returns ``None`` if the payload does not look like a canonical tree payload.
    """
    if not isinstance(payload, (tuple, list)) or len(payload) < 2:
        return None
    abs_path = normalize_abs_path(payload[0])
    hdf5_path = normalize_hdf5_path(payload[1], known_file_paths=known_file_paths, abs_path=abs_path)
    return abs_path, hdf5_path


def storage_key(abs_path, hdf5_path) -> str:
    """Return the internal raw-curve storage key used by the GUI."""
    return f"{normalize_abs_path(abs_path)}##{normalize_hdf5_path(hdf5_path, abs_path=abs_path)}"


def remap_storage_key(key, old_abs_path, new_abs_path):
    """Replace the file-path prefix in ``abs_path##hdf5_path`` keys."""
    try:
        old_abs = normalize_abs_path(old_abs_path)
        new_abs = normalize_abs_path(new_abs_path)
        if isinstance(key, str) and key.startswith(old_abs + "##"):
            return new_abs + key[len(old_abs):]
    except Exception:
        pass
    return key


def find_loaded_by_basename(abs_path_or_name, loaded_paths: Iterable[str]) -> Optional[str]:
    """Find an already loaded HDF5 file by file name only, not full path."""
    base = display_file_name(abs_path_or_name)
    if not base:
        return None
    try:
        for loaded in list(loaded_paths or []):
            if display_file_name(loaded) == base:
                return normalize_abs_path(loaded)
    except Exception:
        return None
    return None


def split_supported_hdf5_paths(
    paths: Sequence[str],
    *,
    dedupe_by_basename: bool = True,
    require_exists: bool = True,
) -> tuple[list[str], list[str]]:
    """Split user-selected/dropped paths into valid HDF5 files and skipped names."""
    valid: list[str] = []
    skipped: list[str] = []
    seen_names: set[str] = set()

    for raw_path in paths or []:
        try:
            abs_path = normalize_abs_path(raw_path)
            base = display_file_name(abs_path)
        except Exception:
            skipped.append(_as_text(raw_path))
            continue

        ok_extension = is_supported_hdf5_extension(abs_path)
        ok_file = os.path.isfile(abs_path) if require_exists else True
        if not (ok_extension and ok_file):
            skipped.append(base)
            continue

        if dedupe_by_basename and base in seen_names:
            skipped.append(f"{base} (duplicate in selected files)")
            continue
        seen_names.add(base)
        valid.append(abs_path)

    return valid, skipped
