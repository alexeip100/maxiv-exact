"""Curve summation dialog.

This dialog lets the user partition the currently active curves into one or more
summation groups by drag-and-drop.

UX (as requested):
- On open, ALL curves are listed under "Available curves".
- The "Summation groups" tree starts with a single group ("Group1") (editable).
- Drag one or multiple curves from "Available curves" into a group to assign them.
  Assigned curves are removed from "Available curves" and appear as children of the group.
- Drag curves back from a group into "Available curves" to unassign them.
- "+ Group" adds a new group ("Group2", "Group3", ...) (editable).
- "− Group" removes the selected group and returns its curves back to "Available curves".
- OK creates summed curves for groups with >= 1 members.

Group naming:
- Group titles are editable.
- If a group title remains at the default "GroupN" and an autoname function is provided,
  it will be auto-filled on accept.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

MIME_CURVES = "application/x-maxiv-exact-curves"


def _pack_curves(curves: List[Tuple[str, str]]) -> bytes:
    return json.dumps([{"key": k, "disp": d} for k, d in curves]).encode("utf-8")


def _unpack_curves(payload: bytes) -> List[Tuple[str, str]]:
    try:
        data = json.loads(payload.decode("utf-8"))
        out: List[Tuple[str, str]] = []
        for item in data:
            k = str(item.get("key", "")).strip()
            d = str(item.get("disp", "")).strip()
            if k and d:
                out.append((k, d))
        return out
    except Exception:
        return []


class AvailableCurvesList(QListWidget):
    """List widget that supports dragging curve items out and dropping them back."""

    def __init__(self, parent_dialog: "CurveSummationDialog"):
        super().__init__(parent_dialog)
        self._dlg = parent_dialog
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def startDrag(self, supportedActions):
        items = self.selectedItems() or []
        curves: List[Tuple[str, str]] = []
        for it in items:
            k = it.data(Qt.ItemDataRole.UserRole)
            d = it.text()
            if k and d:
                curves.append((str(k), str(d)))
        if not curves:
            return
        mime = QMimeData()
        mime.setData(MIME_CURVES, _pack_curves(curves))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_CURVES):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_CURVES):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_CURVES):
            return super().dropEvent(event)
        curves = _unpack_curves(bytes(event.mimeData().data(MIME_CURVES)))
        if curves:
            self._dlg.move_curves_to_available(curves)
        event.acceptProposedAction()


class GroupsTree(QTreeWidget):
    """Tree widget with top-level groups and curve children. Supports DnD."""

    def __init__(self, parent_dialog: "CurveSummationDialog"):
        super().__init__(parent_dialog)
        self._dlg = parent_dialog
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def startDrag(self, supportedActions):
        # Only drag curve children, not group headers
        it = self.currentItem()
        if it is None or it.parent() is None:
            return
        k = it.data(0, Qt.ItemDataRole.UserRole)
        d = it.text(0)
        if not k or not d:
            return
        curves = [(str(k), str(d))]
        mime = QMimeData()
        mime.setData(MIME_CURVES, _pack_curves(curves))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_CURVES):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_CURVES):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_CURVES):
            return super().dropEvent(event)
        curves = _unpack_curves(bytes(event.mimeData().data(MIME_CURVES)))
        if curves:
            pos_item = self.itemAt(event.position().toPoint())
            group_item = None
            if pos_item is not None:
                group_item = pos_item if pos_item.parent() is None else pos_item.parent()
            self._dlg.move_curves_to_group(curves, group_item)
        event.acceptProposedAction()


class CurveSummationDialog(QDialog):
    """Build summation groups from a list of curves.

    Parameters
    ----------
    curves:
        List of tuples: (key, display_name)
    parent:
        Qt parent
    autoname_func:
        Optional callable(keys: List[str]) -> str for default group auto-naming.
    """

    def __init__(self, curves: List[Tuple[str, str]], parent=None, autoname_func=None):
        super().__init__(parent)
        self.setWindowTitle("Curve summation")
        self.resize(900, 560)

        self._all: List[Tuple[str, str]] = list(curves or [])
        self._display_for_key: Dict[str, str] = {k: d for k, d in self._all}
        self._autoname_func = autoname_func
        self._group_counter = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        info = QLabel(
            "Drag curves from 'Available curves' into groups on the right to define summation sub-groups.\n"
            "Right-click is not used here; use drag-and-drop.\n\n"
            "Remove a group with '− Group' to return its curves back to 'Available curves'."
        )
        info.setWordWrap(True)
        outer.addWidget(info)

        mid = QHBoxLayout()
        outer.addLayout(mid, 1)

        # Left
        left = QVBoxLayout()
        mid.addLayout(left, 1)
        left.addWidget(QLabel("Available curves"))
        self.available_list = AvailableCurvesList(self)
        left.addWidget(self.available_list, 1)

        # Middle buttons
        btns = QVBoxLayout()
        mid.addLayout(btns)
        btns.addStretch(1)
        self.btn_add_group = QPushButton("+ Group")
        self.btn_del_group = QPushButton("− Group")
        btns.addWidget(self.btn_add_group)
        btns.addWidget(self.btn_del_group)
        btns.addStretch(1)

        # Right
        right = QVBoxLayout()
        mid.addLayout(right, 1)
        right.addWidget(QLabel("Summation groups"))
        hint_label = QLabel("Tip: Double-click a group name to edit.")
        hint_label.setStyleSheet("color: palette(mid);")
        right.addWidget(hint_label)
        self.groups_tree = GroupsTree(self)
        right.addWidget(self.groups_tree, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        outer.addWidget(self.button_box)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        self.btn_add_group.clicked.connect(self._add_group)
        self.btn_del_group.clicked.connect(self._delete_selected_group)

        self._populate_initial()

    # ---- Public API ----------
    def get_groups(self) -> List[Dict[str, object]]:
        """Return groups as [{"name": str, "keys": [..]}, ...]."""
        groups: List[Dict[str, object]] = []
        for i in range(self.groups_tree.topLevelItemCount()):
            gitem = self.groups_tree.topLevelItem(i)
            if gitem is None:
                continue
            name = str(gitem.text(0) or "Sum").strip() or "Sum"
            keys: List[str] = []
            for j in range(gitem.childCount()):
                c = gitem.child(j)
                if c is None:
                    continue
                k = c.data(0, Qt.ItemDataRole.UserRole)
                if k:
                    keys.append(str(k))
            groups.append({"name": name, "keys": keys})
        return groups

    # ---- DnD helpers called by child widgets ----
    def move_curves_to_group(self, curves: List[Tuple[str, str]], group_item: QTreeWidgetItem | None):
        """Assign curves to the given group (or current/first group if None)."""
        g = group_item
        if g is None:
            g = self.groups_tree.currentItem()
            if g is not None and g.parent() is not None:
                g = g.parent()
        if g is None:
            g = self.groups_tree.topLevelItem(0)
        if g is None:
            g = self._add_group()
        for key, disp in curves:
            # Remove from available (if present)
            self._remove_from_available(key)
            # Ensure it is not already in any group
            self._remove_from_groups(key)
            # Add to target group
            self._create_curve_child(g, key, disp)
        g.setExpanded(True)
        self.groups_tree.setCurrentItem(g)

    def move_curves_to_available(self, curves: List[Tuple[str, str]]):
        """Return curves back to the available list (unassign)."""
        for key, disp in curves:
            self._remove_from_groups(key)
            # avoid duplicates
            if not self._available_has_key(key):
                self._add_to_available(key, disp)

    # ---- Internals ----
    def _populate_initial(self):
        self.available_list.clear()
        self.groups_tree.clear()
        # all curves start as available
        for key, disp in self._all:
            self._add_to_available(key, disp)
        # one default group
        self._add_group()

    def _add_group(self) -> QTreeWidgetItem:
        self._group_counter += 1
        name = f"Group{self._group_counter}"
        g = QTreeWidgetItem([name])
        g.setFlags(g.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        self.groups_tree.addTopLevelItem(g)
        self.groups_tree.setCurrentItem(g)
        return g

    def _delete_selected_group(self):
        g = self.groups_tree.currentItem()
        if g is None:
            return
        if g.parent() is not None:
            g = g.parent()
        if g is None:
            return
        if g.parent() is not None:
            return
        # Move children back
        to_move: List[Tuple[str, str]] = []
        for j in range(g.childCount()):
            c = g.child(j)
            if c is None:
                continue
            k = c.data(0, Qt.ItemDataRole.UserRole)
            d = c.text(0)
            if k and d:
                to_move.append((str(k), str(d)))
        self.move_curves_to_available(to_move)
        idx = self.groups_tree.indexOfTopLevelItem(g)
        if idx >= 0:
            self.groups_tree.takeTopLevelItem(idx)
        # Ensure at least one group exists
        if self.groups_tree.topLevelItemCount() == 0:
            self._group_counter = 0
            self._add_group()

    def _add_to_available(self, key: str, disp: str):
        item = QListWidgetItem(str(disp))
        item.setData(Qt.ItemDataRole.UserRole, str(key))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        self.available_list.addItem(item)

    def _available_has_key(self, key: str) -> bool:
        for i in range(self.available_list.count()):
            it = self.available_list.item(i)
            if it and str(it.data(Qt.ItemDataRole.UserRole)) == str(key):
                return True
        return False

    def _remove_from_available(self, key: str):
        key = str(key)
        for i in range(self.available_list.count() - 1, -1, -1):
            it = self.available_list.item(i)
            if it and str(it.data(Qt.ItemDataRole.UserRole)) == key:
                self.available_list.takeItem(i)

    def _remove_from_groups(self, key: str):
        key = str(key)
        for gi in range(self.groups_tree.topLevelItemCount()):
            g = self.groups_tree.topLevelItem(gi)
            if g is None:
                continue
            for cj in range(g.childCount() - 1, -1, -1):
                c = g.child(cj)
                if c and str(c.data(0, Qt.ItemDataRole.UserRole)) == key:
                    g.takeChild(cj)

    def _create_curve_child(self, group_item: QTreeWidgetItem, key: str, disp: str):
        c = QTreeWidgetItem([str(disp)])
        c.setData(0, Qt.ItemDataRole.UserRole, str(key))
        c.setFlags(c.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
        group_item.addChild(c)


    def _on_accept(self):
        """Validate and accept.

        Rules:
        - At least one curve must be assigned to any group.
        - Group names must be unique (case-insensitive, after stripping).
        """
        total_assigned = 0
        names = []
        for i in range(self.groups_tree.topLevelItemCount()):
            g = self.groups_tree.topLevelItem(i)
            if g is None:
                continue
            name = str(g.text(0) or "").strip() or f"Group{i+1}"
            names.append(name)
            total_assigned += int(g.childCount())

        if total_assigned == 0:
            QMessageBox.warning(self, "Nothing to sum", "Please drag at least one curve into a group.")
            return

        # Enforce unique group names
        norm = [n.strip().lower() for n in names]
        duplicates = []
        seen = set()
        for n, nn in zip(names, norm):
            if nn in seen and n not in duplicates:
                duplicates.append(n)
            else:
                seen.add(nn)
        if duplicates:
            msg = "Group names must be unique. Please rename the following group(s):\n\n- " + "\n- ".join(duplicates)
            QMessageBox.warning(self, "Duplicate group names", msg)
            return

        self.accept()

