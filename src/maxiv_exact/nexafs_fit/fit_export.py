"""Portable CSV and JSON exports of a completed NEXAFS fit pass."""

import csv
from dataclasses import asdict
from io import TextIOWrapper
from math import isfinite
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np

from .persistence import _check_target, _component_doc, _diagnostics_doc, _json, _model_doc, _write_atomic


def _write_curves(archive, member, spectrum, fit, columns, include_fit):
    x = spectrum.energy
    points = iter(())
    if include_fit:
        indices = np.searchsorted(x, fit.energy)
        if (np.any(indices >= x.size) or np.any(np.diff(indices) <= 0)
                or not np.array_equal(x[indices], fit.energy)
                or not np.array_equal(spectrum.intensity[indices], fit.observed)):
            raise ValueError(f"{spectrum.label}: fitted points do not match the processed spectrum.")
        curves = [component.evaluate(fit.energy) for component in fit.components]
        points = zip(indices, fit.prediction, fit.residual, *curves, strict=True)
    point = next(points, None)
    empty = ("",) * (2 + len(columns))
    with archive.open(member, "w") as raw, TextIOWrapper(raw, encoding="utf-8", newline="") as text:
        writer = csv.writer(text)
        writer.writerow(("energy_eV", "processed_intensity", "total_fit", "residual", *columns))
        for index, (energy, observed) in enumerate(zip(x, spectrum.intensity, strict=True)):
            values = empty
            if point is not None and index == point[0]:
                values = point[1:]
                point = next(points, None)
            writer.writerow((energy, observed if isfinite(observed) else "", *values))


def export_fit_pass(path, group, result, names, experiment, *, outdated=False,
                    include_outdated=False, include_provisional=False):
    """Write a ZIP for one pass, with a CSV and parameter JSON for each spectrum."""
    if result.stage not in ("pass1", "pass2") or result.group_revision != group.revision:
        raise ValueError("Choose a completed Pass 1 or Pass 2 result from this spectral group.")
    if outdated and not include_outdated:
        raise ValueError("Explicitly confirm export of the outdated fit.")
    fits = {row.key: row for row in result.spectra}
    if len(fits) != len(result.spectra) or fits.keys() != {spectrum.key for spectrum in group.spectra}:
        raise ValueError("The fitted spectra do not match the processed group.")
    path = _check_target(path, (".zip",), group)
    experiment = experiment.for_group(group)
    definitions = _model_doc(result.model)["components"]
    columns = [f"component_{index:03d}" for index in range(1, len(definitions) + 1)]
    components = [
        {**spec, "name": names.get(spec["key"], spec["key"]), "curve_column": column}
        for spec, column in zip(definitions, columns, strict=True)
    ]
    manifest = {
        "format": "maxiv-exact/nexafs-fit-export",
        "version": 1,
        "stage": result.stage,
        "pass": "Pass 1" if result.stage == "pass1" else "Pass 2",
        "outdated": outdated,
        "fit_interval_eV": result.fit_range,
        "group_revision": group.revision,
        "group_bg": asdict(group.settings),
        "global_diagnostics": _diagnostics_doc(result.global_diagnostics),
        "experimental_parameter": {"name": experiment.name, "unit": experiment.unit},
        "energy_unit": "eV",
        "ip_fwhm_definition": "FWHM of the step derivative",
        "residual_definition": "processed_intensity - total_fit",
        "spectra": [],
    }

    def write(temporary):
        with ZipFile(temporary, mode="w", compression=ZIP_DEFLATED) as archive:
            for index, spectrum in enumerate(group.spectra, 1):
                fit = fits[spectrum.key]
                usable = fit.usable and len(fit.components) == len(components)
                status = fit.diagnostics.outcome if usable else "Failed"
                include_fit = usable and (fit.diagnostics.converged or include_provisional)
                stem = f"spectra/{index:03d}"
                entry = {
                    "key": spectrum.key,
                    "label": spectrum.label,
                    "status": status,
                    "fit_values_included": include_fit,
                    "curves_csv": stem + ".csv",
                    "parameters_json": stem + ".json",
                }
                _write_curves(archive, entry["curves_csv"], spectrum, fit, columns, include_fit)
                values = [_component_doc(component) for component in fit.components] if include_fit else (
                    [None] * len(components)
                )
                metadata = {
                    **entry,
                    "stage": result.stage,
                    "outdated": outdated,
                    "fit_interval_eV": result.fit_range,
                    "normalization_interval_eV": spectrum.normalization_range,
                    "experimental_parameter_value": experiment.values.get(spectrum.key),
                    "diagnostics": _diagnostics_doc(fit.diagnostics),
                    "components": [{**spec, "fitted": fitted} for spec, fitted in zip(components, values, strict=True)],
                }
                archive.writestr(entry["parameters_json"], _json(metadata))
                manifest["spectra"].append(entry)
            archive.writestr("manifest.json", _json(manifest))

    _write_atomic(path, write)
