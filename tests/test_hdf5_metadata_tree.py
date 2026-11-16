from unittest.mock import patch

import h5py
import numpy as np

from maxiv_exact.hdf5_metadata import attribute_preview
from maxiv_exact.hdf5_worker import scan_file


def test_attribute_previews_defer_large_values_and_worker_reads_none(tmp_path):
    path = tmp_path / "metadata.h5"
    with h5py.File(path, "w") as file:
        file.attrs["title"] = "Ni L₂,₃ · Δ"
        data = file.create_dataset("data", data=np.arange(4))
        data.attrs["enabled"] = True
        data.attrs["bytes"] = np.bytes_("Å".encode())
        data.attrs["points"] = np.array([12, 15])
        data.attrs["large"] = np.arange(400)
        assert attribute_preview(data.attrs, "enabled") == "True"
        assert attribute_preview(data.attrs, "bytes") == "Å"
        assert attribute_preview(data.attrs, "points") == "[12 15]"
        with patch.object(h5py.AttributeManager, "__getitem__",
                          side_effect=AssertionError("attribute was loaded eagerly")):
            assert "double-click" in attribute_preview(data.attrs, "large")

    with patch.object(h5py.AttributeManager, "__getitem__",
                      side_effect=AssertionError("worker eagerly read an attribute")):
        payload = scan_file(path)
    assert payload["root_has_attributes"]
    assert payload["root_children"][0]["has_attributes"]
    assert payload["root_children"][0]["kind"] == "dataset"


def test_structure_metadata_and_text_leave_paired_curves_selectable(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QDialog, QPlainTextEdit
    from maxiv_exact.ui import HDF5Viewer

    path = tmp_path / "reference.h5"
    text = "NiO — disclaimer\n\n" + "Please verify against the original publication.\n" * 12
    with h5py.File(path, "w") as file:
        file.attrs["title"] = "NiO Ni L₂,₃"
        spectrum = file.create_group("spectra/000001")
        spectrum.attrs.update(label="NiO test", x_units="eV", note=text)
        spectrum.create_dataset("x", data=[851., 852., 853.])
        spectrum.create_dataset("y", data=[1., 4., 2.]).attrs["mode"] = "TEY"
        file.create_group("Attributes")  # A real object may have the same name.
        doc = file.create_group("documentation")
        doc.create_dataset("disclaimer", data=text, dtype=h5py.string_dtype("utf-8"))
        doc.create_dataset("lines", data=["one", "two"], dtype=h5py.string_dtype("utf-8"))
    app = QApplication.instance() or QApplication([])
    viewer = HDF5Viewer()
    try:
        payload = scan_file(path)
        assert any(row["kind"] == "group" and row["has_children"]
                   for row in payload["root_children"])
        viewer._apply_loaded_hdf5_payload(payload)
        root = viewer.tree.topLevelItem(0)
        assert root.child(0).text(0) == "Attributes"
        assert root.child(0).data(0, Qt.ItemDataRole.UserRole) is not None
        root_metadata = root.child(root.childCount()-1)
        assert root_metadata.child(0).text(0) == "(click to expand)"
        with patch.object(h5py.AttributeManager, "__getitem__",
                          side_effect=AssertionError("expansion read an attribute value")):
            root_metadata.setExpanded(True)
        assert root_metadata.child(0).text(0) == "title"
        viewer.tree.setCurrentItem(root_metadata.child(0))
        assert viewer.scalar_display_raw.text() == "NiO Ni L₂,₃"

        children = {root.child(i).text(0): root.child(i) for i in range(root.childCount())}
        spectra = children["spectra"]
        spectra.setExpanded(True)
        entry = spectra.child(0)
        entry.setExpanded(True)
        y = entry.child(1)
        assert y.text(0) == "y"
        y.setCheckState(0, Qt.CheckState.Checked)
        curve, = viewer.raw_ax.lines
        np.testing.assert_array_equal(curve.get_xdata(), [851., 852., 853.])
        assert curve.get_label() == "NiO test"

        y.child(0).setExpanded(True)
        leaf = y.child(0).child(0)
        assert leaf.text(0) == "mode"
        assert leaf.data(0, Qt.ItemDataRole.UserRole) is None
        assert not (leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        with patch.object(viewer, "_open_h5_read", side_effect=AssertionError("metadata click read a file")):
            viewer.toggle_plot(leaf, 0)
        viewer.tree.itemClicked.emit(leaf, 0)
        assert viewer.scalar_display_raw.text() == "TEY"
        assert list(viewer.raw_ax.lines) == [curve]

        attrs = entry.child(2)
        attrs.setExpanded(True)
        note = next(attrs.child(i) for i in range(attrs.childCount())
                    if attrs.child(i).text(0) == "note")
        viewer.tree.setCurrentItem(note)
        preview = viewer.scalar_display_raw.text()
        assert preview.startswith("NiO — disclaimer") and preview.endswith("…")
        assert len(preview) <= 160
        assert list(viewer.raw_ax.lines) == [curve]
        docs = children["documentation"]
        docs.setExpanded(True)
        disclaimer, lines = docs.child(0), docs.child(1)
        assert disclaimer.text(0) == "disclaimer"
        assert lines.data(0, Qt.ItemDataRole.CheckStateRole) is None
        with patch.object(viewer, "_show_hdf5_text") as show:
            viewer.open_hdf5_tree_text(note, 0)
            show.assert_called_once_with("spectra/000001 · note", text)

        opened = []
        def inspect_dialog():
            dialog = app.activeModalWidget()
            if isinstance(dialog, QDialog):
                editor = dialog.findChild(QPlainTextEdit)
                if editor is not None:
                    opened.append((dialog.windowTitle(), editor.toPlainText(), editor.isReadOnly()))
                dialog.reject()

        QTimer.singleShot(0, inspect_dialog)
        viewer.tree.itemDoubleClicked.emit(disclaimer, 0)
        assert opened == [("documentation/disclaimer", text, True)]

        plain = tmp_path / "plain.h5"
        with h5py.File(plain, "w") as file:
            file.create_dataset("curve", data=np.arange(5))
        viewer._apply_loaded_hdf5_payload(scan_file(plain))
        assert viewer.tree.topLevelItem(1).childCount() == 1
        assert viewer.tree.topLevelItem(1).child(0).text(0) == "curve"
    finally:
        viewer.close()
        app.processEvents()
