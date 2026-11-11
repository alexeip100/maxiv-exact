"""Versioned JSON configurations and self-contained HDF5 analyses."""

import json
import os
from dataclasses import asdict, dataclass, replace
from math import isfinite, isinf
from pathlib import Path
from tempfile import NamedTemporaryFile

import h5py
import numpy as np

from .group import GroupBGSettings, ProcessedGroup, capture_group, mean_spectrum
from .model import FitComponent, FitModel, Gaussian, IPStep, StepForm, evaluate_model
from .solver import FitDiagnostics, FitResult, SpectrumFit
from .trends import Experiment


_CONFIG = "maxiv-exact/nexafs-fit-configuration"
_ANALYSIS = "maxiv-exact/nexafs-fit-analysis"
_VERSION = 1
_STAGES = {"reference", "pass1", "pass2"}


@dataclass(frozen=True)
class Configuration:
    model: FitModel
    names: dict[str, str]
    experiment: Experiment


@dataclass(frozen=True)
class SavedAnalysis:
    group: ProcessedGroup
    configuration: Configuration
    results: dict[str, FitResult]


def _text(value):
    if not isinstance(value, str):
        raise ValueError("Expected text in the NEXAFS file.")
    return value


def _number(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("Expected a finite number in the NEXAFS file.")
    return float(value)


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("Expected a Boolean in the NEXAFS file.")
    return value


def _pair(values, *, optional=False):
    low, high = values
    return tuple(None if optional and v is None else _number(v) for v in (low, high))


def _validate_schema(doc, schema):
    if doc["format"] != schema or type(doc["version"]) is not int or doc["version"] != _VERSION:
        raise ValueError("Unsupported NEXAFS file format or schema version.")


def _component_doc(component):
    return {"kind": "gaussian" if isinstance(component, Gaussian) else "ip", **asdict(component)}


def _read_component(doc):
    kind = doc["kind"]
    if kind == "gaussian":
        result = Gaussian(_number(doc["center"]), _number(doc["fwhm"]), _number(doc["area"]))
        amplitude = result.area
    elif kind == "ip":
        result = IPStep(_number(doc["position"]), _number(doc["fwhm"]), _number(doc["height"]),
                        StepForm(doc["form"]))
        amplitude = result.height
    else:
        raise ValueError("Unknown NEXAFS component type.")
    if result.fwhm <= 0 or amplitude < 0:
        raise ValueError("FWHMs must be positive and fitted amplitudes must be nonnegative.")
    return result


def _model_doc(model):
    return {
        "fit_range": model.fit_range,
        "components": [{**asdict(spec), "initial": _component_doc(spec.initial)} for spec in model.components],
    }


def _read_model(doc):
    limits = doc["fit_range"]
    components = []
    for spec in doc["components"]:
        components.append(FitComponent(
            _text(spec["key"]), _read_component(spec["initial"]),
            spec["position_mode"], spec["width_mode"], _pair(spec["position_bounds"], optional=True),
            _pair(spec["width_bounds"], optional=True), spec["amplitude_mode"],
        ))
    return FitModel(tuple(components), None if limits is None else _pair(limits))


def _configuration_doc(config, names):
    return {"model": _model_doc(config.model), "names": names, "experiment": asdict(config.experiment)}


def _read_configuration(doc):
    model = _read_model(doc["model"])
    names = {_text(k): _text(v) for k, v in doc["names"].items()}
    if any(not names.get(spec.key, "").strip() for spec in model.components):
        raise ValueError("A component is missing its name.")
    exp = doc["experiment"]
    experiment = Experiment(_text(exp["name"]), _text(exp["unit"]),
                            {_text(k): _number(v) for k, v in exp["values"].items()})
    return Configuration(model, names, experiment)


def _json(doc):
    return json.dumps(doc, ensure_ascii=False, allow_nan=False)


def _write_atomic(path, write):
    path = Path(path)
    with NamedTemporaryFile(dir=path.parent, prefix=".exact-", suffix=".tmp", delete=False) as file:
        temporary = Path(file.name)
    try:
        write(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _check_target(path, suffixes, group=None):
    path = Path(path)
    if path.suffix.lower() not in suffixes:
        raise ValueError(f"Use a {' or '.join(suffixes)} file.")
    if group is not None:
        target = path.resolve()
        for spectrum in group.spectra:
            source, separator, _ = spectrum.key.partition("##")
            if separator and Path(source).resolve() == target:
                raise ValueError("Choose a separate output file from the source spectrum data.")
    return path


def save_configuration(path, config, group=None):
    path = _check_target(path, (".json",), group)
    if h5py.is_hdf5(path):
        raise ValueError("Choose a JSON file separate from existing HDF5 data.")
    names = {spec.key: config.names[spec.key] for spec in config.model.components}
    doc = {"format": _CONFIG, "version": _VERSION, **_configuration_doc(config, names)}
    _write_atomic(path, lambda tmp: tmp.write_text(_json(doc), encoding="utf-8"))


def load_configuration(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        _validate_schema(doc, _CONFIG)
        return _read_configuration(doc)
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("Invalid NEXAFS configuration.") from error


def _diagnostics_doc(diagnostics):
    if diagnostics is None:
        return None
    doc = asdict(diagnostics)
    if diagnostics.condition_number is not None and isinf(diagnostics.condition_number):
        doc["condition_number"] = "inf"
    return doc


def _read_diagnostics(doc):
    condition = doc["condition_number"]
    rms = None if doc["rms"] is None else _number(doc["rms"])
    if rms is not None and rms < 0:
        raise ValueError("Residual RMS cannot be negative.")
    def optional_count(key, *, signed=False):
        value = doc.get(key)
        if value is not None and (type(value) is not int or (not signed and value < 0)):
            raise ValueError("Invalid stored solver termination details.")
        return value

    return FitDiagnostics(
        _boolean(doc["converged"]), _text(doc["message"]), rms,
        tuple(map(_text, doc["bounds_reached"])), tuple(map(_text, doc["warnings"])),
        None if condition is None else (float("inf") if condition == "inf" else _number(condition)),
        solver=None if doc.get("solver") is None else _text(doc["solver"]),
        status=optional_count("status", signed=True), nfev=optional_count("nfev"),
        njev=optional_count("njev"), nit=optional_count("nit"),
        optimality=None if doc.get("optimality") is None else _number(doc["optimality"]),
        cost=None if doc.get("cost") is None else _number(doc["cost"]),
    )


def save_analysis(path, analysis):
    path = _check_target(path, (".h5", ".hdf5"), analysis.group)
    if path.exists():
        # Never replace raw or unrelated HDF5 data, even if it was not in this group.
        with h5py.File(path, "r") as previous:
            if previous.attrs.get("format") != _ANALYSIS or previous.attrs.get("version") != _VERSION:
                raise ValueError("Choose a new file or an existing NEXAFS analysis of the same schema version.")
    group, config = analysis.group, analysis.configuration

    def write(temporary):
        doc = {"configuration": _configuration_doc(config, config.names), "revision": group.revision,
               "settings": asdict(group.settings), "spectra": [], "fits": {}}
        with h5py.File(temporary, "w") as file:
            file.attrs["format"] = _ANALYSIS
            file.attrs["version"] = _VERSION
            spectra = file.create_group("spectra")
            for index, row in enumerate(group.spectra):
                spectra.create_dataset(str(index), data=np.stack([row.energy, row.intensity]))
                doc["spectra"].append({"key": row.key, "label": row.label, "range": row.normalization_range})
            fits = file.create_group("fits")
            for stage, result in analysis.results.items():
                stage_group = fits.create_group(stage)
                stage_doc = {"model": _model_doc(result.model), "fit_range": result.fit_range,
                             "group_revision": result.group_revision,
                             "global_diagnostics": _diagnostics_doc(result.global_diagnostics), "rows": []}
                doc["fits"][stage] = stage_doc
                for index, row in enumerate(result.spectra):
                    stage_group.create_dataset(str(index), data=np.stack([
                        row.energy, row.observed, row.prediction, row.residual
                    ]))
                    stage_doc["rows"].append({
                        "key": row.key, "label": row.label, "diagnostics": _diagnostics_doc(row.diagnostics),
                        "components": [_component_doc(component) for component in row.components],
                    })
            file.create_dataset("manifest", data=_json(doc), dtype=h5py.string_dtype("utf-8"))

    _write_atomic(path, write)


def _local_child(group, name, kind):
    if not isinstance(group.get(name, getlink=True), h5py.HardLink):
        raise ValueError("NEXAFS analyses must contain their data locally.")
    obj = group[name]
    if not isinstance(obj, kind) or (kind is h5py.Dataset and (obj.is_virtual or obj.external)):
        raise ValueError("Unexpected or externally stored NEXAFS analysis data.")
    return obj


def _matrix(group, index, rows):
    dataset = _local_child(group, str(index), h5py.Dataset)
    if dataset.ndim != 2 or dataset.shape[0] != rows or dataset.dtype.kind != "f":
        raise ValueError("Invalid NEXAFS data array dimensions or type.")
    data = dataset[...]
    data.setflags(write=False)
    return data


def _read_group(file, doc):
    source = _local_child(file, "spectra", h5py.Group)
    keys, arrays, ranges = [], {}, []
    for index, row in enumerate(doc["spectra"]):
        key = _text(row["key"])
        if not key or key in arrays:
            raise ValueError("Spectrum identifiers must be nonempty and unique.")
        x, y = _matrix(source, index, 2)
        keys.append(key)
        arrays[key] = (_text(row["label"]), x, y)
        ranges.append(_pair(row["range"]))
    settings = doc["settings"]
    degree = settings["polynomial_degree"]
    preedge = _number(settings["preedge_fraction"])
    channel = settings["normalization_channel"]
    if type(degree) is not int or degree < 0 or not 0 <= preedge <= 1:
        raise ValueError("Invalid Group BG settings.")
    group, issue = capture_group(keys, arrays, {}, GroupBGSettings(
        degree, preedge, _boolean(settings["match_preedge_slope"]), None if channel is None else _text(channel)
    ))
    revision = _text(doc["revision"])
    if group is None or not revision or tuple(ranges) != tuple(s.normalization_range for s in group.spectra):
        raise ValueError(issue or "Stored normalization ranges do not match the processed spectra.")
    return replace(group, revision=revision)


def _read_result(stage, data, source, group, names):
    model = _read_model(data["model"])
    if not all(names.get(spec.key, "").strip() for spec in model.components):
        raise ValueError("A fitted component is missing its name.")
    if data["group_revision"] != group.revision:
        raise ValueError("Fit results belong to a different spectral group.")
    limits = _pair(data["fit_range"])
    if limits[0] >= limits[1] or (model.fit_range is not None and limits != model.fit_range):
        raise ValueError("Invalid stored fit range.")
    diag = data["global_diagnostics"]
    if (stage == "pass2") != (diag is not None):
        raise ValueError("Invalid global fitting diagnostics.")
    diag = None if diag is None else _read_diagnostics(diag)
    keys = [row["key"] for row in data["rows"]]
    by_key = {s.key: s for s in group.spectra}
    if stage == "reference":
        if len(keys) != 1 or (keys[0] is not None and keys[0] not in by_key):
            raise ValueError("Invalid reference spectrum identifier.")
    elif keys != list(by_key):
        raise ValueError("Fit results do not match the stored spectral group.")

    fits = []
    for index, row in enumerate(data["rows"]):
        key = row["key"]
        x, y, prediction, residual = _matrix(source, index, 4)
        if key is None:
            expected_x, expected_y = mean_spectrum(((s.energy, s.intensity) for s in group.spectra), limits)
        else:
            spectrum = by_key[key]
            valid = np.isfinite(spectrum.intensity) & (spectrum.energy >= limits[0]) & (spectrum.energy <= limits[1])
            expected_x, expected_y = spectrum.energy[valid], spectrum.intensity[valid]
        if not (np.array_equal(x, expected_x) and np.array_equal(y, expected_y)):
            raise ValueError("Fitted samples do not match the captured spectrum.")
        components = tuple(_read_component(item) for item in row["components"])
        metrics = _read_diagnostics(row["diagnostics"])
        if components:
            if (len(components) != len(model.components) or any(
                type(fit) is not type(spec.initial) or isinstance(fit, IPStep) and fit.form != spec.initial.form
                for fit, spec in zip(components, model.components)
            )):
                raise ValueError("Fitted components do not match the stored model.")
            if (x.size < 3 or not np.allclose(prediction, evaluate_model(x, components), rtol=1e-10, atol=1e-13)
                    or not np.allclose(residual, y - prediction, rtol=1e-10, atol=1e-13)
                    or metrics.rms is None or not np.isclose(metrics.rms, np.sqrt(np.mean(residual**2)))):
                raise ValueError("Inconsistent fitted curves or residual metrics.")
        elif metrics.converged or metrics.rms is not None or not (np.isnan(prediction).all() and np.isnan(residual).all()):
            raise ValueError("Invalid unavailable fit record.")
        fits.append(SpectrumFit(key, _text(row["label"]), x, y, prediction, residual, components, metrics))
    if diag is not None:
        if diag.rms is None:
            consistent = not diag.converged and all(not fit.components for fit in fits)
        else:
            consistent = (all(fit.usable and fit.diagnostics.converged == diag.converged for fit in fits)
                          and np.isclose(diag.rms, np.sqrt(np.mean([fit.diagnostics.rms**2 for fit in fits]))))
        if not consistent:
            raise ValueError("Inconsistent global fit diagnostics.")
    return FitResult(stage, group.revision, model, limits, tuple(fits), diag)


def load_analysis(path):
    try:
        with h5py.File(path, "r") as file:
            if file.attrs.get("format") != _ANALYSIS or file.attrs.get("version") != _VERSION:
                raise ValueError("Unsupported NEXAFS analysis format or schema version.")
            manifest = _local_child(file, "manifest", h5py.Dataset)
            if manifest.shape != ():
                raise ValueError("Invalid NEXAFS analysis manifest.")
            doc = json.loads(manifest.asstr()[()])
            group = _read_group(file, doc)
            config = _read_configuration(doc["configuration"])
            if config.experiment.for_group(group).values != config.experiment.values:
                raise ValueError("Experimental values reference unknown spectra.")
            results = {}
            sources = _local_child(file, "fits", h5py.Group)
            for stage, data in doc["fits"].items():
                if stage not in _STAGES:
                    raise ValueError("Unknown fit stage in the NEXAFS analysis.")
                results[stage] = _read_result(stage, data, _local_child(sources, stage, h5py.Group),
                                              group, config.names)
            return SavedAnalysis(group, config, results)
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("Invalid NEXAFS analysis.") from error
