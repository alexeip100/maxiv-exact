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


def test_raw_library_drop_and_select_y(viewer):
    from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PyQt6.QtGui import QDropEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox, QTreeWidgetItemIterator

    path = Path(viewer._get_library_path())
    if not path.is_file():
        pytest.skip("Reference library is unavailable in this checkout.")
    before = sha256(path.read_bytes()).digest()
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
    spectra.child(0).child(1).setCheckState(0, Qt.CheckState.Unchecked)
    assert len(viewer.raw_ax.lines) == 1
    assert viewer.raw_ax.lines[0].dataset_key.endswith("/000002/y")
    assert sha256(path.read_bytes()).digest() == before


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
