"""Trend selection and CSV data for NEXAFS fits, independent of the GUI."""

import csv
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path

import h5py

from .model import Gaussian, IPStep


PASSES = {"pass1": "Pass 1", "pass2": "Pass 2"}
METRICS = {
    "area": ("Gaussian area", "processed intensity × eV", Gaussian, "area"),
    "center": ("Gaussian center", "eV", Gaussian, "center"),
    "gaussian_fwhm": ("Gaussian FWHM", "eV", Gaussian, "fwhm"),
    "height": ("IP height", "processed intensity", IPStep, "height"),
    "position": ("IP position", "eV", IPStep, "position"),
    "ip_fwhm": ("IP derivative FWHM", "eV", IPStep, "fwhm"),
    "ratio": ("Gaussian area ratio", "dimensionless", Gaussian, "area"),
}


@dataclass(frozen=True)
class Experiment:
    name: str = ""
    unit: str = ""
    values: dict[str, float] = field(default_factory=dict)

    def for_group(self, group):
        keys = {s.key for s in group.spectra}
        return Experiment(self.name, self.unit, {key: value for key, value in self.values.items() if key in keys})

    @property
    def axis_label(self):
        return f"{self.name or 'Experimental parameter'} ({self.unit})" if self.unit else (
            self.name or "Experimental parameter"
        )


@dataclass(frozen=True)
class TrendSeries:
    stage: str
    component: str
    denominator: str | None
    values: tuple[float | None, ...]
    statuses: tuple[str, ...]
    fit_statuses: tuple[str, ...]


def fit_status(row):
    if row is None:
        return "Unavailable"
    return row.diagnostics.outcome if row.usable else "Failed"


def trend_series(group, results, stages, metric, keys, denominator=None, *, show_provisional=False):
    """Return one slot per input spectrum, including gaps and their causes."""
    _, _, kind, field_name = METRICS[metric]
    series = []
    for stage in stages:
        result = results.get(stage)
        fits = {} if result is None else {row.key: row for row in result.spectra}
        fit_statuses = tuple(fit_status(fits.get(spectrum.key)) for spectrum in group.spectra)
        eligible = {"Converged", "Provisional"} if show_provisional else {"Converged"}
        component_keys = () if result is None else tuple(spec.key for spec in result.model.components)
        values = {
            spectrum.key: {key: value for key, value in zip(component_keys, fits[spectrum.key].components)
                           if isinstance(value, kind)}
            for spectrum, status in zip(group.spectra, fit_statuses) if status in eligible
        }
        largest = {status: 0.0 for status in eligible}
        if metric == "ratio":
            for spectrum, status in zip(group.spectra, fit_statuses):
                component = values.get(spectrum.key, {}).get(denominator)
                if component is not None:
                    largest[status] = max(largest[status], abs(component.area))
        for key in keys:
            measured, statuses = [], []
            for spectrum, status in zip(group.spectra, fit_statuses):
                row = values.get(spectrum.key, {})
                value = None
                if status in eligible:
                    if key not in row or (metric == "ratio" and denominator not in row):
                        status = "Component unavailable"
                    elif metric == "ratio":
                        divisor = row[denominator].area
                        if abs(divisor) <= max(1e-15, 1e-10 * largest[status]):
                            status = "Undefined ratio"
                        else:
                            value = row[key].area / divisor
                    else:
                        value = getattr(row[key], field_name)
                if value is not None and not isfinite(value):
                    value, status = None, "Non-finite value"
                measured.append(value)
                statuses.append(status)
            series.append(TrendSeries(stage, key, denominator if metric == "ratio" else None,
                                      tuple(measured), tuple(statuses), fit_statuses))
    return tuple(series)


def _prefix(index, spectrum, experiment):
    return (index, spectrum.key, spectrum.label, experiment.name, experiment.unit, experiment.values.get(spectrum.key))


_SPECTRUM_HEADERS = (
    "spectrum_index", "spectrum_id", "spectrum_name",
    "experimental_parameter_name", "experimental_parameter_unit", "experimental_parameter_value",
)


def _csv_target(path):
    path = Path(path)
    if path.suffix.lower() != ".csv" or h5py.is_hdf5(path):
        raise ValueError("Choose a CSV output file separate from existing HDF5 data.")
    return path


def export_fits(path, group, results, names, experiment, outdated=()):
    """Write one row per spectrum, pass and component, with explicit status."""
    if not any(stage in results for stage in PASSES):
        raise ValueError("Run Pass 1 or Pass 2 before exporting fitted parameters.")
    with open(_csv_target(path), "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow((*_SPECTRUM_HEADERS, "pass", "component_id", "component_name", "component_type",
                         "gaussian_area_processed_intensity_eV", "gaussian_center_eV", "gaussian_fwhm_eV",
                         "ip_height_processed_intensity", "ip_position_eV", "ip_derivative_fwhm_eV",
                         "rms_processed_intensity", "global_rms_processed_intensity", "fit_status",
                         "outdated", "fit_message", "bounds_reached", "fit_warnings", "global_fit_warnings",
                         "solver", "solver_status", "function_evaluations", "jacobian_evaluations",
                         "iterations", "optimality", "solver_cost"))
        for stage, label in PASSES.items():
            result = results.get(stage)
            if result is None:
                continue
            fits = {row.key: row for row in result.spectra}
            global_diag = result.global_diagnostics
            for index, spectrum in enumerate(group.spectra, 1):
                row = fits.get(spectrum.key)
                diag = None if row is None else row.diagnostics
                status = fit_status(row)
                termination = (None,) * 7 if diag is None else (
                    diag.solver, diag.status, diag.nfev, diag.njev, diag.nit, diag.optimality, diag.cost
                )
                for col, spec in enumerate(result.model.components):
                    fit = row.components[col] if status in {"Converged", "Provisional"} else None
                    g = (fit.area, fit.center, fit.fwhm) if isinstance(fit, Gaussian) else (None,) * 3
                    ip = (fit.height, fit.position, fit.fwhm) if isinstance(fit, IPStep) else (None,) * 3
                    writer.writerow((*_prefix(index, spectrum, experiment), label, spec.key,
                                     names.get(spec.key, spec.key),
                                     "Gaussian" if isinstance(spec.initial, Gaussian) else "IP",
                                     *g, *ip, None if diag is None else diag.rms,
                                     None if global_diag is None else global_diag.rms, status,
                                     stage in outdated, "" if diag is None else diag.message,
                                     "" if diag is None else " | ".join(diag.bounds_reached),
                                     "" if diag is None else " | ".join(diag.warnings),
                                     "" if global_diag is None else " | ".join(global_diag.warnings),
                                     *termination))


def export_trends(path, group, series, names, experiment, metric, use_experiment, outdated=()):
    """Write the selected plot's raw values and include unavailable points."""
    if not series:
        raise ValueError("Select at least one trend to export.")
    label, unit, _, _ = METRICS[metric]
    with open(_csv_target(path), "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow((*_SPECTRUM_HEADERS, "pass", "metric", "value_unit", "component_id",
                         "component_name", "denominator_id", "denominator_name", "x_axis", "x_unit",
                         "x_value", "value", "status", "fit_status", "outdated"))
        for line in series:
            points = zip(group.spectra, line.values, line.statuses, line.fit_statuses)
            for index, (spectrum, value, status, outcome) in enumerate(points, 1):
                x = experiment.values.get(spectrum.key) if use_experiment else index
                if x is None and value is not None:
                    status = "Missing experimental value"
                writer.writerow((*_prefix(index, spectrum, experiment), PASSES[line.stage], label, unit,
                                 line.component, names.get(line.component, line.component), line.denominator,
                                 names.get(line.denominator, line.denominator),
                                 (experiment.name or "Experimental parameter") if use_experiment else "Spectrum index",
                                 experiment.unit if use_experiment else "", x, value, status, outcome,
                                 line.stage in outdated))
