"""Chemical-composition helpers for EXACT reference calculations.

The formula syntax intentionally implements only the stoichiometric subset
needed by EXACT at present: element symbols, positive numerical quantities,
and nested parentheses.  This scope follows the chemical-formula parsing
approach used by XAFSmass / ParSeq-XAS, but does not depend on the XAFSmass
application at runtime.

Examples accepted by this module include ``Co2O3``, ``LiFePO4``,
``Al2(SO4)3`` and fractional stoichiometries such as ``La0.7Sr0.3MnO3``.
Weight-percent mixtures, unknown ``x`` concentrations, charges and hydrate-dot
notation are deliberately outside the current EXACT scope.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .reference import Curve, EnergyOutOfRangeError, ReferenceDataError, ReferenceDatabase


class CompositionError(ValueError):
    """Raised when a chemical formula cannot be parsed or validated."""


@dataclass(frozen=True)
class Composition:
    formula: str
    amounts: Mapping[str, float]
    molar_mass_g_mol: float
    atomic_fractions: Mapping[str, float]
    mass_fractions: Mapping[str, float]

    def summary(self) -> str:
        parts = []
        for symbol, amount in self.amounts.items():
            if float(amount).is_integer():
                amount_text = str(int(amount))
            else:
                amount_text = f"{amount:g}"
            parts.append(f"{symbol}: {amount_text}")
        return ", ".join(parts)

    def mass_fraction_summary(self) -> str:
        return ", ".join(
            f"{symbol}: {100.0 * fraction:.2f}%"
            for symbol, fraction in self.mass_fractions.items()
        )


@dataclass(frozen=True)
class CompoundCurve:
    formula: str
    quantity: str
    energy_eV: np.ndarray
    values: np.ndarray
    units: str = "cm^2/g"


class _FormulaParser:
    def __init__(self, formula: str, valid_elements: set[str]):
        self.original = str(formula)
        self.text = "".join(self.original.split())
        self.valid_elements = valid_elements
        self.pos = 0

    def parse(self) -> OrderedDict[str, float]:
        if not self.text:
            raise CompositionError("Chemical formula is empty")
        result = self._parse_group(stop=None)
        if self.pos != len(self.text):
            raise CompositionError(
                f"Unexpected text at position {self.pos + 1}: {self.text[self.pos:]!r}"
            )
        if not result:
            raise CompositionError("Chemical formula contains no elements")
        return result

    def _parse_group(self, stop: str | None) -> OrderedDict[str, float]:
        result: OrderedDict[str, float] = OrderedDict()
        found_any = False

        while self.pos < len(self.text):
            char = self.text[self.pos]
            if stop is not None and char == stop:
                break
            if char == ")":
                if stop is None:
                    raise CompositionError(f"Unmatched ')' at position {self.pos + 1}")
                break

            if char == "(":
                self.pos += 1
                inner = self._parse_group(stop=")")
                if self.pos >= len(self.text) or self.text[self.pos] != ")":
                    raise CompositionError("Unclosed '(' in chemical formula")
                self.pos += 1
                multiplier = self._parse_number(default=1.0)
                for symbol, amount in inner.items():
                    result[symbol] = result.get(symbol, 0.0) + amount * multiplier
                found_any = True
                continue

            if not char.isupper():
                raise CompositionError(
                    f"Expected an element symbol or '(' at position {self.pos + 1}"
                )

            symbol = char
            self.pos += 1
            if self.pos < len(self.text) and self.text[self.pos].islower():
                symbol += self.text[self.pos]
                self.pos += 1
            if symbol not in self.valid_elements:
                raise CompositionError(f"Unknown or unsupported element symbol: {symbol}")

            amount = self._parse_number(default=1.0)
            result[symbol] = result.get(symbol, 0.0) + amount
            found_any = True

        if stop is not None and not found_any:
            raise CompositionError("Empty parentheses are not allowed")
        return result

    def _parse_number(self, *, default: float) -> float:
        start = self.pos
        seen_digit = False
        seen_dot = False
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch.isdigit():
                seen_digit = True
                self.pos += 1
            elif ch == "." and not seen_dot:
                seen_dot = True
                self.pos += 1
            else:
                break
        if self.pos == start:
            return default
        token = self.text[start:self.pos]
        if not seen_digit:
            raise CompositionError(f"Invalid stoichiometric quantity: {token!r}")
        try:
            value = float(token)
        except ValueError as exc:
            raise CompositionError(f"Invalid stoichiometric quantity: {token!r}") from exc
        if not np.isfinite(value) or value <= 0:
            raise CompositionError("Stoichiometric quantities must be positive finite numbers")
        return value


def parse_formula(formula: str, database: ReferenceDatabase) -> Composition:
    """Parse *formula* and calculate atomic/mass fractions from EXACT data."""
    valid = set(database.list_elements())
    amounts = _FormulaParser(formula, valid).parse()

    masses: OrderedDict[str, float] = OrderedDict()
    for symbol, amount in amounts.items():
        masses[symbol] = amount * database.element_info(symbol).molar_mass_g_mol

    molar_mass = float(sum(masses.values()))
    atom_total = float(sum(amounts.values()))
    if molar_mass <= 0 or atom_total <= 0:
        raise CompositionError("Chemical formula has zero total amount or molar mass")

    atomic_fractions = OrderedDict(
        (symbol, float(amount / atom_total)) for symbol, amount in amounts.items()
    )
    mass_fractions = OrderedDict(
        (symbol, float(mass / molar_mass)) for symbol, mass in masses.items()
    )

    return Composition(
        formula="".join(str(formula).split()),
        amounts=amounts,
        molar_mass_g_mol=molar_mass,
        atomic_fractions=atomic_fractions,
        mass_fractions=mass_fractions,
    )


def _norm_mu_quantity(quantity: str) -> str:
    aliases = {
        "mu_photo": "mu_photo_cm2_g",
        "mu_photo_cm2_g": "mu_photo_cm2_g",
        "mu_incoh": "mu_incoh_cm2_g",
        "mu_incoh_cm2_g": "mu_incoh_cm2_g",
        "mu_total": "mu_total_cm2_g",
        "mu_total_cm2_g": "mu_total_cm2_g",
    }
    key = str(quantity).strip().lower()
    try:
        return aliases[key]
    except KeyError as exc:
        raise ReferenceDataError(
            "Compound calculations currently support only Chantler mass attenuation "
            "quantities: mu_photo, mu_incoh and mu_total"
        ) from exc


def compound_mass_attenuation(
    database: ReferenceDatabase,
    composition: Composition | str,
    quantity: str,
    *,
    energy_min_eV: float | None = None,
    energy_max_eV: float | None = None,
) -> CompoundCurve:
    """Return Chantler compound mass attenuation coefficient using the mixture rule.

    The calculation is ``(mu/rho)_compound = sum_i w_i (mu/rho)_i``, where
    ``w_i`` are elemental mass fractions derived from the chemical formula.
    A common grid is built from the union of the constituent Chantler source
    grids over their shared energy range.  No density is required.
    """
    comp = parse_formula(composition, database) if isinstance(composition, str) else composition
    q = _norm_mu_quantity(quantity)

    elemental_curves = {}
    lo = -np.inf
    hi = np.inf
    for symbol in comp.amounts:
        curve = database.interpolation_curve(symbol, "chantler", q)
        elemental_curves[symbol] = curve
        lo = max(lo, float(curve.energy_eV[0]))
        hi = min(hi, float(curve.energy_eV[-1]))

    if energy_min_eV is not None:
        lo = max(lo, float(energy_min_eV))
    if energy_max_eV is not None:
        hi = min(hi, float(energy_max_eV))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise EnergyOutOfRangeError(
            f"No common Chantler energy range for {comp.formula} within the requested limits"
        )

    pieces = [np.asarray([lo, hi], dtype=float)]
    for curve in elemental_curves.values():
        mask = (curve.energy_eV >= lo) & (curve.energy_eV <= hi)
        pieces.append(curve.energy_eV[mask])
    energy = np.unique(np.concatenate(pieces))
    if energy.size < 2:
        raise ReferenceDataError(f"Not enough common energy points for {comp.formula}")

    total = np.zeros_like(energy, dtype=float)
    for symbol, weight in comp.mass_fractions.items():
        total += float(weight) * np.asarray(
            database.interpolate(symbol, "chantler", q, energy), dtype=float
        )

    return CompoundCurve(comp.formula, q, energy, total)


def compound_mass_attenuation_value(
    database: ReferenceDatabase,
    composition: Composition | str,
    quantity: str,
    energy_eV: float,
) -> float:
    """Evaluate a compound Chantler mass attenuation coefficient at one energy."""
    comp = parse_formula(composition, database) if isinstance(composition, str) else composition
    q = _norm_mu_quantity(quantity)
    value = 0.0
    for symbol, weight in comp.mass_fractions.items():
        value += float(weight) * float(database.interpolate(symbol, "chantler", q, energy_eV))
    return float(value)
