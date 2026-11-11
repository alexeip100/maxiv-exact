"""Integrity and data mapping for saved NEXAFS Fit / Trends analyses."""

import csv
import json
from dataclasses import replace

import h5py
import numpy as np
import pytest

from maxiv_exact.nexafs_fit.group import GroupBGSettings, capture_group
from maxiv_exact.nexafs_fit.model import FitComponent, FitModel, Gaussian, IPStep, ParameterMode, evaluate_model
from maxiv_exact.nexafs_fit.persistence import (
    Configuration, SavedAnalysis, load_analysis, load_configuration, save_analysis, save_configuration,
)
from maxiv_exact.nexafs_fit.solver import fit_pass1, fit_pass2, fit_reference
from maxiv_exact.nexafs_fit.trends import Experiment, export_fits, export_trends, trend_series


@pytest.fixture
def analysis(tmp_path):
    source = tmp_path / "source.h5"
    with h5py.File(source, "w") as file:
        file.create_dataset("raw", data=[1, 2, 3])
    curves = {}
    for i in range(3):
        x = np.linspace(525, 570, 180 + i * 10)
        y = evaluate_model(x, (IPStep(540, 4, 0.02), Gaussian(530, 1.3, 0.03 * (i + 1)),
                               Gaussian(534, 2.1, 0.02)))
        # All labels deliberately equal. Only the identifier can map metadata.
        curves[f"{source}##entry{i}/measurement/tey"] = ("TEY", x, y)
    group, reason = capture_group(list(curves), curves, {}, GroupBGSettings(2, .15, True, None))
    assert group is not None, reason
    model = FitModel((
        FitComponent("ip", IPStep(540, 4, 0.01), amplitude_mode=ParameterMode.SHARED),
        FitComponent("a", Gaussian(530, 1.3, 0.03), position_bounds=(529, 531)),
        FitComponent("b", Gaussian(534, 2.1, 0.02)),
    ), (527, 568))
    config = Configuration(model, {"ip": "Edge", "a": "Resonance α", "b": "Resonance β"},
                           Experiment("Temperature", "K", {group.spectra[2].key: 397.123456789}))
    results = {"reference": fit_reference(group, model), "pass1": fit_pass1(group, model),
               "pass2": fit_pass2(group, model)}
    return SavedAnalysis(group, config, results), source


def test_configuration_round_trip_and_identifier_mapping(analysis, tmp_path):
    data, _ = analysis
    config = data.configuration
    file = tmp_path / "config.json"
    save_configuration(file, config, data.group)
    loaded = load_configuration(file)
    assert loaded == config
    a, b, c = data.group.spectra
    reordered = replace(data.group, spectra=(c, a, b))
    assert [loaded.experiment.for_group(reordered).values.get(s.key) for s in reordered.spectra] == [
        397.123456789, None, None,
    ]
    assert not loaded.experiment.for_group(replace(data.group, spectra=(a, b))).values
    doc = json.loads(file.read_text(encoding="utf-8"))
    doc["version"] = 999
    file.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        load_configuration(file)


def test_analysis_is_standalone_and_preserves_distinct_model_versions(analysis, tmp_path):
    data, source = analysis
    old = data.configuration.model
    newer = replace(old, components=old.components[:-1])
    config = replace(data.configuration, model=newer)
    data = replace(data, configuration=config)
    # An unavailable fit is persisted, including its finite observed samples.
    p1 = data.results["pass1"]
    row = p1.spectra[-1]
    nan = np.full(row.energy.shape, np.nan)
    failed = replace(row, components=(), prediction=nan, residual=nan,
                     diagnostics=replace(row.diagnostics, converged=False, rms=None, message="Fit unavailable"))
    data = replace(data, results={**data.results, "pass1": replace(p1, spectra=(*p1.spectra[:-1], failed))})
    path = tmp_path / "analysis.h5"
    original = source.read_bytes()
    with pytest.raises(ValueError, match="separate output"):
        save_analysis(source, data)
    assert source.read_bytes() == original
    save_analysis(path, data)
    source.rename(tmp_path / "moved-source.h5")
    restored = load_analysis(path)
    assert restored.configuration == config
    assert restored.group.revision == data.group.revision
    assert restored.group.settings == data.group.settings
    assert restored.results.keys() == data.results.keys()
    for expected, actual in zip(data.group.spectra, restored.group.spectra):
        assert expected.key == actual.key and expected.normalization_range == actual.normalization_range
        np.testing.assert_array_equal(actual.energy, expected.energy)
        np.testing.assert_array_equal(actual.intensity, expected.intensity)
        assert not actual.intensity.flags.writeable
    for stage, result in restored.results.items():
        expected = data.results[stage]
        assert result.model == old and result.model != config.model
        assert result.global_diagnostics == expected.global_diagnostics
        for actual, original_row in zip(result.spectra, expected.spectra):
            assert actual.components == original_row.components
            assert actual.diagnostics == original_row.diagnostics
            np.testing.assert_array_equal(actual.residual, original_row.residual)
    with h5py.File(path, "r+") as file:
        file["fits/pass2/0"][3, 0] = 10
    with pytest.raises(ValueError, match="residual"):
        load_analysis(path)


def _csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_pass_exports_keep_mapping_and_undefined_ratios(analysis, tmp_path):
    data, _ = analysis
    group, config = data.group, data.configuration
    p1, p2 = data.results["pass1"], data.results["pass2"]
    first, second, third = p2.spectra
    small = replace(first, components=(*first.components[:-1], replace(first.components[-1], area=1e-16)))
    provisional = replace(second, diagnostics=replace(second.diagnostics, converged=False, status=0, nfev=600))
    bad = replace(p1.spectra[1], prediction=np.full_like(second.prediction, np.nan))
    results = {"pass1": replace(p1, spectra=(p1.spectra[0], bad, p1.spectra[2])),
               "pass2": replace(p2, spectra=(small, provisional, third))}
    path = tmp_path / "fits.csv"
    export_fits(path, group, results, config.names, config.experiment, ("pass1",))
    rows = _csv_rows(path)
    assert len(rows) == 18
    index = {(row["pass"], row["spectrum_id"], row["component_id"]): row for row in rows}
    third_key = group.spectra[2].key
    row = index["Pass 2", third_key, "a"]
    assert float(row["experimental_parameter_value"]) == config.experiment.values[third_key]
    assert float(row["gaussian_area_processed_intensity_eV"]) == third.components[1].area
    assert row["component_name"] == "Resonance α" and row["outdated"] == "False"
    assert index["Pass 1", third_key, "ip"]["outdated"] == "True"
    provisional_row = index["Pass 2", group.spectra[1].key, "a"]
    assert provisional_row["fit_status"] == "Provisional"
    assert provisional_row["solver_status"] == "0" and provisional_row["function_evaluations"] == "600"
    bad_row = index["Pass 1", group.spectra[1].key, "a"]
    assert bad_row["fit_status"] == "Failed" and bad_row["gaussian_area_processed_intensity_eV"] == ""

    hidden = trend_series(group, results, ("pass1", "pass2"), "ratio", ["a"], "b")
    assert hidden[1].statuses == ("Undefined ratio", "Provisional", "Converged")
    assert hidden[1].values[1] is None
    series = trend_series(group, results, ("pass1", "pass2"), "ratio", ["a"], "b", show_provisional=True)
    assert series[1].values[1] == pytest.approx(3)
    assert series[0].values[1] is None and series[0].statuses[1] == "Failed"
    path = tmp_path / "trend.csv"
    export_trends(path, group, series, config.names, config.experiment, "ratio", True)
    rows = _csv_rows(path)
    assert len(rows) == 6 and rows[3]["status"] == "Undefined ratio" and rows[3]["value"] == ""
    assert rows[0]["status"] == "Missing experimental value" and rows[0]["x_value"] == ""
    assert rows[4]["fit_status"] == "Provisional" and rows[4]["status"] == "Missing experimental value"
    assert float(rows[-1]["value"]) == pytest.approx(4.5)
    assert rows[-1]["x_unit"] == "K" and rows[-1]["denominator_id"] == "b"
