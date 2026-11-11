"""Bounded reference, independent, and simultaneous NEXAFS fitting.

All fits use the processed intensities as supplied. A global residual block
is divided by sqrt(number of fitted samples) for equal spectrum weighting.
"""

from dataclasses import dataclass, replace
from math import isfinite, sqrt
from typing import Callable

import numpy as np
from scipy.optimize import least_squares, lsq_linear
from scipy.sparse import csr_array, issparse

from .group import ProcessedGroup, ProcessedSpectrum, mean_spectrum
from .model import FitModel, Gaussian, IPStep, ParameterMode, _component_basis


def _use_dense_global(samples, parameters):
    """Bound Jacobian storage and the approximate work of its dense SVD."""
    elements = samples * parameters
    return elements * np.dtype(float).itemsize <= 32 * 1024**2 and elements * parameters <= 100_000_000


@dataclass(frozen=True, slots=True)
class FitDiagnostics:
    converged: bool
    message: str
    rms: float | None
    bounds_reached: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    condition_number: float | None = None
    solver: str | None = None
    status: int | None = None
    nfev: int | None = None
    njev: int | None = None
    nit: int | None = None
    optimality: float | None = None
    cost: float | None = None

    @property
    def outcome(self):
        if self.rms is None or not isfinite(self.rms) or self.rms < 0:
            return "Failed"
        return "Converged" if self.converged else "Provisional"


@dataclass(frozen=True, slots=True, eq=False)
class SpectrumFit:
    key: str | None
    label: str
    energy: np.ndarray
    observed: np.ndarray
    prediction: np.ndarray
    residual: np.ndarray
    # Same order as the keyed component definitions in FitResult.model.
    components: tuple[Gaussian | IPStep, ...]
    diagnostics: FitDiagnostics

    @property
    def usable(self):
        """Fit values must be valid before presentation or export."""
        return (
            self.diagnostics.outcome != "Failed" and bool(self.components)
            and all(all(isfinite(value) for value in _values(component))
                    and component.fwhm > 0 and _values(component)[2] >= 0
                    for component in self.components)
            and all(np.isfinite(array).all()
                    for array in (self.energy, self.observed, self.prediction, self.residual))
        )


@dataclass(frozen=True, slots=True, eq=False)
class FitResult:
    stage: str
    group_revision: str
    model: FitModel
    fit_range: tuple[float, float]
    spectra: tuple[SpectrumFit, ...]
    global_diagnostics: FitDiagnostics | None = None


class FitCancelled(Exception):
    """Raised when a requested fit is cancelled before results are returned."""


@dataclass(frozen=True, slots=True)
class _Samples:
    key: str | None
    label: str
    energy: np.ndarray
    intensity: np.ndarray

    def within(self, limits):
        keep = (self.energy >= limits[0]) & (self.energy <= limits[1])
        return _Samples(self.key, self.label, self.energy[keep], self.intensity[keep])


def _samples(spectrum: ProcessedSpectrum) -> _Samples:
    x, y = np.asarray(spectrum.energy, dtype=float), np.asarray(spectrum.intensity, dtype=float)
    if (x.ndim != 1 or y.shape != x.shape or not np.isfinite(x).all()
            or np.any(np.diff(x) <= 0)):
        raise ValueError(f"{spectrum.label}: expected matching arrays on an increasing photon-energy grid.")
    finite = np.isfinite(y)
    return _Samples(spectrum.key, spectrum.label, x[finite], y[finite])


def _fit_window(samples, model):
    if model.fit_range is not None:
        return model.fit_range
    if any(not scan.energy.size for scan in samples):
        raise ValueError("Every spectrum needs finite samples to determine a common fit interval.")
    lo = max(scan.energy[0] for scan in samples)
    hi = min(scan.energy[-1] for scan in samples)
    if lo >= hi:
        raise ValueError("The spectra have no common photon-energy interval.")
    return float(lo), float(hi)


def _average(samples, limits):
    energy, intensity = mean_spectrum(((scan.energy, scan.intensity) for scan in samples), limits)
    return _Samples(None, "Group average", energy, intensity)


def _values(component):
    if isinstance(component, Gaussian):
        return component.center, component.fwhm, component.area
    return component.position, component.fwhm, component.height


def _component(template, values):
    if isinstance(template, Gaussian):
        return Gaussian(*values)
    return IPStep(*values, form=template.form)


def _readonly(array):
    copy = array.copy()
    copy.setflags(write=False)
    return copy


def _check_cancel(cancelled):
    if cancelled is not None and cancelled():
        raise FitCancelled("NEXAFS fitting was cancelled.")


class _InsufficientData(ValueError):
    pass


class _Problem:
    """Pack each free parameter once per spectrum, or once for the entire group."""

    def __init__(self, scans, model, limits, seeds, global_fit, cancelled):
        self.scans = scans
        self.model = model
        self.global_fit = global_fit
        self.cancelled = cancelled
        if any(scan.energy.size < 3 for scan in scans):
            invalid = next(scan for scan in scans if scan.energy.size < 3)
            raise _InsufficientData(f"{invalid.label}: fewer than three finite samples in the fit interval.")

        span = limits[1] - limits[0]
        midpoint = limits[0] + 0.5 * span
        min_spacing = min(float(np.median(np.diff(scan.energy))) for scan in scans)
        default_width_bounds = (max(span * 1e-6, 0.5 * min_spacing), 2 * span)
        intensity_scale = max(float(np.max(np.abs(scan.intensity))) for scan in scans) or 1.0
        self.weights = [
            1 / (intensity_scale * (sqrt(scan.energy.size) if global_fit else 1))
            for scan in scans
        ]
        self.target = np.concatenate([scan.intensity * w for scan, w in zip(scans, self.weights)])

        initial = np.array([spec.values for spec in model.components], dtype=float)
        self.fixed = initial
        self.indices = np.full((len(scans), *initial.shape), -1, dtype=int)
        self.labels = []
        self.amplitudes = []
        lookup = {}
        start, lower, upper, origins, scales = [], [], [], [], []
        seed_values = {
            i: np.array([_values(component) for component in seed.components])
            for i, seed in seeds.items() if seed.diagnostics.converged
        }

        for row, scan in enumerate(scans):
            for col, spec in enumerate(model.components):
                gaussian = isinstance(spec.initial, Gaussian)
                position_limits = self._limits(spec.position_bounds, limits)
                width_limits = self._limits(spec.width_bounds, default_width_bounds)
                shape_scale = min(max(spec.values[1], default_width_bounds[0]), span)
                modes = spec.position_mode, spec.width_mode, spec.amplitude_mode
                names = ("center" if gaussian else "position", "FWHM", "area" if gaussian else "height")
                bounds = (position_limits, width_limits, (0.0, np.inf))
                for param, mode in enumerate(modes):
                    if mode == ParameterMode.FIXED:
                        continue
                    shared = global_fit and mode == ParameterMode.SHARED
                    variable = (None if shared else row, col, param)
                    if variable not in lookup:
                        lo, hi = bounds[param]
                        if lo >= hi:
                            raise ValueError(f"{spec.key} {names[param]}: bounds are incompatible with the fit interval.")
                        seed = initial[col, param]
                        if shared and seed_values:
                            seed = float(np.median([values[col, param] for values in seed_values.values()]))
                        elif row in seed_values:
                            seed = seed_values[row][col, param]
                        origin = midpoint if param == 0 else 0.0
                        scale = shape_scale
                        if param == 2:
                            scale = intensity_scale * (shape_scale if gaussian else 1.0)
                            self.amplitudes.append(len(start))
                        lookup[variable] = len(start)
                        scope = "shared" if shared else scan.label
                        self.labels.append(f"{spec.key} {names[param]} ({scope})")
                        start.append((np.clip(seed, lo, hi) - origin) / scale)
                        lower.append((lo - origin) / scale)
                        upper.append((hi - origin) / scale)
                        origins.append(origin)
                        scales.append(scale)
                    self.indices[row, col, param] = lookup[variable]

        self.start, self.lower, self.upper, self.origins, self.scales = map(
            np.asarray, (start, lower, upper, origins, scales)
        )
        self.amplitudes = np.asarray(self.amplitudes, dtype=int)
        private = np.bincount(
            [row for row, _, _ in lookup if row is not None], minlength=len(scans)
        )
        for scan, n_private in zip(scans, private):
            if scan.energy.size < n_private:
                raise _InsufficientData(f"{scan.label}: fewer samples than independent fit parameters.")
        if self.target.size < self.start.size:
            raise _InsufficientData("The group has fewer samples than free fit parameters.")

        self.local_indices = [indices[indices >= 0] for indices in self.indices]
        if len(scans) > 1:
            self._jacobian_columns = np.concatenate([
                np.tile(indices, scan.energy.size)
                for scan, indices in zip(scans, self.local_indices)
            ])
            self._jacobian_indptr = np.concatenate(([0], np.cumsum(np.concatenate([
                np.full(scan.energy.size, indices.size, dtype=int)
                for scan, indices in zip(scans, self.local_indices)
            ]))))

    @staticmethod
    def _limits(explicit, defaults):
        return tuple(default if value is None else value for value, default in zip(explicit, defaults))

    def _physical_values(self, physical, row):
        indices = self.indices[row]
        values = self.fixed.copy()
        free = indices >= 0
        values[free] = physical[indices[free]]
        return values

    def _evaluate(self, variables, jacobian=False, amplitude_only=False):
        _check_cancel(self.cancelled)
        physical = self.origins + self.scales * variables
        blocks = []
        for row, (scan, weight) in enumerate(zip(self.scans, self.weights)):
            values = self._physical_values(physical, row)
            if jacobian:
                columns = []
            else:
                prediction = np.zeros_like(scan.energy)
            for col, (spec, (position, width, amplitude)) in enumerate(zip(self.model.components, values)):
                indices = self.indices[row, col]
                need_derivatives = jacobian and not amplitude_only and np.any(indices[:2] >= 0)
                basis = _component_basis(scan.energy, spec.initial, position, width, need_derivatives)
                if need_derivatives:
                    basis, d_position, d_width = basis
                if jacobian:
                    if not amplitude_only:
                        if indices[0] >= 0:
                            columns.append(amplitude * d_position * self.scales[indices[0]])
                        if indices[1] >= 0:
                            columns.append(amplitude * d_width * self.scales[indices[1]])
                    columns.append(basis * self.scales[indices[2]])
                else:
                    prediction += amplitude * basis
            blocks.append(weight * (np.column_stack(columns) if jacobian else prediction))

        if not jacobian:
            return np.concatenate(blocks)
        if len(blocks) == 1:
            return blocks[0]
        if amplitude_only:
            return self._amplitude_matrix(blocks)
        return csr_array((np.concatenate([block.ravel() for block in blocks]),
                          self._jacobian_columns, self._jacobian_indptr),
                         shape=(self.target.size, self.start.size))

    def _amplitude_matrix(self, blocks):
        # Map each local amplitude column to the corresponding shared/independent column.
        lookup = {index: col for col, index in enumerate(self.amplitudes)}
        columns = np.concatenate([
            np.tile([lookup[index] for index in indices[:, 2]], scan.energy.size)
            for scan, indices in zip(self.scans, self.indices)
        ])
        n_components = len(self.model.components)
        indptr = np.arange(self.target.size + 1) * n_components
        return csr_array((np.concatenate([block.ravel() for block in blocks]), columns, indptr),
                         shape=(self.target.size, self.amplitudes.size))

    def solve(self):
        linear = self.amplitudes.size == self.start.size
        matrix = self._evaluate(self.start, jacobian=True, amplitude_only=True)
        seed = lsq_linear(matrix, self.target, bounds=(0, np.inf), tol=1e-12, lsmr_tol=1e-13)
        _check_cancel(self.cancelled)
        if linear:
            return seed, "Bounded linear least squares"
        start = self.start.copy()
        if seed.success and np.isfinite(seed.x).all():
            start[self.amplitudes] = seed.x

        # Single-spectrum fits keep the existing dense path. For Pass 2,
        # select from the actual weighted Jacobian dimensions.
        dense_global = self.global_fit and _use_dense_global(self.target.size, self.start.size)

        def jacobian(q):
            matrix = self._evaluate(q, jacobian=True)
            return matrix.toarray() if dense_global else matrix

        options = {}
        solver = "TRF exact (dense)"
        if dense_global:
            options = {"tr_solver": "exact"}
        elif self.global_fit:
            solver = "TRF LSMR (sparse)"
            options = {"tr_solver": "lsmr", "tr_options": {"atol": 1e-11, "btol": 1e-11}}
        result = least_squares(
            lambda q: self._evaluate(q) - self.target,
            start,
            jac=jacobian,
            bounds=(self.lower, self.upper),
            method="trf",
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
            max_nfev=600,
            **options,
        )
        _check_cancel(self.cancelled)
        return result, solver

    def _failed(self, diagnostics, reason=None):
        if reason:
            diagnostics = replace(diagnostics, converged=False, rms=None, warnings=(reason,))
        fits = tuple(_unavailable(scan, diagnostics) for scan in self.scans)
        return fits, diagnostics if self.global_fit else None

    def fit(self):
        try:
            result, solver = self.solve()
        except (FloatingPointError, np.linalg.LinAlgError) as error:
            return self._failed(FitDiagnostics(False, str(error), None))
        return self.results(result, solver)

    def results(self, result, solver):
        diagnostics = _termination(result, solver)
        variables = result.x
        if (variables.shape != self.start.shape or not np.isfinite(variables).all()
                or not np.isfinite(result.fun).all() or diagnostics.cost is None
                or diagnostics.optimality is None
                or not np.allclose(variables, np.clip(variables, self.lower, self.upper),
                                   rtol=1e-12, atol=1e-12)):
            return self._failed(diagnostics, "Solver returned a non-finite or infeasible result.")

        physical = self.origins + self.scales * variables
        if not np.isfinite(physical).all():
            return self._failed(diagnostics, "Fitted parameters are not finite.")
        jacobian = self._evaluate(variables, jacobian=True)
        if not np.isfinite(jacobian.data if issparse(jacobian) else jacobian).all():
            return self._failed(diagnostics, "Solver returned a non-finite Jacobian.")
        try:
            condition, warnings = _conditioning(jacobian, self.labels)
        except np.linalg.LinAlgError:
            return self._failed(diagnostics, "Jacobian conditioning could not be computed.")
        near_lower = np.isfinite(self.lower) & (variables - self.lower <= 1e-6)
        near_upper = np.isfinite(self.upper) & (self.upper - variables <= 1e-6)
        hits = {
            index: f"{self.labels[index]}: {'lower' if near_lower[index] else 'upper'} bound"
            for index in np.flatnonzero(near_lower | near_upper)
        }

        fits = []
        for row, scan in enumerate(self.scans):
            components = tuple(
                _component(spec.initial, values)
                for spec, values in zip(self.model.components, self._physical_values(physical, row))
            )
            prediction = sum(component.evaluate(scan.energy) for component in components)
            residual = scan.intensity - prediction
            row_diagnostics = replace(
                diagnostics,
                rms=float(np.sqrt(np.mean(residual**2))),
                bounds_reached=tuple(hits[index] for index in self.local_indices[row] if index in hits),
                warnings=() if self.global_fit else warnings,
                condition_number=None if self.global_fit else condition,
            )
            fit = SpectrumFit(scan.key, scan.label, *map(_readonly, (
                scan.energy, scan.intensity, prediction, residual
            )), components, row_diagnostics)
            if not fit.usable:
                return self._failed(diagnostics, "Fitted parameters or reconstructed curves are invalid.")
            fits.append(fit)

        aggregate = None
        if self.global_fit:
            rms = sqrt(sum(fit.diagnostics.rms**2 for fit in fits) / len(fits))
            aggregate = replace(diagnostics, rms=rms, bounds_reached=tuple(hits.values()),
                                warnings=warnings, condition_number=condition)
        return tuple(fits), aggregate


def _termination(result, solver):
    def optional(key, conversion):
        value = result.get(key)
        return conversion(value) if value is not None and isfinite(value) else None

    return FitDiagnostics(
        bool(result.success), str(result.message), None,
        solver=solver, status=int(result.status), nfev=optional("nfev", int),
        njev=optional("njev", int), nit=optional("nit", int),
        optimality=optional("optimality", float), cost=optional("cost", float),
    )


def _unavailable(scan, diagnostics):
    unavailable = np.full(scan.energy.shape, np.nan)
    return SpectrumFit(scan.key, scan.label, *map(_readonly, (
        scan.energy, scan.intensity, unavailable, unavailable
    )), (), diagnostics)


def _conditioning(jacobian, labels):
    """Column-normalized sensitivity and near-collinearity diagnostics."""
    gram = jacobian.T @ jacobian
    if issparse(gram):
        gram = gram.toarray()
    norms = np.sqrt(np.maximum(0, gram.diagonal()))
    informative = norms > max(float(np.max(norms)) * 1e-8, np.finfo(float).tiny)
    warnings = []
    if not informative.all():
        weak = [label for label, valid in zip(labels, informative) if not valid]
        listing = ", ".join(weak[:4])
        if len(weak) > 4:
            listing += f" and {len(weak) - 4} others"
        warnings.append(f"Poorly constrained parameters with little or no local sensitivity: {listing}.")
    if not informative.any():
        return float("inf"), tuple(warnings)

    norms = norms[informative]
    correlation = gram[np.ix_(informative, informative)] / np.outer(norms, norms)
    eigenvalues = np.linalg.eigvalsh(correlation)
    largest, smallest = float(eigenvalues[-1]), float(eigenvalues[0])
    condition = sqrt(largest / smallest) if smallest > 0 and informative.all() else float("inf")
    if condition >= 1e6:
        warnings.append("Poorly conditioned fit: the free parameters cannot be reliably separated locally.")
    row, col = np.triu_indices(len(norms), k=1)
    if row.size:
        pair = int(np.argmax(np.abs(correlation[row, col])))
        i, j = row[pair], col[pair]
        if abs(correlation[i, j]) >= 0.995:
            names = [label for label, valid in zip(labels, informative) if valid]
            warnings.append(f"Highly correlated sensitivities: {names[i]} and {names[j]}.")
    return condition, tuple(warnings)


def _fit_individual(scan, model, limits, seed, cancelled):
    try:
        problem = _Problem([scan], model, limits, {0: seed} if seed else {}, False, cancelled)
    except _InsufficientData as error:
        return _unavailable(scan, FitDiagnostics(False, str(error), None))
    fits, _ = problem.fit()
    return fits[0]


def _check_seed(seed, group, model, stage):
    if seed.stage != stage or seed.group_revision != group.revision or seed.model != model:
        raise ValueError(f"Starting results must come from a matching {stage} fit of this group and model.")


def fit_reference(group: ProcessedGroup, model: FitModel, *, spectrum_key: str | None = None,
                  cancelled: Callable[[], bool] | None = None) -> FitResult:
    """Fit the average by default, or the spectrum identified by spectrum_key."""
    _check_cancel(cancelled)
    samples = [_samples(spectrum) for spectrum in group.spectra]
    if not samples:
        raise ValueError("The group is empty.")
    if spectrum_key is None:
        if any(scan.energy.size == 0 for scan in samples):
            raise ValueError("The average reference needs finite samples from every spectrum.")
        limits = _fit_window(samples, model)
        scan = _average(samples, limits)
    else:
        scan = next((scan for scan in samples if scan.key == spectrum_key), None)
        if scan is None:
            raise ValueError(f"Unknown reference spectrum: {spectrum_key!r}.")
        limits = _fit_window([scan], model)
        scan = scan.within(limits)
    fit = _fit_individual(scan, model, limits, None, cancelled)
    return FitResult("reference", group.revision, model, limits, (fit,))


def fit_pass1(group: ProcessedGroup, model: FitModel, *, reference: FitResult | None = None,
              cancelled: Callable[[], bool] | None = None) -> FitResult:
    """Fit each scan separately. Shared shape parameters are free in each fit."""
    _check_cancel(cancelled)
    if reference is not None:
        _check_seed(reference, group, model, "reference")
    if not group.spectra:
        raise ValueError("The group is empty.")
    scans = [_samples(spectrum) for spectrum in group.spectra]
    limits = _fit_window(scans, model)
    seed = reference.spectra[0] if reference is not None else None
    results = tuple(_fit_individual(scan.within(limits), model, limits, seed, cancelled) for scan in scans)
    return FitResult("pass1", group.revision, model, limits, results)


def fit_pass2(group: ProcessedGroup, model: FitModel, *, pass1: FitResult | None = None,
              cancelled: Callable[[], bool] | None = None) -> FitResult:
    """Simultaneous group fit with independent and explicitly shared parameters."""
    _check_cancel(cancelled)
    if pass1 is not None:
        _check_seed(pass1, group, model, "pass1")
    if len(group.spectra) < 3:
        raise ValueError("The global fit requires at least three spectra.")
    scans = [_samples(spectrum) for spectrum in group.spectra]
    limits = _fit_window(scans, model)
    seeds = {}
    if pass1 is not None:
        by_key = {result.key: result for result in pass1.spectra}
        seeds = {i: by_key[scan.key] for i, scan in enumerate(scans) if scan.key in by_key}
    problem = _Problem([scan.within(limits) for scan in scans], model, limits, seeds, True, cancelled)
    fits, diagnostics = problem.fit()
    return FitResult("pass2", group.revision, model, limits, fits, diagnostics)
