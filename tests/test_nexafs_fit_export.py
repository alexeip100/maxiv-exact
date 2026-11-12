"""Fit exports preserve native points, per-component values and result status."""

import csv
from dataclasses import replace
import io
import json
from zipfile import ZipFile

import numpy as np
import pytest

from maxiv_exact.nexafs_fit.fit_export import export_fit_pass
from maxiv_exact.nexafs_fit.group import GroupBGSettings, capture_group
from maxiv_exact.nexafs_fit.model import FitComponent, FitModel, Gaussian, IPStep, StepForm, evaluate_model
from maxiv_exact.nexafs_fit.solver import fit_pass1, fit_pass2
from maxiv_exact.nexafs_fit.trends import Experiment


@pytest.fixture
def fit_group():
    components = (
        FitComponent("peak", Gaussian(530.123456789, 1.4, 0.024)),
        FitComponent("step_a", IPStep(538, 3, 0.021)),
        FitComponent("step_b", IPStep(543, 2, 0.012, StepForm.ARCTAN)),
    )
    model = FitModel(components, (524, 548))
    scans = {}
    for index in range(3):
        energy = np.linspace(520, 550, 80 + index)
        scans[str(index)] = ("Repeated label", energy, evaluate_model(energy, [spec.initial for spec in components]))
    group, reason = capture_group(list(scans), scans, {}, GroupBGSettings(2, .12, False, None))
    assert group is not None, reason
    return group, model


def test_pass2_zip_retains_native_curves_and_full_precision_metadata(tmp_path, fit_group):
    group, model = fit_group
    result = fit_pass2(group, model)
    path = tmp_path / "fit.zip"
    export_fit_pass(path, group, result, {"peak": "Resonance", "step_a": "Edge", "step_b": "Edge"},
                    Experiment("Temperature", "K", {"1": 12.3456789}))

    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["pass"] == "Pass 2" and manifest["stage"] == "pass2"
        assert manifest["global_diagnostics"]["converged"]
        assert manifest["fit_interval_eV"] == [524, 548]
        assert manifest["experimental_parameter"] == {"name": "Temperature", "unit": "K"}
        for spectrum, fit, entry in zip(group.spectra, result.spectra, manifest["spectra"], strict=True):
            assert spectrum.key == fit.key == entry["key"]
            rows = list(csv.DictReader(io.StringIO(archive.read(entry["curves_csv"]).decode())))
            meta = json.loads(archive.read(entry["parameters_json"]))
            assert meta["experimental_parameter_value"] == (12.3456789 if fit.key == "1" else None)
            assert meta["components"][0]["fitted"]["center"] == 530.123456789
            assert meta["components"][2]["fitted"]["form"] == StepForm.ARCTAN.value
            assert meta["components"][0]["position_mode"] == "fixed"
            assert meta["status"] == "Converged"
            np.testing.assert_array_equal([float(row["energy_eV"]) for row in rows], spectrum.energy)
            np.testing.assert_array_equal([float(row["processed_intensity"]) for row in rows], spectrum.intensity)
            used = [row for row in rows if row["total_fit"]]
            np.testing.assert_array_equal([float(row["energy_eV"]) for row in used], fit.energy)
            np.testing.assert_array_equal([float(row["total_fit"]) for row in used], fit.prediction)
            np.testing.assert_array_equal([float(row["residual"]) for row in used], fit.residual)
            for spec, component in zip(meta["components"], fit.components, strict=True):
                column = spec["curve_column"]
                np.testing.assert_array_equal([float(row[column]) for row in used], component.evaluate(fit.energy))
                assert all(row[column] == row["residual"] == "" for row in rows if not row["total_fit"])


def test_archive_requires_opt_in_for_outdated_and_provisional_fits(tmp_path, fit_group):
    group, model = fit_group
    result = fit_pass1(group, model)
    good, provisional, failed = result.spectra
    provisional = replace(provisional, diagnostics=replace(provisional.diagnostics, converged=False, status=0))
    failed = replace(failed, components=(), diagnostics=replace(failed.diagnostics, converged=False, rms=None))
    result = replace(result, spectra=(good, provisional, failed))
    path = tmp_path / "fit.zip"
    with pytest.raises(ValueError, match="outdated"):
        export_fit_pass(path, group, result, {}, Experiment(), outdated=True)
    assert not path.exists()

    for include_provisional in (False, True):
        export_fit_pass(path, group, result, {}, Experiment(), outdated=True,
                        include_outdated=True, include_provisional=include_provisional)
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            entries = manifest["spectra"]
            assert manifest["outdated"] and manifest["pass"] == "Pass 1"
            assert [entry["status"] for entry in entries] == ["Converged", "Provisional", "Failed"]
            assert [entry["fit_values_included"] for entry in entries] == [True, include_provisional, False]
            for entry in entries:
                meta = json.loads(archive.read(entry["parameters_json"]))
                assert (meta["components"][0]["fitted"] is not None) == entry["fit_values_included"]
                rows = list(csv.DictReader(io.StringIO(archive.read(entry["curves_csv"]).decode())))
                assert any(row["processed_intensity"] for row in rows)
                assert any(row["total_fit"] for row in rows) == entry["fit_values_included"]
