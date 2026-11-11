"""Scientific definitions and Group BG handoff for NEXAFS Fit / Trends."""

import h5py
import numpy as np
import pytest
from matplotlib.figure import Figure
from types import SimpleNamespace

from maxiv_exact.compat import trapezoid
from maxiv_exact.nexafs_fit.model import (
    Gaussian, IPStep, StepForm, evaluate_model, gaussian_basis, ip_step_basis,
)
from maxiv_exact.plotting.mixin_group_bg import GroupBackgroundMixin
from maxiv_exact.plotting.mixin_processed_plot import ProcessedPlotMixin
from maxiv_exact.processing import ProcessingMixin


def test_gaussian_amplitude_is_integrated_area():
    center, fwhm, area = 286.0, 1.8, 0.37
    energy = np.linspace(center - 8 * fwhm, center + 8 * fwhm, 4001)
    gaussian = Gaussian(center, fwhm, area)
    assert trapezoid(gaussian.evaluate(energy), energy) == pytest.approx(area)
    basis = gaussian_basis([center, center + fwhm / 2], center, fwhm)
    assert basis[1] == pytest.approx(basis[0] / 2)
    with pytest.raises(ValueError, match="FWHM"):
        gaussian_basis(energy, center, 0)


@pytest.mark.parametrize("form", [StepForm.ERF, StepForm.ARCTAN])
def test_step_height_midpoint_and_derivative_fwhm(form):
    center, fwhm, height = 290.0, 2.4, 0.09
    step = IPStep(center, fwhm, height, form)
    # Finite differences verify the public width convention for both forms.
    sample = np.array([center, center + fwhm / 2])
    eps = 1e-4
    derivative = (step.evaluate(sample + eps) - step.evaluate(sample - eps)) / (2 * eps)
    assert derivative[1] == pytest.approx(derivative[0] / 2, rel=1e-6)
    assert evaluate_model([center], [step])[0] == pytest.approx(height / 2)
    assert ip_step_basis(center + 1e6, center, fwhm, form) == pytest.approx(1)


class _ProcessedView(GroupBackgroundMixin, ProcessedPlotMixin, ProcessingMixin):
    """Real processing and plots with just the surrounding UI replaced."""

    def __init__(self, path):
        self.proc_ax = Figure().subplots()
        self.canvas_proc = SimpleNamespace(draw=lambda: None)
        self.nexafs_fit_button = SimpleNamespace()
        self.nexafs_fit_button.setEnabled = lambda value: setattr(self.nexafs_fit_button, "enabled", value)
        self.nexafs_fit_button.setToolTip = lambda value: setattr(self.nexafs_fit_button, "reason", value)
        self.combo_bg = SimpleNamespace(currentText=lambda: "Auto")
        self.combo_poly = SimpleNamespace(currentText=lambda: "2")
        self.combo_post_norm = SimpleNamespace(currentText=lambda: "Area")
        self.spin_preedge = SimpleNamespace(value=lambda: 15)
        self.subtract = True
        self.chk_show_without_bg = SimpleNamespace(isChecked=lambda: self.subtract)
        self.chk_group_bg = SimpleNamespace(isChecked=lambda: True, isEnabled=lambda: True)
        self.chk_group_bg_slope = SimpleNamespace(isChecked=lambda: False)
        self.chk_sum = self.chk_normalize = self.chk_group_bg_slope
        self.plot_data = {}
        self.raw_visibility = {}
        with h5py.File(path, "w") as file:
            for index in range(3):
                # Different native sampling densities, including uneven spacing.
                fraction = np.linspace(0, 1, 101 + 20 * index) ** (1 + index / 5)
                energy = 278 + 28 * fraction
                parent = f"entry{index}/measurement"
                file[f"{parent}/energy"] = energy
                key = f"{path}##{parent}/pfy"
                self.plot_data[key] = (
                    0.35 + 0.01 * (energy - 278)
                    + Gaussian(287.0, 1.9, 0.5 + 0.2 * index).evaluate(energy)
                    + IPStep(292.0, 1.5, 0.3).evaluate(energy)
                )
                self.raw_visibility[key] = True

    @staticmethod
    def _open_h5_read(path):
        return h5py.File(path, "r")

    def shorten_label(self, label):
        return label

    def _get_persistent_curve_color(self, key):
        return None

    def _noop(self, *args):
        pass

    _set_group_bg_mode = _update_group_bg_checkbox_state = _update_group_bg_slope_checkbox_state = _noop
    update_pass_button_state = update_proc_tree = _noop


def test_capture_matches_drawn_curves_and_is_invalidated_on_refresh(tmp_path):
    view = _ProcessedView(tmp_path / "group.h5")
    view.update_plot_processed()
    snapshot = view._nexafs_group
    assert view.nexafs_fit_button.enabled, view.nexafs_fit_button.reason
    assert len(snapshot.spectra) == 3
    assert [s.energy.size for s in snapshot.spectra] == [101, 121, 141]
    for spectrum in snapshot.spectra:
        x, y = view._get_drawn_processed_xy(spectrum.key)
        np.testing.assert_array_equal(spectrum.energy, x)
        np.testing.assert_array_equal(spectrum.intensity, y)
        assert trapezoid(y, x) == pytest.approx(1)
        assert not np.shares_memory(spectrum.intensity, y)
        assert not spectrum.energy.flags.writeable
        assert not spectrum.intensity.flags.writeable

    view.subtract = False
    view.update_plot_processed()
    assert view._nexafs_group is None
    assert not view.nexafs_fit_button.enabled
    assert "background subtraction" in view.nexafs_fit_button.reason
    assert all(trapezoid(s.intensity, s.energy) == pytest.approx(1) for s in snapshot.spectra)

    view.subtract = True
    view.raw_visibility[next(iter(view.plot_data))] = False
    view.update_plot_processed()
    assert not view.nexafs_fit_button.enabled
    assert "three spectra" in view.nexafs_fit_button.reason


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        ("no_energy", "no photon-energy axis"),
        ("different_range", "area-normalization energy ranges differ"),
        ("no_equalization", "equalization did not complete"),
    ],
)
def test_one_bad_spectrum_blocks_entire_group(tmp_path, failure, reason):
    path = tmp_path / "group.h5"
    view = _ProcessedView(path)
    key = next(iter(view.plot_data))
    if failure == "no_equalization":
        view.plot_data[key] = np.zeros_like(view.plot_data[key])
    else:
        with h5py.File(path, "r+") as file:
            if failure == "no_energy":
                del file["entry0/measurement/energy"]
            else:
                file["entry0/measurement/energy"][:] += 2

    view.update_plot_processed()
    # Legacy plotting still produces curves, even when analysis is ineligible.
    assert len(view.proc_ax.lines) == 3
    assert view._nexafs_group is None
    assert reason in view.nexafs_fit_button.reason
