from unittest.mock import patch
from hashlib import sha256
from pathlib import Path

import h5py
import numpy as np
import pytest

from maxiv_exact.data import lookup_energy
from maxiv_exact.processing import subtract_spectra


def test_subtraction_uses_only_overlap_and_preserves_descending_grid_and_negatives():
    sample = (np.array([405., 404., 403., 402., 401., 400.]), np.arange(6.))
    reference = (np.array([404.5, 402.5, 400.5]), np.array([6., 4., 2.]))
    x, y = subtract_spectra(sample, reference, 1.25)
    np.testing.assert_array_equal(x, [404., 403., 402., 401.])
    np.testing.assert_allclose(y, [-5.875, -3.625, -1.375, 0.875])
    np.testing.assert_array_equal(sample[1], np.arange(6.))
    with pytest.raises(ValueError, match="overlap"):
        subtract_spectra(sample, ([404.9, 406.], [1., 2.]), 1)
    with pytest.raises(ValueError, match="strictly"):
        subtract_spectra(sample, ([401., 401., 402.], [1., 2., 3.]), 1)


@pytest.mark.parametrize("decision", ["accept", "cancel", "no overlap", "single"])
def test_plotted_csv_aligns_only_on_confirmation(tmp_path, decision):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from matplotlib.lines import Line2D
    from PyQt6.QtWidgets import QMessageBox

    from maxiv_exact.export import ExportMixin

    first_x = [405., 404., 403., 402., 401., 400.]
    other_x = [400.5, 402.5, 404.5] if decision != "no overlap" else [410., 411., 412.]
    lines = {
        "first": Line2D(first_x, [5., 4., 3., 2., 1., 0.]),
        "other": Line2D(other_x, [2., 4., 6.], visible=decision != "single"),
    }
    filename = tmp_path / "combined.csv"
    plotted = SimpleNamespace(
        plotted_lines=lines,
        custom_labels={"first": "Sample", "other": "Reference"},
        _csv_save_dialog=Mock(return_value=str(filename)),
    )
    answer = QMessageBox.StandardButton.Ok if decision == "accept" else QMessageBox.StandardButton.Cancel
    with (patch.object(QMessageBox, "question", return_value=answer) as question,
          patch.object(QMessageBox, "warning") as warning):
        ExportMixin.export_ascii_plotted(plotted)

    assert question.call_count == (1 if decision in ("accept", "cancel") else 0)
    assert warning.call_count == (1 if decision == "no overlap" else 0)
    np.testing.assert_array_equal(lines["first"].get_xdata(), first_x)
    np.testing.assert_array_equal(lines["other"].get_xdata(), other_x)
    if decision in ("cancel", "no overlap"):
        plotted._csv_save_dialog.assert_not_called()
        assert not filename.exists()
    elif decision == "accept":
        assert filename.read_text().splitlines()[0] == "Energy (eV),Sample,Reference"
        np.testing.assert_array_equal(
            np.loadtxt(filename, delimiter=",", skiprows=1),
            [[404., 4., 5.5], [403., 3., 4.5], [402., 2., 3.5], [401., 1., 2.5]],
        )
    else:
        np.testing.assert_array_equal(np.loadtxt(filename, delimiter=",", skiprows=1)[:, 0], first_x)


@pytest.mark.parametrize("group_bg", [False, True])
def test_pass_transfers_multiple_displayed_spectra_on_their_own_grids(viewer, tmp_path, group_bg):
    from PyQt6.QtWidgets import QMessageBox

    path = str(tmp_path / "spectra.h5")
    y = np.linspace(1., 2., 101) + np.r_[np.zeros(35), np.ones(66)]
    reference = "spectra/Ni/000001"
    measurements = ["entry1/measurement", "entry2/measurement", "entry3/measurement"]
    with h5py.File(path, "w") as file:
        for index, parent in enumerate([*measurements, reference]):
            group = file.create_group(parent)
            group["x"] = np.linspace(840. + index / 10, 860., y.size)
            group["y"] = y + index / 10
            group["i0"] = np.ones_like(y)
            key = f"{path}##{parent}/y"
            viewer.plot_data[key] = group["y"][:]
            viewer.raw_visibility[key] = group_bg if parent == measurements[-1] else True
        file[reference].attrs.update(x_units="eV", label="Ni literature standard")
    viewer.update_plot_raw()
    viewer.data_tabs.setCurrentIndex(1)
    if group_bg:
        viewer.combo_bg.setCurrentText("Auto")
        viewer.chk_group_bg.setChecked(True)
        assert viewer.chk_show_without_bg.isChecked()
    viewer.update_plot_processed()
    expected = {key: tuple(np.asarray(values).copy() for values in line.get_data())
                for key, line in viewer._drawn_spectra().items()}
    assert len(expected) == (4 if group_bg else 3)
    assert viewer.pass_button.isEnabled()
    viewer.pass_button.click()
    assert viewer.data_tabs.currentIndex() == 2
    assert set(viewer.plotted_lines) == expected.keys()
    for key, (x_values, y_values) in expected.items():
        passed_x, passed_y = viewer.original_line_data[key]
        np.testing.assert_array_equal(passed_x, x_values)
        np.testing.assert_array_equal(passed_y, y_values)
        assert viewer.plotted_metadata[key]["post_normalization"] == ("Area" if group_bg else "None")
    reference_key = f"{path}##{reference}/y"
    assert viewer.plotted_metadata[reference_key]["reference_title"] == "Ni literature standard"

    viewer.data_tabs.setCurrentIndex(1)
    with patch.object(QMessageBox, "warning"):
        viewer.pass_button.click()
    assert viewer.plotted_list.count() == len(expected)

    for key in viewer.plot_data:
        viewer.raw_visibility[key] = False
    viewer.raw_visibility[f"{path}##stale/measurement/y"] = True
    viewer.update_plot_processed()
    assert not viewer.pass_button.isEnabled()


@pytest.fixture
def viewer(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from maxiv_exact.ui import HDF5Viewer
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = HDF5Viewer()
    yield window
    window.close()
    app.processEvents()


def test_live_calibration_is_independent_and_absolute(viewer, tmp_path):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest

    path = str(tmp_path / "sample.h5")
    parent = "entry1/measurement"
    a, b = (f"{path}##{parent}/{channel}" for channel in ("tey", "pfy"))
    original = np.linspace(397., 407., 21)
    signal = np.linspace(0., 10., original.size)
    viewer.energy_cache[f"{path}::{parent}"] = (original, True)
    viewer.plot_data.update({a: signal, b: signal + 1})
    viewer.raw_visibility.update({a: True, b: True})
    viewer.update_plot_processed()
    limits = viewer.proc_ax.get_xlim()

    def edit(initial, first, second, accept):
        def interact():
            dialog = viewer._spectra_preview_dialog
            try:
                spin = dialog._inputs[a]
                assert spin.singleStep() == 0.05
                assert spin.value() == initial
                spin.lineEdit().selectAll()
                QTest.keyClicks(spin.lineEdit(), str(first).replace(".", spin.locale().decimalPoint()))
                QTest.keyClick(spin, Qt.Key.Key_Return)
                assert dialog.isVisible()
                assert spin.value() == first
                dialog._inputs[b].setValue(second)
                np.testing.assert_allclose(viewer._get_drawn_processed_xy(a)[0], original + first)
                np.testing.assert_allclose(viewer._get_drawn_processed_xy(b)[0], original + second)
                np.testing.assert_array_equal(viewer._get_drawn_processed_xy(a)[1], signal)
                assert viewer.proc_ax.get_xlim() == limits
            except BaseException as error:
                failures.append(error)
                dialog.reject()
            else:
                dialog.accept() if accept else dialog.reject()

        failures = []
        QTimer.singleShot(0, interact)
        viewer.open_energy_calibration_dialog()
        if failures:
            raise failures[0]

    edit(0, 0.153, -0.07, True)
    edit(0.153, 0.2, -0.8, False)
    assert viewer._energy_shifts == {a: 0.153, b: -0.07}
    edit(0.153, 0.2, 0, True)
    np.testing.assert_allclose(viewer._get_drawn_processed_xy(a)[0], original + 0.2)
    np.testing.assert_array_equal(viewer._get_drawn_processed_xy(b)[0], original)
    np.testing.assert_array_equal(lookup_energy(viewer, path, parent, len(original)), original)

    viewer.raw_visibility[b] = False
    viewer.update_plot_processed()
    assert list(viewer._drawn_spectra()) == [a]
    np.testing.assert_allclose(viewer.prepare_arrays_for_export()["x"], original + 0.2)
    assert viewer.sum_spectra_action.isEnabled()
    assert not viewer.subtract_spectra_action.isEnabled()
    from PyQt6.QtWidgets import QDialog
    from maxiv_exact.widgets.curve_summation_dialog import CurveSummationDialog

    with patch.object(CurveSummationDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
         patch.object(CurveSummationDialog, "get_groups", return_value=[{"keys": [a], "name": "Test sum"}]):
        viewer.sum_spectra_action.trigger()
    sum_key, = viewer._summed_curve_sources
    assert viewer._summed_curve_sources[sum_key] == [a]
    assert list(viewer._drawn_spectra()) == [sum_key]
    np.testing.assert_allclose(viewer._get_drawn_processed_xy(sum_key)[0], original + 0.2)
    from PyQt6.QtWidgets import QTreeWidgetItemIterator

    sample = {"name": "Sample"}
    reference = {"name": "Reference"}
    viewer._add_difference_snapshot(original, signal - 1, sample, reference, "Single", 1.0)
    diff_key, = viewer._difference_sources
    viewer.raw_visibility[a] = True
    viewer.data_tabs.setCurrentIndex(1)
    viewer.data_tabs.setCurrentIndex(0)
    raw_line, = viewer.raw_ax.get_lines()
    assert raw_line.dataset_key == a
    assert viewer.raw_ax.get_xlabel() == "Photon energy (eV)"
    np.testing.assert_array_equal(raw_line.get_xdata(), original)
    rows = QTreeWidgetItemIterator(viewer.raw_tree)
    while rows.value():
        assert rows.value().data(0, Qt.ItemDataRole.UserRole) not in {sum_key, diff_key}
        rows += 1
    viewer.data_tabs.setCurrentIndex(1)
    assert set(viewer._drawn_spectra()) == {a, sum_key, diff_key}
    np.testing.assert_allclose(viewer._get_drawn_processed_xy(a)[0], original + 0.2)


def test_group_bg_series_and_i0_difference_use_actual_plot_and_snapshot(viewer, tmp_path):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    path = str(tmp_path / "scans.h5")
    x = np.linspace(520., 550., 301)
    keys = []
    with h5py.File(path, "w") as file:
        for i in range(4):
            parent = f"entry{i}/measurement"
            monitor = np.linspace(1., 2., x.size)
            signal = monitor * (1. + .01 * (x - 520) + (x > 530) + np.exp(-((x - 535 - i) / 2)**2))
            file[f"{parent}/i0"] = monitor
            file[f"{parent}/energy"] = x
            key = f"{path}##{parent}/signal"
            keys.append(key)
            viewer.plot_data[key] = signal
            viewer.raw_visibility[key] = i < 3
    viewer.combo_norm.addItem("i0")
    viewer.combo_norm.setCurrentText("i0")
    viewer.chk_normalize.setChecked(True)
    viewer._energy_shifts[keys[1]] = 0.15
    viewer.update_plot_processed()

    def run_dialog(*, group_bg, series, create):
        failures = []
        before = dict(viewer._drawn_spectra())
        assert list(before) == keys[:3]
        expected = {}

        def interact():
            dialog = viewer._spectra_preview_dialog
            try:
                assert list(dialog.spectra) == keys[:3]
                assert dialog.reference.currentData() == keys[0]
                assert dialog.multiplier.value() == 1
                assert ("Group BG" if group_bg else "I₀-normalized") in dialog.layout().itemAt(0).widget().text()
                dialog.mode.setCurrentText("Series" if series else "Single")
                dialog.multiplier.setValue(1.3)
                assert len(dialog.results) == (2 if series else 1)
                assert len(dialog._preview) == len(dialog.results)
                for key, (energy, result) in dialog.results.items():
                    sx, sy = before[key].get_data()
                    rx, ry = before[keys[0]].get_data()
                    keep = (sx >= rx.min()) & (sx <= rx.max())
                    np.testing.assert_array_equal(energy, sx[keep])
                    np.testing.assert_allclose(result, sy[keep] - 1.3 * np.interp(sx[keep], rx, ry))
                    expected[key] = energy, result
            except BaseException as error:
                failures.append(error)
                dialog.reject()
            else:
                dialog.accept() if create else dialog.reject()

        QTimer.singleShot(0, interact)
        viewer.open_spectrum_subtraction_dialog()
        if failures:
            raise failures[0]
        assert not any(line.get_label() == "_difference_preview" for line in viewer.proc_ax.lines)
        return expected

    run_dialog(group_bg=False, series=False, create=False)
    assert not viewer._difference_sources
    viewer.combo_bg.setCurrentText("Auto")
    viewer.chk_group_bg.setChecked(True)
    viewer.update_plot_processed()
    assert not viewer.calibrate_energy_action.isEnabled()
    assert viewer.subtract_spectra_action.isEnabled()
    expected = run_dialog(group_bg=True, series=True, create=True)
    assert len(viewer._difference_sources) == 2
    for key, origin in viewer._difference_sources.items():
        sample = origin["sample"]
        assert sample["processing"]["group_bg"]
        assert sample["processing"]["i0_applied"]
        assert origin["reference"]["key"] == keys[0]
        assert origin["multiplier"] == 1.3
        for actual, wanted in zip(viewer._get_drawn_processed_xy(key), expected[sample["key"]]):
            np.testing.assert_array_equal(actual, wanted)

    viewer.chk_group_bg.setChecked(False)
    assert viewer.calibrate_energy_action.isEnabled()
    viewer._energy_shifts[keys[1]] = -0.2
    viewer.chk_normalize.setChecked(False)
    differences = list(viewer._difference_sources)
    key = differences[0]
    origin = viewer._difference_sources[key]
    assert origin["sample"]["shift"] == 0.15
    assert len({viewer.curve_display_names[k] for k in differences}) == 2
    for other in viewer.raw_visibility:
        viewer.raw_visibility[other] = other == key
    viewer.update_plot_processed()
    with patch.object(QInputDialog, "getText", return_value=("O K-edge difference", True)):
        viewer._rename_summed_group(key, None, is_difference=True)
    assert viewer._difference_sources[key] is origin
    filename = tmp_path / "difference.csv"
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(filename), "")):
        viewer.export_ascii()
    assert "O K-edge difference" in filename.read_text(encoding="utf-8").splitlines()[0]
    wanted = expected[origin["sample"]["key"]]
    np.testing.assert_array_equal(np.loadtxt(filename, delimiter=",", skiprows=1).T, wanted)
    viewer.pass_to_plotted_no_clear()
    np.testing.assert_array_equal(viewer.original_line_data[key], wanted)
    filename = tmp_path / "plotted-difference.csv"
    viewer.legend_mode_combo.setCurrentText("Entry number")
    with patch.object(viewer, "_csv_save_dialog", return_value=str(filename)):
        viewer.export_ascii_plotted()
    assert "O K-edge difference" in filename.read_text(encoding="utf-8").splitlines()[0]
    np.testing.assert_array_equal(np.loadtxt(filename, delimiter=",", skiprows=1).T, wanted)
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok):
        viewer._delete_summed_group(key)
    assert key not in viewer.plot_data
    assert key not in viewer._difference_sources
    assert all(source in viewer.plot_data for source in keys)


def drop_hdf5_in_raw_data(viewer, path):
    from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PyQt6.QtGui import QDropEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPointF(), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    with patch.object(QMessageBox, "critical", side_effect=AssertionError("HDF5 drop failed")):
        assert viewer.eventFilter(viewer.canvas_raw, event)
        assert event.isAccepted()
        for _ in range(300):
            if viewer.tree.topLevelItemCount():
                break
            QTest.qWait(100)

    root = viewer.tree.topLevelItem(0)
    assert root is not None and root.text(0) == path.name
    return root


def test_raw_library_drop_and_select_y(viewer):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItemIterator

    path = Path(viewer._get_library_path())
    if not path.is_file():
        pytest.skip("Reference library is unavailable in this checkout.")
    before = sha256(path.read_bytes()).digest()
    root = drop_hdf5_in_raw_data(viewer, path)
    spectra = root.child(0)
    assert spectra.text(0) == "spectra"
    spectra.setExpanded(True)
    for i, identifier in enumerate(("000001", "000002")):
        entry = spectra.child(i)
        assert entry.text(0) == identifier
        entry.setExpanded(True)
        assert entry.child(0).text(0) == "x"
        y_item = entry.child(1)
        assert y_item.text(0) == "y"
        y_item.setCheckState(0, Qt.CheckState.Checked)
        assert entry.child(0).checkState(0) == Qt.CheckState.Unchecked
    assert viewer.raw_ax.get_xlabel() == "Photon energy (eV)"
    assert len(viewer.raw_ax.lines) == 2
    names = {}
    rows = QTreeWidgetItemIterator(viewer.raw_tree)
    while rows.value():
        item = rows.value()
        names[item.data(0, Qt.ItemDataRole.UserRole)] = item.text(0)
        rows += 1
    with h5py.File(path, "r") as file:
        for line in viewer.raw_ax.lines:
            y_path = line.dataset_key.split("##", 1)[1]
            np.testing.assert_array_equal(line.get_xdata(), file[y_path].parent["x"][:])
            np.testing.assert_array_equal(line.get_ydata(), file[y_path][:])
            assert line.get_label() == file[y_path].parent.attrs["label"]
            assert names[line.dataset_key] == line.get_label()
    viewer.data_tabs.setCurrentIndex(1)
    assert len(viewer._drawn_spectra()) == 2
    for key, line in viewer._drawn_spectra().items():
        with h5py.File(path, "r") as file:
            group = file[key.split("##", 1)[1]].parent
            np.testing.assert_array_equal(line.get_xdata(), group["x"][:])
            np.testing.assert_array_equal(line.get_ydata(), group["y"][:])
        assert line.get_label() == names[key]
    spectra.child(0).child(1).setCheckState(0, Qt.CheckState.Unchecked)
    assert len(viewer.raw_ax.lines) == 1
    assert viewer.raw_ax.lines[0].dataset_key.endswith("/000002/y")
    viewer.update_plot_processed()
    key, = viewer._drawn_spectra()
    assert viewer._is_reference_spectrum(key)
    viewer.pass_to_plotted_no_clear()
    with h5py.File(path, "r") as file:
        group = file[key.split("##", 1)[1]].parent
        np.testing.assert_array_equal(viewer.original_line_data[key], [group["x"][:], group["y"][:]])
    viewer.legend_mode_combo.setCurrentText("Entry number")
    assert [entry.get_text() for entry in viewer.plotted_ax.get_legend().get_texts()] == [names[key]]
    assert sha256(path.read_bytes()).digest() == before


@pytest.mark.parametrize("accepted", [True, False])
def test_legend_name_dialog_keeps_dragged_location(viewer, accepted):
    from matplotlib.backend_bases import MouseButton, MouseEvent
    from PyQt6.QtWidgets import QApplication, QInputDialog

    viewer._add_reference_curve_to_plotted("reference", [401., 402.], [1., 3.], "Stored title")
    viewer.custom_labels["reference"] = None
    viewer.plotted_lines["reference"].set_label("<select curve name>")
    viewer.update_legend()
    ax = viewer.plotted_ax
    canvas = viewer.canvas_plotted
    legend = ax.get_legend()
    legend.set_loc((0.35, 0.45))
    canvas.draw()

    def click(event_name, x, y, button=MouseButton.LEFT):
        event = MouseEvent(event_name, canvas, x, y, button=button)
        canvas.callbacks.process(event_name, event)

    def corner():
        bounds = ax.get_legend().get_window_extent().transformed(ax.transAxes.inverted())
        return bounds.x0, bounds.y1

    expected = corner()
    text_box = legend.get_texts()[0].get_window_extent()
    x = (text_box.x0 + text_box.x1) / 2
    y = (text_box.y0 + text_box.y1) / 2

    def answer(*args, **kwargs):
        assert not legend._draggable.got_artist
        return "New name", accepted

    with patch.object(QInputDialog, "getText", side_effect=answer) as dialog:
        click("button_press_event", x, y)
        dialog.assert_not_called()
        click("button_release_event", x, y)
        QApplication.processEvents()
        dialog.assert_called_once()

    click("motion_notify_event", x + 60, y - 40, button=None)
    canvas.draw()
    np.testing.assert_allclose(corner(), expected, atol=0.01)
    assert ax.get_legend().get_texts()[0].get_text() == (
        "New name" if accepted else "<select curve name>"
    )


def test_waterfall_controls_preserve_toolbar_zoom(viewer):
    from matplotlib.backend_bases import MouseButton, MouseEvent

    viewer._add_reference_curve_to_plotted("a", [400., 405., 410.], [1., 2., 4.], "A")
    viewer._add_reference_curve_to_plotted("b", [400., 405., 410.], [0., 1., 3.], "B")
    viewer.rescale_plotted_axes()
    ax, toolbar, canvas = viewer.plotted_ax, viewer.toolbar_plotted, viewer.canvas_plotted
    full = ax.get_xlim(), ax.get_ylim()
    toolbar.zoom()
    for event_name, point in (("button_press_event", (0.2, 0.2)),
                              ("button_release_event", (0.7, 0.7))):
        x, y = ax.transAxes.transform(point)
        canvas.callbacks.process(event_name, MouseEvent(event_name, canvas, x, y, MouseButton.LEFT))
    toolbar.zoom()
    zoom = ax.get_xlim(), ax.get_ylim()
    assert zoom != full

    viewer.waterfall_checkbox.setChecked(True)
    assert ax.get_xlim() == zoom[0]
    assert ax.get_ylim() == full[1]
    viewer.waterfall_slider.setValue(40)
    assert ax.get_xlim() == zoom[0]
    assert ax.get_ylim()[1] == pytest.approx(5.6 * 1.05)
    viewer.waterfall_spin.setValue(0.5)
    assert ax.get_xlim() == zoom[0]
    assert ax.get_ylim()[1] == pytest.approx(6 * 1.05)
    assert max(viewer.plotted_lines["a"].get_ydata()) == 6
    viewer.waterfall_checkbox.setChecked(False)
    assert ax.get_xlim() == zoom[0]
    assert ax.get_ylim() == full[1]
    viewer.waterfall_checkbox.setChecked(True)

    toolbar.back()
    assert ax.get_ylim()[1] > 6
    toolbar.forward()
    assert (ax.get_xlim(), ax.get_ylim()) == zoom
    toolbar.home()
    assert ax.get_xlim() == full[0]
    assert ax.get_ylim()[1] > 6
    viewer.waterfall_checkbox.setChecked(False)
    assert (ax.get_xlim(), ax.get_ylim()) == full


def test_raw_pair_names_disambiguate_duplicate_titles(viewer, tmp_path):
    path = str(tmp_path / "pairs.h5")
    with h5py.File(path, "w") as file:
        for name in ("a", "b", "c"):
            file[f"{name}/x"] = [10, 20]
            file[f"{name}/y"] = [1, 2]
            if name != "c":
                file[name].attrs["title"] = "Reference"
    for name in ("a", "b", "c"):
        key = f"{path}##{name}/y"
        viewer.plot_data[key] = np.array([1, 2])
        viewer.raw_visibility[key] = name != "b"
    viewer.update_plot_raw()
    assert viewer._raw_pair_names == {
        f"{path}##a/y": "Reference (pairs.h5:/a)",
        f"{path}##b/y": "Reference (pairs.h5:/b)",
        f"{path}##c/y": "/c",
    }
    assert [line.get_label() for line in viewer.raw_ax.lines] == ["Reference (pairs.h5:/a)", "/c"]
    viewer.update_plot_processed()
    assert not viewer._drawn_spectra()
    assert not viewer._is_reference_spectrum(f"{path}##a/y")


def test_raw_nested_library_drop_and_metadata(viewer, tmp_path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QTreeWidgetItemIterator

    file_path = tmp_path / "nested_reference.h5"
    names = {
        "spectra/Ni/L2,3/NiO/000003": "NiO | TEY | Finazzi et al. 1999",
        "spectra/O/K/NiO/000003": "NiO | TEY | O K-edge",
    }
    disclaimer = "Data usage and provenance.\n" * 60 + "End of disclaimer."
    processing = "Background subtracted and area normalized."
    citation = "Citation and acquisition metadata. " * 50 + "End of citation."
    with h5py.File(file_path, "w") as file:
        file.attrs.update(library_version="1.0", created_with="maxiv_exact")
        file["documentation/disclaimer"] = disclaimer
        file["documentation/processing_method"] = processing
        for index, (path, title) in enumerate(names.items()):
            group = file.create_group(path)
            group.attrs.update(title=title, citation=citation)
            group["x"] = np.array([849.05, 851.42, 855.18]) - index * 320
            group["y"] = [0.03, 0.4 + index, -0.02]
            group["y"].attrs["processing"] = processing
        file["instrument/status_values"] = [7, 8]
    before = sha256(file_path.read_bytes()).digest()
    root = drop_hdf5_in_raw_data(viewer, file_path)

    def find_item(*segments):
        item = root
        for name in segments:
            item.setExpanded(True)
            item = next(item.child(i) for i in range(item.childCount())
                        if item.child(i).text(0) == name)
        return item

    role = Qt.ItemDataRole.CheckStateRole
    for path in names:
        group = find_item(*path.split("/"))
        assert group.data(0, role) is None
        x_item = find_item(*path.split("/"), "x")
        y_item = find_item(*path.split("/"), "y")
        assert x_item.checkState(0) == Qt.CheckState.Unchecked
        y_item.setCheckState(0, Qt.CheckState.Checked)
        assert x_item.checkState(0) == Qt.CheckState.Unchecked

    displayed = {}
    rows = QTreeWidgetItemIterator(viewer.raw_tree)
    while rows.value():
        item = rows.value()
        displayed[item.data(0, Qt.ItemDataRole.UserRole)] = item.text(0)
        rows += 1
    assert viewer.raw_ax.get_xlabel() == "Photon energy (eV)"
    assert len(viewer.raw_ax.lines) == len(names)
    with h5py.File(file_path, "r") as file:
        for line in viewer.raw_ax.lines:
            path = line.dataset_key.split("##", 1)[1].rpartition("/")[0]
            assert line.get_label() == displayed[line.dataset_key] == names[path]
            np.testing.assert_array_equal(line.get_xdata(), file[f"{path}/x"][:])
            np.testing.assert_array_equal(line.get_ydata(), file[f"{path}/y"][:])

    viewer.data_tabs.setCurrentIndex(1)
    assert len(viewer._drawn_spectra()) == len(names)
    for key, line in viewer._drawn_spectra().items():
        path = key.split("##", 1)[1].rpartition("/")[0]
        assert line.get_label() == names[path]
        np.testing.assert_array_equal(line.get_data(), next(
            raw.get_data() for raw in viewer.raw_ax.lines if raw.dataset_key == key
        ))
    key = next(iter(viewer._drawn_spectra()))
    original_x, original_y = (array.copy() for array in viewer._get_drawn_processed_xy(key))
    viewer._energy_shifts[key] = 0.153
    viewer.update_plot_processed()
    np.testing.assert_allclose(viewer._get_drawn_processed_xy(key)[0], original_x + 0.153)
    np.testing.assert_array_equal(viewer._get_drawn_processed_xy(key)[1], original_y)

    finazzi = next(iter(names)).split("/")
    for item, expected in (
        (find_item("documentation", "disclaimer"), disclaimer),
        (find_item("documentation", "processing_method"), processing),
        (find_item(*finazzi, "Attributes", "citation"), citation),
        (find_item(*finazzi, "y", "Attributes", "processing"), processing),
    ):
        assert item.data(0, role) is None
        captured = []

        def inspect_dialog(dialog):
            captured.append(dialog.findChild(QPlainTextEdit).toPlainText())
            return QDialog.DialogCode.Accepted

        with patch.object(QDialog, "exec", inspect_dialog):
            viewer.tree.itemDoubleClicked.emit(item, 0)
        assert captured == [expected]

    find_item("instrument", "status_values").setCheckState(0, Qt.CheckState.Checked)
    standalone = next(line for line in viewer.raw_ax.lines
                      if line.dataset_key.endswith("instrument/status_values"))
    np.testing.assert_array_equal(standalone.get_xdata(), [0, 1])
    assert sha256(file_path.read_bytes()).digest() == before
