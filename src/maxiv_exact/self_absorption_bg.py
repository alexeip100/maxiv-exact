"""Reference/background utilities for PFY self-absorption correction."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .composition import parse_formula
from .reference import ReferenceDatabase
from .self_absorption import SelfAbsorptionError


@dataclass(frozen=True)
class PowerLawFit:
    amplitude: float
    exponent: float
    background: np.ndarray
    mask: np.ndarray
    rms_relative: float


@dataclass(frozen=True)
class ReferenceModel:
    energy_eV: np.ndarray
    mu_total: np.ndarray
    mu_bg: np.ndarray
    mu_target_tab: np.ndarray
    mu_f: float
    power_law: PowerLawFit


def fit_power_law_background(energy_eV, mu_total, *, mask=None, fraction: float = 0.12) -> PowerLawFit:
    """Fit mu_bg=A*E^-p to a selected tabulated pre-edge region."""
    e = np.asarray(energy_eV, dtype=float)
    mu = np.asarray(mu_total, dtype=float)
    if e.shape != mu.shape or e.ndim != 1:
        raise SelfAbsorptionError("Reference energy and attenuation arrays must be matching 1-D arrays.")
    valid = np.isfinite(e) & np.isfinite(mu) & (e > 0) & (mu > 0)
    if mask is None:
        idx = np.where(valid)[0]
        if idx.size < 3:
            raise SelfAbsorptionError("Too few valid reference points for a power-law fit.")
        frac = min(max(float(fraction), 0.01), 0.95)
        n = max(3, int(round(frac * idx.size)))
        fit_mask = np.zeros_like(valid)
        fit_mask[idx[:min(n, idx.size)]] = True
    else:
        fit_mask = valid & np.asarray(mask, dtype=bool)
    if np.count_nonzero(fit_mask) < 3:
        raise SelfAbsorptionError("Reference pre-edge region contains fewer than 3 valid points.")
    x = np.log(e[fit_mask])
    y = np.log(mu[fit_mask])
    slope, intercept = np.polyfit(x, y, 1)
    p = -float(slope)
    a = float(np.exp(intercept))
    bg = a * np.power(e, -p)
    rel = (bg[fit_mask] - mu[fit_mask]) / mu[fit_mask]
    rms_rel = float(np.sqrt(np.mean(rel * rel)))
    return PowerLawFit(a, p, bg, fit_mask, rms_rel)


def compound_mu_total(energy_eV, formula: str, database: ReferenceDatabase | None = None):
    """Return Chantler compound mass attenuation at arbitrary photon energies."""
    db = database or ReferenceDatabase()
    scalar = np.ndim(energy_eV) == 0
    e = np.atleast_1d(np.asarray(energy_eV, dtype=float))
    if e.ndim != 1 or e.size < 1 or not np.all(np.isfinite(e)) or np.any(e <= 0):
        raise SelfAbsorptionError("Photon-energy grid must contain positive finite values.")
    composition = parse_formula(formula, db)
    mu = np.zeros_like(e, dtype=float)
    for symbol, weight in composition.mass_fractions.items():
        mu += weight * np.asarray(db.interpolate(symbol, "chantler", "mu_total", e), dtype=float)
    if scalar:
        return float(mu[0])
    return mu


def build_reference_model(
    energy_eV,
    formula: str,
    fluorescence_energy_eV: float,
    database: ReferenceDatabase | None = None,
    *,
    preedge_fraction: float = 0.12,
    preedge_mask=None,
) -> ReferenceModel:
    """Build Chantler compound attenuation and pre-edge extrapolation.

    The target-shell tabulated contribution is only a calibration aid:
    ``mu_target_tab = max(mu_total - mu_bg, 0)``.  It is *not* used as the
    near-edge spectrum to be recovered.
    """
    db = database or ReferenceDatabase()
    e = np.asarray(energy_eV, dtype=float)
    if e.ndim != 1 or e.size < 3 or not np.all(np.isfinite(e)):
        raise SelfAbsorptionError("Energy grid must be a finite 1-D array with at least 3 points.")
    mu_total = np.asarray(compound_mu_total(e, formula, db), dtype=float)
    mu_f = float(compound_mu_total(float(fluorescence_energy_eV), formula, db))
    fit = fit_power_law_background(e, mu_total, mask=preedge_mask, fraction=preedge_fraction)
    mu_target = np.maximum(mu_total - fit.background, 0.0)
    return ReferenceModel(e, mu_total, fit.background, mu_target, mu_f, fit)
