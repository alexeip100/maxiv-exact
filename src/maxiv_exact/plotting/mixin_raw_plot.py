"""Phase 4: Raw plotting + Plotted-tab passing helpers.

This module contains the parts of the original PlottingMixin that primarily deal
with:
  - selecting datasets from the raw tree
  - plotting raw curves
  - passing curves to the Plotted Data tab

The code is moved with minimal changes to preserve behaviour.
"""

from __future__ import annotations

from datetime import datetime

import h5py
import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidgetItem, QMessageBox

from ..data import lookup_energy
from .. import processing

try:
    from ..widgets.curve_item import CurveListItemWidget
except Exception:  # pragma: no cover
    CurveListItemWidget = None


class RawPlotMixin:
    """Mixin implementing raw plotting and passing curves to Plotted Data."""

    # ------------ Plotted tab helpers ------------
    def pass_to_plotted_no_clear(self):
        if not getattr(self, "plot_data", None):
            return

        visible_keys = [key for key in self.plot_data if self.raw_visibility.get(key, False)]
        if self.chk_sum.isChecked():
            if not visible_keys:
                return
            key = visible_keys[0]
        else:
            if len(visible_keys) != 1:
                # Multi-pass is allowed only for group Auto BG with subtraction enabled.
                allow_multi = False
                try:
                    mode = str(getattr(self, "combo_bg").currentText()) if hasattr(self, "combo_bg") else ""
                    cb = getattr(self, "chk_group_bg", None)
                    if (
                        len(visible_keys) >= 2
                        and str(mode) in ("Automatic", "Auto")
                        and cb is not None
                        and cb.isEnabled()
                        and cb.isChecked()
                        and getattr(self, "chk_show_without_bg", None) is not None
                        and self.chk_show_without_bg.isChecked()
                        and (not self.chk_sum.isChecked())
                    ):
                        allow_multi = True
                except Exception:
                    allow_multi = False

                if not allow_multi:
                    QMessageBox.warning(self, "Warning", "Please select exactly one dataset, or enable 'Sum'.")
                    return

                # --- Multi-pass: pass all selected curves at once ---
                try:
                    deg = int(self.combo_poly.currentText())
                except Exception:
                    deg = 2
                try:
                    pre = float(self.spin_preedge.value()) / 100.0
                except Exception:
                    pre = 0.12

                # Post-normalization mode
                norm_mode = "None"
                try:
                    if hasattr(self, "combo_post_norm"):
                        # In Group BG mode the combobox is disabled but still reflects the enforced mode ("Area").
                        if (getattr(self, "chk_group_bg", None) is not None and self.chk_group_bg.isChecked()):
                            norm_mode = str(self.combo_post_norm.currentText())
                        elif self.combo_post_norm.isEnabled():
                            norm_mode = str(self.combo_post_norm.currentText())
                except Exception:
                    norm_mode = "None"

                # Group backgrounds (fallback handled inside)
                _x_common, bgs = self._compute_group_auto_backgrounds(visible_keys, deg=deg, pre_edge_percent=pre)
                if bgs is None:
                    bgs = {}

                # If Area post-normalization is active, equalize the *area-normalized jump* across the group
                # by adding a zero-area tilt term to the per-spectrum background.
                try:
                    m = str(norm_mode).strip().lower()
                    _equalize_jump = m in ("area", "area=1")
                except Exception:
                    _equalize_jump = False

                if _equalize_jump and len(visible_keys) >= 2:
                    # Coupled group constraint for Area post-normalization:
                    # - pre-edge baseline after BG subtraction is set to 0 for each spectrum
                    # - jump after BG subtraction and Area-normalization is equalized across the group
                    # - optionally, pre-edge slope after BG subtraction is also matched across the group
                    try:
                        items_simple = {}
                        for key in visible_keys:
                            parts = key.split("##", 1)
                            if len(parts) != 2:
                                continue
                            abs_path, hdf5_path = parts
                            parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                            y_data = self.plot_data.get(key)
                            if y_data is None:
                                continue
                            x_data = lookup_energy(self, abs_path, parent, len(y_data))
                            y_proc = processing.apply_normalization(self, abs_path, parent, y_data)
                            x_arr = np.asarray(x_data, dtype=float).ravel()
                            y_arr = np.asarray(y_proc, dtype=float).ravel()
                            mlen = min(int(x_arr.size), int(y_arr.size))
                            if mlen < 3:
                                continue
                            x_use = x_arr[:mlen]
                            y_use = y_arr[:mlen]
                            bg = bgs.get(key)
                            if bg is None:
                                bg = self._apply_automatic_bg_new(x_use, y_use, deg=deg, pre_edge_percent=pre, do_plot=False)
                            bg = np.asarray(bg, dtype=float).ravel()[:mlen]
                            items_simple[key] = (x_use, y_use, bg)

                        _match_slope = False
                        try:
                            scb = getattr(self, "chk_group_bg_slope", None)
                            if scb is not None and scb.isEnabled() and scb.isChecked():
                                _match_slope = True
                        except Exception:
                            _match_slope = False

                        adjusted, msg = self._group_equalize_area_jump_and_zero_preedge(
                            items_simple, pre=float(pre), match_preedge_slope=bool(_match_slope)
                        )
                        for k, (_x_u, _y_u, bg_u) in adjusted.items():
                            bgs[k] = bg_u
                        if msg:
                            try:
                                self.statusBar().showMessage(msg, 6000)
                            except Exception:
                                pass
                    except Exception:
                        pass

                added = 0
                skipped = 0

                for key in visible_keys:
                    storage_key = key
                    if storage_key in self.plotted_curves:
                        skipped += 1
                        continue

                    # Build x/y (normalized, bg-subtracted, post-normalized)
                    parts = key.split("##", 1)
                    if len(parts) != 2:
                        skipped += 1
                        continue
                    abs_path, hdf5_path = parts
                    parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                    y_data = self.plot_data.get(key)
                    if y_data is None:
                        skipped += 1
                        continue
                    main_x, main_y = self._get_drawn_processed_xy(key)
                    if main_x is None or main_y is None:
                        x_data = lookup_energy(self, abs_path, parent, len(y_data))
                        y_proc = processing.apply_normalization(self, abs_path, parent, y_data)
                        mlen = min(len(x_data), len(y_proc))
                        if mlen <= 1:
                            skipped += 1
                            continue
                        main_x = np.asarray(x_data[:mlen], dtype=float).ravel()
                        main_y = np.asarray(y_proc[:mlen], dtype=float).ravel()

                        bg = bgs.get(key)
                        if bg is None:
                            bg = self._apply_automatic_bg_new(main_x, main_y, deg=deg, pre_edge_percent=pre, do_plot=False)
                        bg = np.asarray(bg, dtype=float).ravel()[:mlen]
                        subtracted = main_y - bg
                        try:
                            from .. import processing as _p

                            subtracted = _p._proc_safe_post_normalize(self, main_x, subtracted, norm_mode)
                        except Exception:
                            pass
                        main_y = subtracted

                    # Build label + metadata
                    source_file = abs_path
                    source_entry = hdf5_path
                    detector_name = ""
                    path_parts = hdf5_path.split("/")
                    if len(path_parts) >= 3 and path_parts[1] == "measurement":
                        entry = path_parts[0]
                        channel_name = path_parts[-1]
                        origin_label = f"{entry}: {channel_name}"
                        detector_name = channel_name
                    else:
                        origin_label = hdf5_path
                        detector_name = path_parts[-1] if path_parts else hdf5_path

                    metadata_parts = []
                    try:
                        nm = str(norm_mode).lower()
                        if nm and nm != "none":
                            metadata_parts.append(nm)
                    except Exception:
                        pass
                    if self.chk_normalize.isChecked():
                        metadata_parts.append("normalized")
                    metadata_parts.append("bg subtracted")
                    if metadata_parts:
                        origin_label += " (" + ", ".join(metadata_parts) + ")"

                    if not hasattr(self, "plotted_metadata") or not isinstance(getattr(self, "plotted_metadata", None), dict):
                        self.plotted_metadata = {}
                    self.plotted_metadata[storage_key] = {
                        "detector": detector_name or "",
                        "source_file": source_file or "",
                        "source_entry": source_entry or "",
                        "post_normalization": norm_mode,
                        "is_reference": False,
                    }

                    # Add to plot + list
                    if storage_key not in self.custom_labels:
                        self.custom_labels[storage_key] = None

                    # `custom_labels` holds ONLY user-defined legend labels. The plotted list should
                    # show the intrinsic curve name (e.g. summed-group name) when available.
                    _cl = (getattr(self, "custom_labels", {}) or {}).get(storage_key)
                    _cl = str(_cl).strip() if isinstance(_cl, str) else ""
                    cdn = (getattr(self, "curve_display_names", {}) or {})
                    intrinsic_label = str(cdn.get(storage_key)).strip() if storage_key in cdn else ""
                    display_label = intrinsic_label if intrinsic_label else origin_label

                    # Use an integer default linewidth (2) so users can return to the initial look
                    # using the simple size control (which only allows integers).
                    line_label = _cl if _cl else "<select curve name>"
                    line, = self.plotted_ax.plot(main_x, main_y, label=line_label, linewidth=2.0)
                    self.plotted_curves.add(storage_key)
                    self.plotted_lines[storage_key] = line
                    self.original_line_data[storage_key] = (np.asarray(main_x).copy(), np.asarray(main_y).copy())

                    item = QListWidgetItem()
                    try:
                        item.setData(Qt.ItemDataRole.UserRole, storage_key)
                    except Exception:
                        pass

                    if CurveListItemWidget:
                        widget = CurveListItemWidget(display_label, line.get_color(), storage_key)
                        widget.colorChanged.connect(self.change_curve_color)
                        widget.visibilityChanged.connect(self.change_curve_visibility)
                        widget.styleChanged.connect(self.change_curve_style)
                        if hasattr(widget, "removeRequested"):
                            widget.removeRequested.connect(self.on_curve_remove_requested)
                        if hasattr(widget, "addToLibraryRequested"):
                            try:
                                self.on_add_to_library_requested
                            except AttributeError:
                                pass
                            else:
                                widget.addToLibraryRequested.connect(self.on_add_to_library_requested)
                        item.setSizeHint(widget.sizeHint())
                        self.plotted_list.addItem(item)
                        self.plotted_list.setItemWidget(item, widget)
                    else:
                        item.setText(display_label)
                        self.plotted_list.addItem(item)

                    added += 1

                if added:
                    try:
                        self.data_tabs.setCurrentIndex(2)
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "rescale_plotted_axes"):
                            self.rescale_plotted_axes()
                        else:
                            self._apply_grid_mode()
                    except Exception:
                        pass
                    self.update_legend()

                if skipped and added == 0:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "No new curves were passed (they may already be present in Plotted Data).",
                    )
                return

            key = visible_keys[0]

        # Use synthetic key for summed curve so it doesn't collide with first component
        storage_key = f"SUMMED#{getattr(self, '_sum_serial', 0) + 1}" if self.chk_sum.isChecked() else key

        if storage_key in self.plotted_curves:
            QMessageBox.warning(self, "Warning", "This curve is already passed for plotting.")
            return

        main_x, main_y = self.compute_main_curve()
        if main_x is None or main_y is None:
            return

        used_drawn_processed = False
        try:
            if (not self.chk_sum.isChecked()) and hasattr(self, "data_tabs") and int(self.data_tabs.currentIndex()) == 1:
                cb = getattr(self, "chk_group_bg", None)
                mode = str(getattr(self, "combo_bg").currentText()) if hasattr(self, "combo_bg") else ""
                if cb is not None and cb.isEnabled() and cb.isChecked() and str(mode) in ("Automatic", "Auto"):
                    dx, dy = self._get_drawn_processed_xy(key)
                    if dx is not None and dy is not None:
                        main_x, main_y = dx, dy
                        used_drawn_processed = True
        except Exception:
            used_drawn_processed = False

        # Post-normalization mode (used for metadata and potential library export)
        norm_mode = "None"
        try:
            if hasattr(self, "combo_post_norm") and self.combo_post_norm.isEnabled():
                norm_mode = str(self.combo_post_norm.currentText())
        except Exception:
            norm_mode = "None"

        bg_subtracted = False
        if (not used_drawn_processed) and self.chk_show_without_bg.isChecked():
            background = self._compute_background(main_x, main_y)
            subtracted = main_y - background
            try:
                from .. import processing as _p

                subtracted = _p._proc_safe_post_normalize(self, main_x, subtracted, norm_mode)
            except Exception:
                pass
            main_y = subtracted
            bg_subtracted = True

        # Parse the key into source file / entry information
        source_file = ""
        source_entry = ""
        detector_name = ""
        parts = key.split("##", 1)
        if self.chk_sum.isChecked():
            origin_label = "Summed Curve"
        else:
            if len(parts) == 2:
                source_file = parts[0]
                path = parts[1]
                source_entry = path
                # Typical path looks like "entryXXXX/measurement/<channel_name>".
                # We want to drop the redundant "measurement" and show
                # "entryXXXX: <channel_name>" in the Plotted Data list.
                path_parts = path.split("/")
                if len(path_parts) >= 3 and path_parts[1] == "measurement":
                    entry = path_parts[0]
                    channel_name = path_parts[-1]
                    origin_label = f"{entry}: {channel_name}"
                    detector_name = channel_name
                else:
                    origin_label = path
                    detector_name = path_parts[-1] if path_parts else path
            else:
                origin_label = key

        metadata_parts = []
        if bg_subtracted and hasattr(self, "combo_post_norm") and self.combo_post_norm.isEnabled():
            try:
                nm = self.combo_post_norm.currentText().lower()
                if nm != "none":
                    metadata_parts.append(nm)
            except Exception:
                pass
        if self.chk_normalize.isChecked():
            metadata_parts.append("normalized")
        if self.chk_sum.isChecked():
            metadata_parts.append("summed")
        if bg_subtracted:
            metadata_parts.append("bg subtracted")
        if metadata_parts:
            origin_label += " (" + ", ".join(metadata_parts) + ")"

        # Metadata bookkeeping for potential library export
        if not hasattr(self, "plotted_metadata") or not isinstance(getattr(self, "plotted_metadata", None), dict):
            self.plotted_metadata = {}
        self.plotted_metadata[storage_key] = {
            "detector": detector_name or "",
            "source_file": source_file or "",
            "source_entry": source_entry or "",
            "post_normalization": norm_mode,
            "is_reference": False,
        }

        # Add the curve to the plotted axes and list
        if storage_key not in self.custom_labels:
            self.custom_labels[storage_key] = None

        # `custom_labels` holds ONLY user-defined legend labels. The plotted list should
        # show the intrinsic curve name (e.g. summed-group name) when available.
        _cl = (getattr(self, "custom_labels", {}) or {}).get(storage_key)
        _cl = str(_cl).strip() if isinstance(_cl, str) else ""
        cdn = (getattr(self, "curve_display_names", {}) or {})
        intrinsic_label = str(cdn.get(storage_key)).strip() if storage_key in cdn else ""
        display_label = intrinsic_label if intrinsic_label else origin_label

        # Use an integer default linewidth (2) so users can return to the initial look
        # using the simple size control (which only allows integers).
        line_label = _cl if _cl else "<select curve name>"
        line, = self.plotted_ax.plot(main_x, main_y, label=line_label, linewidth=2.0)
        self.plotted_curves.add(storage_key)
        self.plotted_lines[storage_key] = line

        # Store original data so we can revert it for Waterfall
        self.original_line_data[storage_key] = (np.asarray(main_x).copy(), np.asarray(main_y).copy())

        item = QListWidgetItem()
        # Store curve key in the item for robust reordering
        try:
            item.setData(Qt.ItemDataRole.UserRole, storage_key)
        except Exception:
            pass
            pass

        # Avoid circular import with UI; gracefully degrade if custom widget is unavailable.
        if CurveListItemWidget:
            widget = CurveListItemWidget(display_label, line.get_color(), storage_key)
            widget.colorChanged.connect(self.change_curve_color)
            widget.visibilityChanged.connect(self.change_curve_visibility)
            widget.styleChanged.connect(self.change_curve_style)
            # Allow removing a plotted curve from the list/plot.
            if hasattr(widget, "removeRequested"):
                widget.removeRequested.connect(self.on_curve_remove_requested)
            # Allow adding the curve to the reference library, if LibraryMixin is present.
            if hasattr(widget, "addToLibraryRequested"):
                try:
                    self.on_add_to_library_requested  # type: ignore[attr-defined]
                except AttributeError:
                    pass
                else:
                    widget.addToLibraryRequested.connect(self.on_add_to_library_requested)
            item.setSizeHint(widget.sizeHint())
            self.plotted_list.addItem(item)
            self.plotted_list.setItemWidget(item, widget)
        else:
            item.setText(display_label)
            self.plotted_list.addItem(item)

        self.data_tabs.setCurrentIndex(2)
        try:
            if hasattr(self, "rescale_plotted_axes"):
                self.rescale_plotted_axes()
            else:
                self._apply_grid_mode()
        except Exception:
            pass
        self.update_legend()
        if self.chk_sum.isChecked():
            self._sum_serial = getattr(self, "_sum_serial", 0) + 1

    def _add_reference_curve_to_plotted(self, storage_key, x, y, label, meta=None):
        """Add a reference spectrum (from the library) directly to Plotted Data."""
        try:
            import numpy as _np
        except Exception:
            import numpy as _np

        if not hasattr(self, "plotted_curves"):
            self.plotted_curves = set()
        if not hasattr(self, "plotted_lines"):
            self.plotted_lines = {}
        if not hasattr(self, "original_line_data"):
            self.original_line_data = {}
        if not hasattr(self, "custom_labels"):
            self.custom_labels = {}
        if not hasattr(self, "plotted_list") or self.plotted_list is None:
            return

        # Normalize arrays
        try:
            x_arr = _np.asarray(x).ravel()
            y_arr = _np.asarray(y).ravel()
        except Exception:
            return
        if x_arr.size == 0 or y_arr.size == 0:
            return
        n = min(int(x_arr.size), int(y_arr.size))
        x_arr = x_arr[:n]
        y_arr = y_arr[:n]

        # Register curve
        self.custom_labels[storage_key] = str(label)
        # Reference curves use the same default linewidth as regular plotted curves.
        line, = self.plotted_ax.plot(x_arr, y_arr, label=str(label), linewidth=2.0)
        self.plotted_curves.add(storage_key)
        self.plotted_lines[storage_key] = line
        self.original_line_data[storage_key] = (x_arr.copy(), y_arr.copy())

        # Metadata bookkeeping (mark as reference)
        if not hasattr(self, "plotted_metadata") or not isinstance(getattr(self, "plotted_metadata", None), dict):
            self.plotted_metadata = {}
        m = dict(meta or {})
        m.setdefault("detector", str(m.get("detector", "") or ""))
        m.setdefault("source_file", str(m.get("source_file", "") or ""))
        m.setdefault("source_entry", str(m.get("source_entry", "") or ""))
        m.setdefault("post_normalization", str(m.get("post_normalization", "") or "None"))
        m["is_reference"] = bool(m.get("is_reference", True))
        m["is_imported"] = bool(m.get("is_imported", False))
        self.plotted_metadata[storage_key] = m

        # Create list item with curve controls
        item = QListWidgetItem()
        # Store curve key in the item for robust reordering
        try:
            item.setData(Qt.ItemDataRole.UserRole, storage_key)
        except Exception:
            pass

        origin_label = str(label)
        if CurveListItemWidget:
            widget = CurveListItemWidget(origin_label, line.get_color(), storage_key)
            widget.colorChanged.connect(self.change_curve_color)
            widget.visibilityChanged.connect(self.change_curve_visibility)
            widget.styleChanged.connect(self.change_curve_style)
            if hasattr(widget, "removeRequested"):
                widget.removeRequested.connect(self.on_curve_remove_requested)
            # Reference curves should not be added to library again
            if hasattr(widget, "set_add_to_library_enabled"):
                widget.set_add_to_library_enabled(False)
            item.setSizeHint(widget.sizeHint())
            self.plotted_list.addItem(item)
            self.plotted_list.setItemWidget(item, widget)
        else:
            item.setText(origin_label)
            self.plotted_list.addItem(item)

        # Ensure Plotted Data tab is visible and legend updated
        try:
            self.data_tabs.setCurrentIndex(2)
        except Exception:
            pass
        try:
            self._apply_grid_mode()
        except Exception:
            pass
        try:
            self.update_legend()
        except Exception:
            pass

    def confirm_clear_plotted_data(self):
        """Ask before clearing the complete Plotted Data composition."""
        try:
            if self.plotted_list.count() == 0:
                return
        except Exception:
            try:
                if not getattr(self, "plotted_curves", None):
                    return
            except Exception:
                pass

        answer = QMessageBox.question(
            self,
            "Clear plotted curves",
            "Do you want to clear all plotted curves?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Ok:
            self.clear_plotted_data()

    def clear_plotted_data(self):
        """Clear the Plotted Data axes/list while preserving UI state.

        Two important UX details:
        - Keep the current grid density setting ("None/Coarse/Fine/Finest").
        - If the Annotation checkbox is enabled, recreate the annotation box
          after clearing the axes (ax.clear() removes the artist).
        """

        # Preserve grid mode text (if available)
        grid_mode = None
        try:
            combo = getattr(self, 'grid_mode_combo', None)
            if combo is not None:
                grid_mode = combo.currentText()
        except Exception:
            grid_mode = None

        # Preserve whether the annotation box should be visible
        show_annotation = False
        try:
            chk = getattr(self, 'chk_show_annotation', None)
            if chk is not None:
                show_annotation = bool(chk.isChecked())
        except Exception:
            show_annotation = False

        # Clear axes and restore labels
        self.plotted_ax.clear()
        self.plotted_ax.set_xlabel("Photon energy (eV)")
        self.plotted_ax.set_ylabel("XAS intensity (arb. units)")

        # Restore grid setting (ax.clear resets it)
        try:
            self._apply_grid_mode(grid_mode)
        except Exception:
            pass

        # Recreate annotation box if needed (ax.clear removes the artist)
        if show_annotation:
            try:
                # Force recreation on the cleared axes
                self.plotted_annotation = None
            except Exception:
                pass
            try:
                self.toggle_plotted_annotation(True)
            except Exception:
                pass

        self.canvas_plotted_fig.tight_layout()
        self.canvas_plotted.draw()
        self.plotted_curves.clear()
        self.plotted_lines.clear()
        self.plotted_list.clear()
        # Do NOT blindly clear custom labels here: summed curves rely on their
        # user-given names being preserved across clearing/re-adding in the
        # Plotted Data tab. Keep labels for synthetic "__SUM__" curves and
        # clear everything else.
        try:
            def _is_sum_key(k: str) -> bool:
                parts = str(k).split("##", 1)
                if len(parts) != 2:
                    return False
                try:
                    _abs, h5 = parts
                    return str(h5).lstrip("/").startswith("__SUM__/")
                except Exception:
                    return False

            keep = {}
            for k, v in (getattr(self, "custom_labels", {}) or {}).items():
                if _is_sum_key(k):
                    keep[k] = v
            self.custom_labels.clear()
            self.custom_labels.update(keep)
        except Exception:
            try:
                self.custom_labels.clear()
            except Exception:
                pass
        self.original_line_data.clear()
        # Keep Waterfall baseline storage in sync
        try:
            self._waterfall_original_data.clear()
        except Exception:
            pass
        try:
            self.update_legend()
        except Exception:
            pass
        try:
            self.recompute_waterfall_layout()
        except Exception:
            pass

    # ------------ Left tree interactions ------------
    def toggle_plot(self, item, column):
        if column != 0:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        # UserRole payload must be a (abs_path, hdf5_path) tuple
        if not isinstance(data, tuple) or len(data) != 2:
            return
        abs_path, hdf5_path = data
        hdf5_path = self._normalize_hdf5_key(hdf5_path)
        # Prefer datasets from the "measurement" group only; ignore "plot_1" and other derived groups.
        norm = "/" + str(hdf5_path).strip("/") + "/"
        if "/measurement/" not in norm:
            try:
                from PyQt6.QtWidgets import QMessageBox as _QMessageBox

                _QMessageBox.information(
                    self,
                    "Ignoring non-measurement data",
                    f'The dataset “{hdf5_path}” is not under a "/measurement/" group and will be ignored.',
                )
            except Exception:
                pass
            try:
                item.setCheckState(0, Qt.CheckState.Unchecked)
            except Exception:
                pass
            return
        if abs_path not in self.hdf5_files:
            return

        try:
            with self._open_h5_read(abs_path) as f:
                if hdf5_path and hdf5_path in f:
                    ds_obj = f[hdf5_path]
                    if isinstance(ds_obj, h5py.Dataset) and ds_obj.ndim == 1:
                        if getattr(ds_obj, "size", 0) == 0:
                            QMessageBox.warning(
                                self,
                                "Empty dataset",
                                f'The dataset “{hdf5_path}” contains no data and will be ignored.',
                            )
                            item.setCheckState(0, Qt.CheckState.Unchecked)
                            return

                        combined_label = f"{abs_path}##{hdf5_path}"
                        if item.checkState(0) == Qt.CheckState.Checked:
                            y = ds_obj[()]
                            try:
                                y = np.asarray(y)
                            except Exception:
                                QMessageBox.warning(
                                    self,
                                    "Invalid dataset",
                                    f'The dataset “{hdf5_path}” could not be read as a 1D array and will be ignored.',
                                )
                                item.setCheckState(0, Qt.CheckState.Unchecked)
                                return
                            if y.ndim != 1 or y.size == 0:
                                QMessageBox.warning(
                                    self,
                                    "Invalid dataset",
                                    f'The dataset “{hdf5_path}” is not a non-empty 1D array and will be ignored.',
                                )
                                item.setCheckState(0, Qt.CheckState.Unchecked)
                                return
                            self.plot_data[combined_label] = y
                            self.raw_visibility[combined_label] = True
                            # Track source so bulk toggles don't accidentally remove
                            # manually selected curves.
                            try:
                                self._add_raw_key_source(combined_label, "tree")
                            except Exception:
                                pass
                        else:
                            try:
                                should_delete = self._remove_raw_key_source(combined_label, "tree")
                            except Exception:
                                should_delete = True
                            if should_delete:
                                self.plot_data.pop(combined_label, None)
                                self.raw_visibility.pop(combined_label, None)
                            else:
                                # Still requested by another selection mechanism.
                                self.raw_visibility[combined_label] = True

            self._filter_empty_plot_data()
            self.update_plot_raw()
            self.update_plot_processed()
            self.update_pass_button_state()

        except Exception:
            pass

    def display_data(self, item, column):
        # Update scalar/text display for the *current* tree item (mouse or keyboard),
        # and expand groups instead of trying to display them.
        if self.data_tabs.currentIndex() != 0:
            return
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        abs_path, hdf5_path = data
        hdf5_path = self._normalize_hdf5_key(hdf5_path)

        if abs_path not in self.hdf5_files:
            return

        try:
            # Selecting the file root ("") or any group should just expand it.
            if hdf5_path in (None, ""):
                try:
                    item.setExpanded(True)
                    # Populate children immediately for keyboard navigation.
                    if item.childCount() == 1 and item.child(0).text(0) == "(click to expand)":
                        self.load_subtree(item)
                except Exception:
                    pass
                try:
                    self.scalar_display_raw.setText("")
                except Exception:
                    pass
                return

            with self._open_h5_read(abs_path) as f:
                if hdf5_path not in f:
                    return
                obj = f[hdf5_path]
                if isinstance(obj, h5py.Group):
                    try:
                        item.setExpanded(True)
                        if item.childCount() == 1 and item.child(0).text(0) == "(click to expand)":
                            self.load_subtree(item)
                    except Exception:
                        pass
                    try:
                        self.scalar_display_raw.setText("")
                    except Exception:
                        pass
                    return

                # Dataset
                arr = obj[()]

            # Scalars and 1D
            if isinstance(arr, np.ndarray) and arr.ndim in (0, 1):
                if arr.ndim == 0:
                    arr = arr.item()
                # For 1D, nothing here; the plot is handled elsewhere
                return

            # Bytes → str
            if isinstance(arr, bytes):
                arr = arr.decode("utf-8")

            # Try datetime formatting if string looks like ISO-ish
            if isinstance(arr, str) and "T" in arr and "-" in arr:
                try:
                    dt_obj = datetime.strptime(arr, "%Y-%m-%dT%H:%M:%S.%f")
                    arr = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            self.scalar_display_raw.setText(str(arr) if not isinstance(arr, float) else f"{arr:.2f}")

        except Exception as e:
            self.scalar_display_raw.setText(f"Error displaying data: {e}")

    # ------------ Raw plotting ------------
    def plot_curves(self, ax):
        ax.clear()
        for combined_label, y_data in list(getattr(self, "plot_data", {}).items()):
            try:
                if not self.raw_visibility.get(combined_label, True):
                    continue

                parts = str(combined_label).split("##", 1)
                if len(parts) != 2:
                    continue
                abs_path, hdf5_path = parts
                parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""

                # Robustly coerce y to a 1D array
                y_arr = np.asarray(y_data)
                if y_arr.ndim != 1 or y_arr.size == 0:
                    continue

                # Lookup energy axis; pass point count without calling len() on scalars
                x_data = lookup_energy(self, abs_path, parent, int(y_arr.size))
                x_arr = np.asarray(x_data)
                if x_arr.ndim != 1 or x_arr.size == 0:
                    continue

                mlen = min(int(x_arr.size), int(y_arr.size))
                if mlen <= 0:
                    continue
                x_use = x_arr[:mlen]
                y_use = y_arr[:mlen]

                if x_use.size == 0:
                    continue

                line, = ax.plot(
                    x_use,
                    y_use,
                    label=self.shorten_label(hdf5_path),
                    color=self._get_persistent_curve_color(combined_label),
                )
                line.dataset_key = combined_label
            except Exception:
                # Skip problematic datasets but continue plotting the rest
                continue
        ax.set_xlabel("Photon energy (eV)")

    def update_plot_raw(self):
        try:
            self._filter_empty_plot_data()
            self.plot_curves(self.raw_ax)
            self.canvas_raw_fig.tight_layout()
            self.canvas_raw.draw()
            self.update_raw_tree()
        except Exception as e:
            print("update_plot_raw error:", e)
