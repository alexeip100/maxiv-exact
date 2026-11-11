"""NEXAFS component functions on a photon-energy axis in eV."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, log, pi, sqrt

import numpy as np
from scipy.special import erf


class StepForm(StrEnum):
    ERF = "erf"
    ARCTAN = "arctan"


def _scaled_energy(energy, position, fwhm):
    if not isfinite(position) or not isfinite(fwhm) or fwhm <= 0:
        raise ValueError("Position must be finite and FWHM must be finite and positive.")
    return (np.asarray(energy, dtype=float) - position) / fwhm


def gaussian_basis(energy, center, fwhm):
    """Return a Gaussian with unit integral over the entire energy axis."""
    scaled = _scaled_energy(energy, center, fwhm)
    return (2 * sqrt(log(2) / pi) / fwhm) * np.exp(-4 * log(2) * scaled**2)


def ip_step_basis(energy, position, fwhm, form=StepForm.ERF):
    """Return a unit-height IP step whose derivative has the specified FWHM."""
    scaled = _scaled_energy(energy, position, fwhm)
    if form == StepForm.ERF:
        return 0.5 * (1 + erf(2 * sqrt(log(2)) * scaled))
    if form == StepForm.ARCTAN:
        return 0.5 + np.arctan(2 * scaled) / pi
    raise ValueError(f"Unknown IP step form: {form!r}")


@dataclass(frozen=True, slots=True)
class Gaussian:
    center: float
    fwhm: float
    area: float

    def evaluate(self, energy):
        if not isfinite(self.area):
            raise ValueError("Gaussian area must be finite.")
        return self.area * gaussian_basis(energy, self.center, self.fwhm)


@dataclass(frozen=True, slots=True)
class IPStep:
    position: float
    fwhm: float
    height: float
    form: StepForm = StepForm.ERF

    def evaluate(self, energy):
        if not isfinite(self.height):
            raise ValueError("IP step height must be finite.")
        return self.height * ip_step_basis(energy, self.position, self.fwhm, self.form)


def evaluate_model(energy, components):
    """Sum Gaussian areas and IP heights on the supplied grid."""
    energy = np.asarray(energy, dtype=float)
    total = np.zeros_like(energy)
    for component in components:
        total += component.evaluate(energy)
    return total


class ParameterMode(StrEnum):
    FIXED = "fixed"
    SHARED = "shared"
    INDEPENDENT = "independent"


@dataclass(frozen=True, slots=True)
class FitComponent:
    """An initial component and its constraints, keyed independently of table order.

    Positions and FWHMs are in eV. A missing bound uses the solver default.
    Gaussian areas are always independent. IP heights may be shared in Pass 2.
    """

    key: str
    initial: Gaussian | IPStep
    position_mode: ParameterMode = ParameterMode.FIXED
    width_mode: ParameterMode = ParameterMode.FIXED
    position_bounds: tuple[float | None, float | None] = (None, None)
    width_bounds: tuple[float | None, float | None] = (None, None)
    amplitude_mode: ParameterMode = ParameterMode.INDEPENDENT

    def __post_init__(self):
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("A component needs a nonempty identifier.")
        if not isinstance(self.initial, (Gaussian, IPStep)):
            raise TypeError("Expected a Gaussian or IP step.")
        for name in ("position_mode", "width_mode", "amplitude_mode"):
            object.__setattr__(self, name, ParameterMode(getattr(self, name)))
        if self.amplitude_mode == ParameterMode.FIXED or (
            isinstance(self.initial, Gaussian) and self.amplitude_mode != ParameterMode.INDEPENDENT
        ):
            raise ValueError("Gaussian areas must be independent and IP heights must be independent or shared.")
        position, width, amplitude = self.values
        self.initial.evaluate([position])
        if amplitude < 0:
            raise ValueError("Initial Gaussian areas and IP heights must be nonnegative.")
        for name, value, bounds in (
            ("position_bounds", position, self.position_bounds),
            ("width_bounds", width, self.width_bounds),
        ):
            low, high = bounds
            if any(limit is not None and not isfinite(limit) for limit in bounds):
                raise ValueError(f"{self.key}: explicit bounds must be finite.")
            if name == "width_bounds" and any(limit is not None and limit <= 0 for limit in bounds):
                raise ValueError(f"{self.key}: width bounds must be positive.")
            if (low is not None and high is not None and low >= high
                    or low is not None and value < low or high is not None and value > high):
                raise ValueError(f"{self.key}: invalid {name} for the initial value.")
            object.__setattr__(self, name, (low, high))

    @property
    def values(self):
        if isinstance(self.initial, Gaussian):
            return self.initial.center, self.initial.fwhm, self.initial.area
        return self.initial.position, self.initial.fwhm, self.initial.height


@dataclass(frozen=True, slots=True)
class FitModel:
    components: tuple[FitComponent, ...]
    fit_range: tuple[float, float] | None = None

    def __post_init__(self):
        components = tuple(self.components)
        if not any(isinstance(component.initial, IPStep) for component in components):
            raise ValueError("The fit model needs at least one IP step.")
        if len({component.key for component in components}) != len(components):
            raise ValueError("Component identifiers must be unique.")
        object.__setattr__(self, "components", components)
        if self.fit_range is not None:
            low, high = self.fit_range
            if not (isfinite(low) and isfinite(high) and low < high):
                raise ValueError("The fit interval must have finite, increasing limits.")
            object.__setattr__(self, "fit_range", (low, high))


def _component_basis(energy, template, position, width, derivatives):
    """Unit basis and, when requested, its derivatives in position and FWHM."""
    scaled = (energy - position) / width
    if isinstance(template, Gaussian):
        basis = gaussian_basis(energy, position, width)
        if not derivatives:
            return basis
        term = 8 * log(2) * scaled
        return basis, basis * term / width, basis * (term * scaled - 1) / width
    basis = ip_step_basis(energy, position, width, template.form)
    if not derivatives:
        return basis
    if template.form == StepForm.ERF:
        slope = gaussian_basis(energy, position, width)
    else:
        slope = 2 / (pi * width * (1 + (2 * scaled)**2))
    return basis, -slope, -slope * scaled
