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


def test_literature_groups_keep_provenance_and_published_axis(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from maxiv_exact.ui import HDF5Viewer

    path = tmp_path / "reference.h5"
    entry_path = "spectra/Cu/L2,3/Cu/000036"
    with h5py.File(path, "w") as file:
        file.attrs.update(database_role="master", master_database_version="2.0")
        spectrum = file.create_group(entry_path)
        spectrum.attrs.update(
            label="Cu metal", x_units="eV", electronic_environment="Metallic Cu",
            authors="Yang et al.", year=2022, doi="10.example/cu",
            figure="Figure S6(a), red trace", proposed_energy_shift_eV=-1.0,
            source_pdf_sha256="pdfhash",
        )
        spectrum.create_dataset("x", data=[930., 931., 932.])
        spectrum.create_dataset("y", data=[1., 2., 4.])
        file.copy(spectrum, spectrum.parent, name="000037")
        spectrum.parent["000037"].attrs["proposed_energy_shift_eV"] = 0.0

    def child(parent, name):
        return next(parent.child(i) for i in range(parent.childCount())
                    if parent.child(i).text(0) == name)

    app = QApplication.instance() or QApplication([])
    viewer = HDF5Viewer()
    try:
        viewer._apply_loaded_hdf5_payload(scan_file(path))
        item = viewer.tree.topLevelItem(0)
        for name in entry_path.split("/"):
            item.setExpanded(True)
            item = child(item, name)
        item.setExpanded(True)
        attrs = child(item, "Attributes")
        attrs.setExpanded(True)
        identify = child(attrs, "Identify spectrum")
        source = child(attrs, "Source")
        processing = child(attrs, "Digitization and processing")
        assert identify.isExpanded() and not source.isExpanded() and not processing.isExpanded()

        shift = child(identify, "Curator-proposed energy shift")
        viewer.tree.setCurrentItem(shift)
        assert viewer.scalar_display_raw.text() == "−1.0 eV · currently off"
        assert shift.data(0, Qt.ItemDataRole.UserRole) is None

        source.setExpanded(True)
        with patch.object(viewer, "_show_hdf5_text") as show:
            viewer.open_hdf5_tree_text(child(source, "Citation"), 0)
        assert show.call_args.args[1] == "Yang et al. (2022)\nDOI: 10.example/cu"
        assert viewer._read_hdf5_tree_text(child(source, "Figure / panel / trace"))[1] == "Figure S6(a), red trace"
        assert viewer._read_hdf5_tree_text(child(processing, "source_pdf_sha256"))[1] == "pdfhash"

        child(item, "y").setCheckState(0, Qt.CheckState.Checked)
        curve, = viewer.raw_ax.lines
        np.testing.assert_array_equal(curve.get_xdata(), [930., 931., 932.])

        zero = child(item.parent(), "000037")
        zero.setExpanded(True)
        zero_attrs = child(zero, "Attributes")
        zero_attrs.setExpanded(True)
        assert child(zero_attrs, "Identify spectrum").childCount() == 1
    finally:
        viewer.close()
        app.processEvents()
