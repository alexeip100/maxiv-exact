"""UI tree view logic (raw/proc curve trees).

This mixin hosts QTreeWidget population + item-changed handling and related helpers.
It is intentionally kept separate from plotting logic to reduce coupling.
"""

from __future__ import annotations

import numpy as np

from .utils.sorting import parse_entry_number

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QColor, QIcon
from PyQt5.QtWidgets import QTreeWidgetItem


def _qcolor_from_curve_color(color):
    """Convert Matplotlib/Qt color values to a valid QColor.

    Matplotlib may return named/hex strings, QColor objects, or RGB/RGBA
    tuples (including NumPy scalar values).  Passing a tuple directly to
    QColor is not supported by PyQt5 on all platforms.
    """
    if isinstance(color, QColor):
        return QColor(color)
    if isinstance(color, str):
        qcolor = QColor(color)
        return qcolor if qcolor.isValid() else QColor()
    if isinstance(color, (tuple, list, np.ndarray)):
        try:
            values = [float(v) for v in color]
        except Exception:
            return QColor()
        if len(values) not in (3, 4):
            return QColor()
        try:
            # Matplotlib normally uses 0..1 floats, but also accept 0..255 RGB(A).
            if all(0.0 <= v <= 1.0 for v in values):
                if len(values) == 3:
                    return QColor.fromRgbF(values[0], values[1], values[2])
                return QColor.fromRgbF(values[0], values[1], values[2], values[3])
            ints = [max(0, min(255, int(round(v)))) for v in values]
            if len(ints) == 3:
                return QColor(ints[0], ints[1], ints[2])
            return QColor(ints[0], ints[1], ints[2], ints[3])
        except Exception:
            return QColor()
    try:
        qcolor = QColor(color)
        return qcolor if qcolor.isValid() else QColor()
    except Exception:
        return QColor()


class TreeViewMixin:
    """Mixin for managing the Raw/Processed curve QTreeWidgets."""

    def recursive_uncheck(self, item, col):
        if not item:
            return
        if item.data(col, Qt.UserRole):
            item.setCheckState(col, Qt.Unchecked)
        for i in range(item.childCount()):
            self.recursive_uncheck(item.child(i), col)

    # ------------ Tabs & right-panel trees ------------

    def group_datasets(self):
        """Group currently loaded 1D datasets into "regions" by scan start/end energies.

        Regions are determined ONLY by the start/end of the energy axis (x).
        Small numerical differences (< 0.01 eV) in start/end must not split regions.

        Notes:
        - NaNs in the signal (y) must not influence region limits.
        - This implementation is order-independent (uses union-find clustering),
          avoiding the "greedy clustering" pitfall where earlier region references
          can drift and prevent later merges.
        """
        import numpy as np

        tol_E = 0.01  # eV (10 meV)

        # Collect (key, E_start, E_end)
        items = []
        for key, y_data in getattr(self, "plot_data", {}).items():
            try:
                parts = key.split("##", 1)
                if len(parts) != 2:
                    continue
                abs_path, hdf5_path = parts
                parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""

                if y_data is None:
                    continue
                y_arr = np.asarray(y_data).ravel()
                if y_arr.size == 0:
                    continue

                # Energy lookup (pcap_energy_av preferred inside lookup_energy).
                try:
                    from .data import lookup_energy as _lookup
                    x_data = _lookup(self, abs_path, parent, int(y_arr.size))
                except Exception:
                    x_data = np.arange(y_arr.size)

                if getattr(x_data, "size", 0) == 0:
                    continue
                x_arr = np.asarray(x_data).ravel()

                # Match plotting length.
                n = int(min(x_arr.size, y_arr.size))
                if n <= 0:
                    continue
                x_use = x_arr[:n]

                # Use first/last finite x as scan limits.
                finite = np.isfinite(x_use)
                if not np.any(finite):
                    continue
                i0 = int(np.argmax(finite))
                i1 = int(len(finite) - 1 - np.argmax(finite[::-1]))

                e_start = float(x_use[i0])
                e_end = float(x_use[i1])
                if not (np.isfinite(e_start) and np.isfinite(e_end)):
                    continue
                if e_end < e_start:
                    e_start, e_end = e_end, e_start

                items.append((key, e_start, e_end))
            except Exception:
                continue

        if not items:
            return []

        # ---- Union-Find clustering (order-independent) ----
        n = len(items)
        parent = list(range(n))
        rank = [0] * n

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                parent[ra] = rb
            elif rank[ra] > rank[rb]:
                parent[rb] = ra
            else:
                parent[rb] = ra
                rank[ra] += 1

        # Bucket by start energy to reduce comparisons.
        # Any pair within tol_E must fall into same or adjacent start-bin.
        start_bins = {}  # bin_id -> list of indices already seen
        for i, (_, es, ee) in enumerate(items):
            b = int(np.floor(es / tol_E))
            # Compare with indices in neighbouring start-bins.
            for bb in (b - 1, b, b + 1):
                for j in start_bins.get(bb, []):
                    _, es2, ee2 = items[j]
                    if abs(es - es2) <= tol_E and abs(ee - ee2) <= tol_E:
                        union(i, j)
            start_bins.setdefault(b, []).append(i)

        # Build clusters
        clusters = {}
        for i, (key, es, ee) in enumerate(items):
            r = find(i)
            clusters.setdefault(r, {"keys": [], "starts": [], "ends": []})
            clusters[r]["keys"].append(key)
            clusters[r]["starts"].append(es)
            clusters[r]["ends"].append(ee)

        out = []
        for c in clusters.values():
            # Robust representative for display
            ref_start = float(np.median(c["starts"]))
            ref_end = float(np.median(c["ends"]))
            out.append({"keys": c["keys"], "min": ref_start, "max": ref_end})

        out.sort(key=lambda g: (g.get("min", 0.0), g.get("max", 0.0)))
        return out

    def update_raw_tree(self):
        # Refresh 'All in channel' combobox if present
        try:
            self._refresh_all_in_channel_combo()
        except Exception:
            pass
        if not hasattr(self, "raw_tree"):
            return
        self.raw_tree.blockSignals(True)
        try:
            self.raw_tree.clear()
            groups = self.group_datasets(include_sums=False)
            for idx, group in enumerate(groups):
                region_id = f"region_{idx}"
                region_state = getattr(self, "region_states", {}).get(region_id, Qt.Checked)
                display = group.get("label")
                if not display:
                    display = f"({group.get('min',0):.3f}–{group.get('max',0):.3f} eV)"
                region_item = QTreeWidgetItem([f"Region {idx+1}  {display}"])
                region_item.setFlags(region_item.flags() | Qt.ItemIsUserCheckable)
                region_item.setCheckState(0, region_state)
                region_item.setData(0, Qt.UserRole+1, region_id)
                sorted_keys = sorted(group['keys'], key=lambda x: parse_entry_number(x.split("##",1)[1] if "##" in x else ""))
                for key in sorted_keys:
                    parts = key.split("##", 1)
                    label = None
                    try:
                        cl = getattr(self, "custom_labels", {}) or {}
                        if key in cl and cl[key]:
                            label = str(cl[key])
                    except Exception:
                        label = None
                    if not label:
                        label = self.shorten_label(parts[1]) if len(parts) == 2 else key
                    child = QTreeWidgetItem([label])
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    child_state = Qt.Checked if getattr(self, "raw_visibility", {}).get(key, True) else Qt.Unchecked
                    child.setCheckState(0, child_state)
                    child.setData(0, Qt.UserRole, key)
                    color = None
                    try:
                        color = self.get_line_color_for_key(key, self.raw_ax)
                    except Exception:
                        pass
                    if color is not None:
                        qcolor = _qcolor_from_curve_color(color)
                        if qcolor.isValid():
                            pixmap = QPixmap(16, 16)
                            pixmap.fill(qcolor)
                            child.setIcon(0, QIcon(pixmap))
                    region_item.addChild(child)
                self.raw_tree.addTopLevelItem(region_item)
                region_item.setExpanded(True)
                child_count = region_item.childCount()
                checked_count = sum(region_item.child(i).checkState(0) == Qt.Checked for i in range(child_count))
                if checked_count == 0:
                    region_item.setCheckState(0, Qt.Unchecked)
                elif checked_count == child_count:
                    region_item.setCheckState(0, Qt.Checked)
                else:
                    region_item.setCheckState(0, Qt.PartiallyChecked)
        finally:
            self.raw_tree.blockSignals(False)
            self.raw_tree.update()
            setattr(self, "raw_tree_reset", False)

    def raw_tree_item_changed(self, item, column):
        if not hasattr(self, "raw_tree"):
            return
        self.raw_tree.blockSignals(True)
        try:
            if item.parent() is None:
                state = item.checkState(0)
                region_id = item.data(0, Qt.UserRole+1)
                if region_id is not None:
                    self.region_states[region_id] = state
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, state)
                    key = child.data(0, Qt.UserRole)
                    self.raw_visibility[key] = (state == Qt.Checked)
            else:
                key = item.data(0, Qt.UserRole)
                self.raw_visibility[key] = (item.checkState(0) == Qt.Checked)
                parent_item = item.parent()
                child_count = parent_item.childCount()
                checked_count = sum(parent_item.child(i).checkState(0) == Qt.Checked for i in range(child_count))
                if checked_count == 0:
                    parent_item.setCheckState(0, Qt.Unchecked)
                elif checked_count == child_count:
                    parent_item.setCheckState(0, Qt.Checked)
                else:
                    parent_item.setCheckState(0, Qt.PartiallyChecked)
        finally:
            self.raw_tree.blockSignals(False)
        QTimer.singleShot(0, self.update_plot_raw)

    def update_proc_tree(self):
        if not hasattr(self, "proc_tree"):
            return
        self.proc_tree.blockSignals(True)
        try:
            self.proc_tree.clear()
            groups = self.group_datasets(include_sums=True)
            for idx, group in enumerate(groups):
                region_id = f"proc_region_{idx}"
                display = group.get("label")
                if not display:
                    display = f"({group.get('min',0):.3f}–{group.get('max',0):.3f} eV)"
                region_item = QTreeWidgetItem([f"Region {idx+1}  {display}"])
                region_item.setFlags(region_item.flags() | Qt.ItemIsUserCheckable)
                region_item.setCheckState(0, self.proc_region_states.get(region_id, Qt.Checked))
                region_item.setData(0, Qt.UserRole+1, region_id)
                sorted_keys = sorted(group['keys'], key=lambda x: parse_entry_number(x.split("##",1)[1] if "##" in x else ""))
                for key in sorted_keys:
                    parts = key.split("##", 1)
                    # Use intrinsic curve names (e.g. synthetic summed-group names) when available.
                    label = None
                    try:
                        cdn = getattr(self, "curve_display_names", {}) or {}
                        if key in cdn and cdn[key]:
                            label = str(cdn[key])
                    except Exception:
                        label = None
                    if not label:
                        label = self.shorten_label(parts[1]) if len(parts) == 2 else key
                    child = QTreeWidgetItem([label])
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    child_state = Qt.Checked if self.raw_visibility.get(key, True) else Qt.Unchecked
                    child.setCheckState(0, child_state)
                    child.setData(0, Qt.UserRole, key)
                    color = None
                    try:
                        color = self.get_line_color_for_key(key, self.proc_ax)
                    except Exception:
                        pass
                    if color is not None:
                        qcolor = _qcolor_from_curve_color(color)
                        if qcolor.isValid():
                            pixmap = QPixmap(16, 16)
                            pixmap.fill(qcolor)
                            child.setIcon(0, QIcon(pixmap))
                    region_item.addChild(child)
                self.proc_tree.addTopLevelItem(region_item)
                region_item.setExpanded(True)
                child_count = region_item.childCount()
                checked_count = sum(region_item.child(i).checkState(0) == Qt.Checked for i in range(child_count))
                if checked_count == 0:
                    region_item.setCheckState(0, Qt.Unchecked)
                elif checked_count == child_count:
                    region_item.setCheckState(0, Qt.Checked)
                else:
                    region_item.setCheckState(0, Qt.PartiallyChecked)
        finally:
            self.proc_tree.blockSignals(False)
            self.proc_tree.update()

    def proc_tree_item_changed(self, item, column):
        if not hasattr(self, "proc_tree"):
            return
        self.proc_tree.blockSignals(True)
        try:
            if item.parent() is None:
                state = item.checkState(0)
                region_id = item.data(0, Qt.UserRole+1)
                if region_id is not None:
                    self.proc_region_states[region_id] = state
                for i in range(item.childCount()):
                    child = item.child(i)
                    child.setCheckState(0, state)
                    key = child.data(0, Qt.UserRole)
                    self.raw_visibility[key] = (state == Qt.Checked)
            else:
                key = item.data(0, Qt.UserRole)
                self.raw_visibility[key] = (item.checkState(0) == Qt.Checked)
                parent_item = item.parent()
                child_count = parent_item.childCount()
                checked_count = sum(parent_item.child(i).checkState(0) == Qt.Checked for i in range(child_count))
                if checked_count == 0:
                    parent_item.setCheckState(0, Qt.Unchecked)
                elif checked_count == child_count:
                    parent_item.setCheckState(0, Qt.Checked)
                else:
                    parent_item.setCheckState(0, Qt.PartiallyChecked)
        finally:
            self.proc_tree.blockSignals(False)
        QTimer.singleShot(0, self.update_plot_processed)


    # ------------------------------------------------------------------
    # Processed Data tree: context menu for summed groups
    # ------------------------------------------------------------------
    def on_proc_tree_context_menu(self, pos):
        """Right-click context menu on the Processed Data tree for summed groups."""
        try:
            tree = getattr(self, "proc_tree", None)
            if tree is None:
                return
            item = tree.itemAt(pos)
            if item is None:
                return
            key = item.data(0, Qt.UserRole)
            if not key:
                return
            key = str(key)
            sources = getattr(self, "_summed_curve_sources", {}) or {}
            if key not in sources:
                return
            from PyQt5.QtWidgets import QMenu
            menu = QMenu(tree)
            act_info = menu.addAction("Group info")
            act_rename = menu.addAction("Rename")
            act_delete = menu.addAction("Delete")
            chosen = menu.exec_(tree.viewport().mapToGlobal(pos))
            if chosen is None:
                return
            if chosen == act_info:
                self._show_summed_group_info(key)
            elif chosen == act_rename:
                self._rename_summed_group(key, item)
            elif chosen == act_delete:
                self._delete_summed_group(key)
        except Exception:
            return

    def _show_summed_group_info(self, sum_key: str):
        """Show a dialog listing constituent curves of a summed group."""
        from PyQt5.QtWidgets import QMessageBox
        sources = getattr(self, "_summed_curve_sources", {}) or {}
        keys = list(sources.get(sum_key, []) or [])
        if not keys:
            QMessageBox.information(self, "Group info", "No source curves were recorded for this group.")
            return
        lines = []
        for k in keys:
            try:
                parts = str(k).split("##", 1)
                disp = self.shorten_label(parts[1]) if (len(parts) == 2 and hasattr(self, "shorten_label")) else str(k)
            except Exception:
                disp = str(k)
            lines.append(f"- {disp}")
        gname = ""
        try:
            cdn = getattr(self, "curve_display_names", {}) or {}
            gname = str(cdn.get(sum_key) or "")
        except Exception:
            gname = ""
        title = gname if gname else "Summed group"
        QMessageBox.information(self, "Group info", f"<b>{title}</b><br><br>Constituent curves:<br>" + "<br>".join(lines))

    def _rename_summed_group(self, sum_key: str, item):
        """Rename a summed group and propagate the label to Plotted Data (if present)."""
        from PyQt5.QtWidgets import QInputDialog
        current = ""
        try:
            cdn = getattr(self, "curve_display_names", {}) or {}
            current = str(cdn.get(sum_key) or "")
        except Exception:
            current = ""
        new_name, ok = QInputDialog.getText(self, "Rename group", "New group name:", text=current)
        if not ok:
            return
        new_name = str(new_name).strip()
        if not new_name:
            return
        try:
            if not hasattr(self, "curve_display_names") or self.curve_display_names is None:
                self.curve_display_names = {}
            self.curve_display_names[sum_key] = new_name
        except Exception:
            pass
        try:
            item.setText(0, new_name)
        except Exception:
            pass
        self._update_plotted_curve_label(sum_key, new_name)
        try:
            self.update_legend()
        except Exception:
            pass

    def _update_plotted_curve_label(self, key: str, new_label: str) -> None:
        """If a curve is present in Plotted Data, update its row label widget."""
        try:
            lw = getattr(self, "plotted_list", None)
            if lw is None:
                return
            for i in range(lw.count()):
                it = lw.item(i)
                w = lw.itemWidget(it)
                if w is None:
                    continue
                try:
                    if str(getattr(w, "key", "")) == str(key):
                        if hasattr(w, "label") and w.label is not None:
                            w.label.setText(str(new_label))
                        else:
                            it.setText(str(new_label))
                except Exception:
                    continue
        except Exception:
            return

    def _delete_summed_group(self, sum_key: str):
        """Delete a summed group from internal stores after confirmation.

        Note: this does NOT remove it from Plotted Data automatically.
        """
        from PyQt5.QtWidgets import QMessageBox
        sources = getattr(self, "_summed_curve_sources", {}) or {}
        if sum_key not in sources:
            return
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Delete group")
        msg.setText("Delete this summed group from the Processed Data set?")
        msg.setInformativeText("This cannot be undone. Curves already passed to Plotted Data will NOT be removed.")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        if msg.exec_() != QMessageBox.Ok:
            return
        try:
            if hasattr(self, "plot_data") and isinstance(self.plot_data, dict):
                self.plot_data.pop(sum_key, None)
        except Exception:
            pass
        try:
            if hasattr(self, "raw_visibility") and isinstance(self.raw_visibility, dict):
                self.raw_visibility.pop(sum_key, None)
        except Exception:
            pass
        try:
            cdn = getattr(self, "curve_display_names", None)
            if isinstance(cdn, dict):
                cdn.pop(sum_key, None)
        except Exception:
            pass
        try:
            sources.pop(sum_key, None)
        except Exception:
            pass
        try:
            overrides = getattr(self, "_region_overrides", None)
            if isinstance(overrides, dict):
                overrides.pop(sum_key, None)
        except Exception:
            pass
        try:
            self.update_plot_processed()
        except Exception:
            pass
        try:
            self.update_plot_raw()
        except Exception:
            pass
