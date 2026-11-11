"""Capture eligible Group BG spectra on their native photon-energy grids."""

from dataclasses import dataclass
from uuid import uuid4

import numpy as np


GROUP_REQUIRED = "Select at least three spectra and enable Group BG."


@dataclass(frozen=True, slots=True)
class GroupBGSettings:
    polynomial_degree: int
    preedge_fraction: float
    match_preedge_slope: bool
    normalization_channel: str | None


@dataclass(frozen=True, slots=True, eq=False)
class ProcessedSpectrum:
    key: str
    label: str
    energy: np.ndarray
    intensity: np.ndarray
    normalization_range: tuple[float, float]


@dataclass(frozen=True, slots=True, eq=False)
class ProcessedGroup:
    revision: str
    settings: GroupBGSettings
    spectra: tuple[ProcessedSpectrum, ...]


def capture_group(keys, processed, problems, settings):
    """Build a snapshot only if all selected spectra completed processing.

    `processed` holds the label, energy and intensity actually passed to the
    plot. The caller records any skipped processing steps in `problems`.
    """
    if len(keys) < 3:
        return None, GROUP_REQUIRED

    entries = []
    spacings = []
    for key in keys:
        if key in problems:
            return None, problems[key]
        if key not in processed:
            return None, f"Group BG did not produce a spectrum for {key}."
        label, energy, intensity = processed[key]
        finite_energy = np.isfinite(energy)
        if not finite_energy.all() or np.any(np.diff(energy) <= 0):
            return None, f"{label}: photon energies must be finite and strictly increasing."
        used_energy = energy[np.isfinite(intensity)]
        if used_energy.size < 3:
            return None, f"{label}: fewer than three finite intensity points."
        normalization_range = (float(used_energy[0]), float(used_energy[-1]))
        spacings.append(float(np.median(np.diff(used_energy))))
        entries.append((key, label, energy, intensity, normalization_range))

    # Allow small endpoint offsets, but reject differing integration windows.
    # The coarsest median step permits slightly offset grids. A span-relative
    # cap also protects short or sparse scans against large window differences.
    starts, ends = zip(*(entry[-1] for entry in entries))
    shortest_span = min(hi - lo for lo, hi in zip(starts, ends))
    tolerance = min(max(spacings), 0.01 * shortest_span)
    if max(starts) - min(starts) > tolerance or max(ends) - min(ends) > tolerance:
        return None, "Group BG area-normalization energy ranges differ across the selected spectra."

    spectra = []
    for key, label, energy, intensity, limits in entries:
        energy = energy.copy()
        intensity = intensity.copy()
        energy.setflags(write=False)
        intensity.setflags(write=False)
        spectra.append(ProcessedSpectrum(key, label, energy, intensity, limits))
    return ProcessedGroup(uuid4().hex, settings, tuple(spectra)), ""


def mean_spectrum(spectra, limits=None):
    """Average (energy, intensity) pairs without extrapolating any spectrum.

    Use the native grid with the most samples within the finite common range.
    Missing intensity points are omitted before interpolation.
    """
    finite_pairs = []
    for energy, intensity in spectra:
        mask = np.isfinite(intensity)
        finite_pairs.append((energy[mask], intensity[mask]))
    if not finite_pairs or any(x.size == 0 for x, _ in finite_pairs):
        raise ValueError("The average needs finite samples from every spectrum.")
    low = max(x[0] for x, _ in finite_pairs)
    high = min(x[-1] for x, _ in finite_pairs)
    if limits is not None:
        low, high = max(low, limits[0]), min(high, limits[1])
    grid = max((x[(x >= low) & (x <= high)] for x, _ in finite_pairs), key=len)
    if grid.size < 3:
        raise ValueError("Fewer than three usable points in the common energy interval.")
    return grid, np.mean([np.interp(grid, x, y) for x, y in finite_pairs], axis=0)
