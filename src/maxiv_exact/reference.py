"""Reference X-ray data backend for EXACT.

This module provides a deliberately small, source-explicit API over the frozen
``xray_reference.h5`` resource bundled with EXACT.  Raw upstream tabulations
are never modified in place.  Plot-ready masking and interpolation are derived
views with explicit policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterable, Literal

import h5py
import numpy as np


SourceName = Literal["henke", "chantler"]


class ReferenceDataError(RuntimeError):
    """Base error for reference-data access."""


class UnknownElementError(ReferenceDataError):
    pass


class UnknownSourceError(ReferenceDataError):
    pass


class UnknownQuantityError(ReferenceDataError):
    pass


class EnergyOutOfRangeError(ReferenceDataError):
    pass


@dataclass(frozen=True)
class ElementInfo:
    symbol: str
    atomic_number: int
    molar_mass_g_mol: float
    density_g_cm3: float


@dataclass(frozen=True)
class Curve:
    element: str
    source: SourceName
    quantity: str
    energy_eV: np.ndarray
    values: np.ndarray
    units: str
    raw: bool


_QUANTITY_ALIASES = {
    "energy": "energy_eV",
    "energy_ev": "energy_eV",
    "f1": "f1",
    "f2": "f2",
    "mu_photo": "mu_photo_cm2_g",
    "mu_photo_cm2_g": "mu_photo_cm2_g",
    "mu_incoh": "mu_incoh_cm2_g",
    "mu_incoh_cm2_g": "mu_incoh_cm2_g",
    "mu_total": "mu_total_cm2_g",
    "mu_total_cm2_g": "mu_total_cm2_g",
}


class ReferenceDatabase:
    """Read-only access to EXACT's frozen X-ray reference database.

    Parameters
    ----------
    path:
        Optional HDF5 path.  If omitted, the resource shipped with EXACT is
        used.  Supplying a path is useful for builder/validation tests.
    """

    def __init__(self, path: str | Path | None = None):
        self._explicit_path = Path(path).expanduser().resolve() if path else None

    def _open(self):
        if self._explicit_path is not None:
            return h5py.File(self._explicit_path, "r")
        resource = files("maxiv_exact.resources").joinpath("xray_reference.h5")
        # h5py needs a filesystem path.  Package wheels are normally unpacked,
        # but as_file also keeps this safe for other importers.
        ctx = as_file(resource)
        path = ctx.__enter__()
        h5 = h5py.File(path, "r")

        class _ManagedH5:
            def __enter__(self_inner):
                return h5

            def __exit__(self_inner, exc_type, exc, tb):
                try:
                    h5.close()
                finally:
                    ctx.__exit__(exc_type, exc, tb)

        return _ManagedH5()

    @staticmethod
    def _norm_element(element: str) -> str:
        text = str(element).strip()
        if not text:
            raise UnknownElementError("Element symbol is empty")
        return text[0].upper() + text[1:].lower()

    @staticmethod
    def _norm_source(source: str) -> SourceName:
        value = str(source).strip().lower()
        if value not in {"henke", "chantler"}:
            raise UnknownSourceError(f"Unknown reference source: {source!r}")
        return value  # type: ignore[return-value]

    @staticmethod
    def _norm_quantity(quantity: str) -> str:
        key = str(quantity).strip().lower()
        try:
            return _QUANTITY_ALIASES[key]
        except KeyError as exc:
            raise UnknownQuantityError(f"Unknown reference quantity: {quantity!r}") from exc

    def database_metadata(self) -> dict[str, object]:
        with self._open() as h5:
            return {str(k): self._plain(v) for k, v in h5.attrs.items()}

    def source_metadata(self, source: str) -> dict[str, object]:
        source = self._norm_source(source)
        group_name = "henke_cxro" if source == "henke" else "chantler_xraydb"
        with self._open() as h5:
            g = h5[f"sources/{group_name}"]
            return {str(k): self._plain(v) for k, v in g.attrs.items()}

    def list_elements(self) -> list[str]:
        with self._open() as h5:
            pairs = []
            for symbol, g in h5["elements"].items():
                pairs.append((int(g.attrs.get("atomic_number", 999)), symbol))
            return [symbol for _, symbol in sorted(pairs)]

    def element_info(self, element: str) -> ElementInfo:
        symbol = self._norm_element(element)
        with self._open() as h5:
            path = f"elements/{symbol}"
            if path not in h5:
                raise UnknownElementError(f"Element {symbol!r} is not in the reference database")
            g = h5[path]
            return ElementInfo(
                symbol=symbol,
                atomic_number=int(g.attrs["atomic_number"]),
                molar_mass_g_mol=float(g.attrs["molar_mass_g_mol"]),
                density_g_cm3=float(g.attrs["density_g_cm3"]),
            )

    def sources_for(self, element: str) -> tuple[SourceName, ...]:
        symbol = self._norm_element(element)
        with self._open() as h5:
            path = f"elements/{symbol}"
            if path not in h5:
                raise UnknownElementError(f"Element {symbol!r} is not in the reference database")
            names = tuple(name for name in ("henke", "chantler") if name in h5[path])
            return names  # type: ignore[return-value]

    def quantities(self, element: str, source: str) -> tuple[str, ...]:
        symbol = self._norm_element(element)
        source_n = self._norm_source(source)
        with self._open() as h5:
            g = self._source_group(h5, symbol, source_n)
            return tuple(
                name for name in (
                    "f1", "f2", "mu_photo_cm2_g", "mu_incoh_cm2_g", "mu_total_cm2_g"
                ) if name in g
            )

    def raw_curve(self, element: str, source: str, quantity: str) -> Curve:
        """Return an exact copy of one upstream tabulation.

        For Henke ``f1``, the source sentinel ``-9999`` is preserved here.
        For Chantler, the stored ``f1`` dataset is the anomalous correction
        ``f'`` as supplied by XrayDB/Chantler, not ``Z + f'``.  Energy
        ordering and duplicate points are also preserved exactly.
        """
        symbol = self._norm_element(element)
        source_n = self._norm_source(source)
        q = self._norm_quantity(quantity)
        if q == "energy_eV":
            raise UnknownQuantityError("Use a physical quantity, not energy itself, for raw_curve()")
        with self._open() as h5:
            g = self._source_group(h5, symbol, source_n)
            if q not in g:
                raise UnknownQuantityError(f"{q!r} is not available for {symbol}/{source_n}")
            e = np.asarray(g["energy_eV"], dtype=float).copy()
            y = np.asarray(g[q], dtype=float).copy()
            units = str(g[q].attrs.get("units", ""))
        return Curve(symbol, source_n, q, e, y, units, raw=True)

    def curve(
        self,
        element: str,
        source: str,
        quantity: str,
        *,
        energy_min_eV: float | None = None,
        energy_max_eV: float | None = None,
    ) -> Curve:
        """Return a plotting-ready curve while preserving source point order.

        Transformations are intentionally limited and explicit:
        * Henke's ``f1=-9999`` sentinel is masked as ``NaN``;
        * Chantler/XrayDB ``f1`` is converted from the stored anomalous
          correction ``f'`` to the full real atomic scattering factor
          ``f1 = Z + f'`` so it is directly comparable with Henke ``f1``.

        Duplicate and locally non-monotonic energies remain in the returned
        curve so the source tabulation can still be inspected faithfully.
        """
        raw = self.raw_curve(element, source, quantity)
        e = raw.energy_eV.copy()
        y = raw.values.copy()
        if raw.source == "henke" and raw.quantity == "f1":
            y[y == -9999.0] = np.nan
        elif raw.source == "chantler" and raw.quantity == "f1":
            # XrayDB stores Chantler's anomalous correction f' in the f1
            # column.  EXACT's user-facing f1 convention is the full real
            # atomic scattering factor, directly comparable with Henke:
            #     f1 = Z + f'
            y = y + float(self.element_info(raw.element).atomic_number)

        keep = np.ones(e.shape, dtype=bool)
        if energy_min_eV is not None:
            keep &= e >= float(energy_min_eV)
        if energy_max_eV is not None:
            keep &= e <= float(energy_max_eV)
        return Curve(raw.element, raw.source, raw.quantity, e[keep], y[keep], raw.units, raw=False)

    def interpolation_curve(self, element: str, source: str, quantity: str) -> Curve:
        """Return a strictly increasing curve suitable for interpolation.

        Policy for source quirks is explicit:
        * Henke ``f1=-9999`` rows are removed.
        * energies are stable-sorted ascending;
        * duplicate energies are made right-continuous by keeping the last
          source occurrence after stable sorting.

        The frozen raw table is never changed.
        """
        curve = self.curve(element, source, quantity)
        e = curve.energy_eV
        y = curve.values
        finite = np.isfinite(e) & np.isfinite(y)
        e = e[finite]
        y = y[finite]
        if e.size < 2:
            raise ReferenceDataError(
                f"Not enough finite points for interpolation: {curve.element}/{curve.source}/{curve.quantity}"
            )

        order = np.argsort(e, kind="stable")
        e = e[order]
        y = y[order]

        # Keep the last value at each duplicate energy.  With stable sorting,
        # this is a right-continuous convention for source edge pairs.
        keep = np.ones(e.size, dtype=bool)
        keep[:-1] = e[:-1] != e[1:]
        e = e[keep]
        y = y[keep]
        if np.any(np.diff(e) <= 0):
            raise ReferenceDataError("Failed to canonicalize energy grid")
        return Curve(curve.element, curve.source, curve.quantity, e, y, curve.units, raw=False)

    def interpolate(
        self,
        element: str,
        source: str,
        quantity: str,
        energy_eV: float | Iterable[float] | np.ndarray,
        *,
        method: Literal["auto", "linear", "loglog"] = "auto",
    ):
        """Interpolate one quantity without extrapolation.

        ``auto`` uses linear interpolation for ``f1`` and log-log interpolation
        for positive quantities (``f2`` and mass attenuation coefficients).
        This is an EXACT policy and is intentionally explicit; it is not stored
        as part of the frozen source data.
        """
        c = self.interpolation_curve(element, source, quantity)
        xq = np.asarray(energy_eV, dtype=float)
        scalar = xq.ndim == 0
        xq = np.atleast_1d(xq)
        if np.any(~np.isfinite(xq)):
            raise ValueError("Requested energies must be finite")
        lo, hi = float(c.energy_eV[0]), float(c.energy_eV[-1])
        if np.any((xq < lo) | (xq > hi)):
            raise EnergyOutOfRangeError(
                f"Requested energy is outside {c.element}/{c.source}/{c.quantity} range "
                f"[{lo:g}, {hi:g}] eV"
            )

        chosen = method
        if method == "auto":
            chosen = "linear" if c.quantity == "f1" else "loglog"

        if chosen == "linear":
            out = np.interp(xq, c.energy_eV, c.values)
        elif chosen == "loglog":
            if np.any(c.energy_eV <= 0) or np.any(c.values < 0):
                raise ReferenceDataError(
                    f"Log-log interpolation requires positive energies and non-negative data "
                    f"for {c.element}/{c.source}/{c.quantity}"
                )

            # Chantler attenuation/f2 tables can contain exact zeros below an
            # absorption threshold (Li is an important soft-X-ray example).
            # Preserve those source zeros.  Use log-log interpolation only
            # when both bracketing values are strictly positive; otherwise
            # interpolate linearly across that single interval.  This avoids
            # taking log(0) while retaining the normal XrayDB-like log-log
            # behavior everywhere the source quantity is positive.
            e = c.energy_eV
            y = c.values
            idx = np.searchsorted(e, xq, side="right") - 1
            idx = np.clip(idx, 0, len(e) - 2)
            e0, e1 = e[idx], e[idx + 1]
            y0, y1 = y[idx], y[idx + 1]
            frac = (xq - e0) / (e1 - e0)
            out = np.empty_like(xq, dtype=float)
            positive = (y0 > 0) & (y1 > 0)
            if np.any(positive):
                out[positive] = np.exp(
                    np.log(y0[positive])
                    + frac[positive] * (np.log(y1[positive]) - np.log(y0[positive]))
                )
            if np.any(~positive):
                out[~positive] = y0[~positive] + frac[~positive] * (y1[~positive] - y0[~positive])
        else:
            raise ValueError(f"Unknown interpolation method: {method!r}")
        return float(out[0]) if scalar else out

    def diagnostics(self, element: str, source: str) -> dict[str, np.ndarray]:
        symbol = self._norm_element(element)
        source_n = self._norm_source(source)
        with self._open() as h5:
            g = self._source_group(h5, symbol, source_n)
            result = {}
            for name in (
                "source_duplicate_energy_indices",
                "source_decreasing_energy_indices",
                "source_nonincreasing_energy_indices",
            ):
                if name in g:
                    result[name] = np.asarray(g[name], dtype=np.int64).copy()
            return result

    @staticmethod
    def _source_group(h5: h5py.File, symbol: str, source: SourceName) -> h5py.Group:
        element_path = f"elements/{symbol}"
        if element_path not in h5:
            raise UnknownElementError(f"Element {symbol!r} is not in the reference database")
        source_path = f"{element_path}/{source}"
        if source_path not in h5:
            raise UnknownSourceError(f"Source {source!r} is not available for element {symbol}")
        return h5[source_path]

    @staticmethod
    def _plain(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value


_default_database: ReferenceDatabase | None = None


def reference_database() -> ReferenceDatabase:
    """Return a lazily created process-wide reference database accessor."""
    global _default_database
    if _default_database is None:
        _default_database = ReferenceDatabase()
    return _default_database
