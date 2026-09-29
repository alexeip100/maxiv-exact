"""Channel mapping (beamline profiles).

This module provides a small JSON-backed mapping from canonical roles
(TEY/PEY/TFY/PFY/I0/Energy) to HDF5 dataset name *patterns*.

Goals:
- Keep the default mapping identical to the current FlexPES-A assumptions.
- Allow users to create and save additional mappings for other facilities.
- Keep implementation self-contained to avoid further growth of plotting.py.

The values are treated as *substrings* when searching for datasets.
For I0/Energy you can provide a list of candidate substrings.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from PyQt6 import QtWidgets, QtCore, QtGui  # type: ignore


ROLE_ORDER = ["TEY", "PEY", "TFY", "PFY", "I0", "Energy"]


def _package_default_json_path() -> str:
    return os.path.join(os.path.dirname(__file__), "docs", "channel_mappings.json")


def _user_json_path() -> str:
    """Return the EXACT per-user writable path for the mapping JSON.

    During the 2.5 rebrand, copy the legacy ``~/.flexpes_nexafs`` mapping
    on first use when the new location does not yet exist.
    """
    try:
        base = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.AppDataLocation
        )
    except Exception:
        base = os.path.join(os.path.expanduser("~"), ".maxiv_exact")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".maxiv_exact")
    os.makedirs(base, exist_ok=True)
    target = os.path.join(base, "channel_mappings.json")

    if not os.path.exists(target):
        legacy = os.path.join(
            os.path.expanduser("~"), ".flexpes_nexafs", "channel_mappings.json"
        )
        if os.path.isfile(legacy):
            try:
                shutil.copyfile(legacy, target)
            except Exception:
                pass
    return target


def _is_writable_path(path: str) -> bool:
    """Return True if 'path' can be created/overwritten."""
    try:
        path = str(path)
        parent = os.path.dirname(path) or "."
        if os.path.exists(path):
            return os.access(path, os.W_OK)
        return os.path.isdir(parent) and os.access(parent, os.W_OK)
    except Exception:
        return False


def _effective_json_path() -> str:
    """Prefer the package JSON if writable (developer/source checkout); otherwise use per-user config."""
    pkg = _package_default_json_path()
    usr = _user_json_path()
    if _is_writable_path(pkg):
        return pkg
    return usr


@dataclass

class ChannelConfigManager:
    """Load/save and query channel mappings."""

    data: Dict[str, Any]

    def __init__(self) -> None:
        self.data = {}
        self.load()

    def json_path(self) -> str:
        """Return the JSON file currently used for load/save."""
        return str(getattr(self, 'mapping_path', _effective_json_path()))

    def load(self) -> None:
        """Load mapping JSON.

        If running from a writable source checkout, edits are stored in the package
        file (docs/channel_mappings.json). Otherwise, edits are stored in a per-user
        config file (AppDataLocation/channel_mappings.json).
        """
        default_path = _package_default_json_path()
        path = _effective_json_path()

        # Ensure target exists
        if not os.path.exists(path):
            try:
                if path != default_path and os.path.exists(default_path):
                    shutil.copyfile(default_path, path)
                else:
                    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump({
                            "active_profile": "FlexPES-A",
                            "profiles": {
                                "FlexPES-A": {
                                    "TEY": "_ch1",
                                    "PEY": "_ch3",
                                    "TFY": "roi2_dtc",
                                    "PFY": "roi1_dtc",
                                    "I0": ["b107a_em_03_ch2", "b107a_em_04_ch2", "Pt_No"],
                                    "Energy": ["x", "energy", "photon_energy", "pcap_energy_av", "mono_traj_energy"],
                                }
                            },
                        }, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        # Load JSON
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}

        # Ensure required structure
        self.data.setdefault("active_profile", "FlexPES-A")
        self.data.setdefault("profiles", {})
        if not isinstance(self.data.get("profiles"), dict):
            self.data["profiles"] = {}
        if not self.data["profiles"]:
            self.data["profiles"] = {
                "FlexPES-A": {
                    "TEY": "_ch1",
                    "PEY": "_ch3",
                    "TFY": "roi2_dtc",
                    "PFY": "roi1_dtc",
                    "I0": ["b107a_em_03_ch2", "b107a_em_04_ch2", "Pt_No"],
                    "Energy": ["x", "energy", "photon_energy", "pcap_energy_av", "mono_traj_energy"],
                }
            }

        # Ensure active profile exists
        ap = str(self.data.get("active_profile", "FlexPES-A"))
        if ap not in self.data["profiles"]:
            self.data["active_profile"] = next(iter(self.data["profiles"].keys()))
        # Clean up empty profiles created by older UI versions
        self._prune_empty_profiles()


        # Remember which file we are using
        self.mapping_path = path
    def save(self) -> None:
        path = _effective_json_path()
        self.mapping_path = path
        self._prune_empty_profiles()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # Backwards compatibility
    def save_to_user(self) -> None:
        self.save()

    def active_profile(self) -> str:
        return str(self.data.get("active_profile", "FlexPES-A"))

    def set_active_profile(self, name: str) -> None:
        name = str(name).strip()
        if not name:
            return
        if name not in self.data.get("profiles", {}):
            self.data.setdefault("profiles", {})[name] = {}
        self.data["active_profile"] = name

    def _prune_empty_profiles(self) -> None:
        """Remove profiles that are effectively empty.

        Older dialog versions could create a new profile on every keystroke in an
        editable combo box (e.g. 'F', 'Fl', ...). We remove such profiles here.
        """
        profiles = self.data.get("profiles", {})
        if not isinstance(profiles, dict):
            return

        protected = {"FlexPES-A"}
        active = self.data.get("active_profile")
        if isinstance(active, str) and active:
            protected.add(active)

        def _is_empty_profile(p: dict) -> bool:
            if not isinstance(p, dict) or len(p) == 0:
                return True
            for v in p.values():
                if v is None:
                    continue
                if isinstance(v, str) and v.strip() == "":
                    continue
                if isinstance(v, list) and len([x for x in v if str(x).strip() != ""]) == 0:
                    continue
                return False
            return True

        for name in list(profiles.keys()):
            if name in protected:
                continue
            if _is_empty_profile(profiles.get(name, {})):
                profiles.pop(name, None)


    def profiles(self) -> List[str]:
        return sorted(list(self.data.get("profiles", {}).keys()), key=lambda s: s.lower())

    def get_value(self, role: str) -> Union[str, List[str], None]:
        prof = self.data.get("profiles", {}).get(self.active_profile(), {})
        return prof.get(role)

    def get_value_for_profile(self, profile: str, role: str) -> Union[str, List[str], None]:
        prof = self.data.get("profiles", {}).get(str(profile), {})
        return prof.get(role)

    def set_value(self, role: str, value: Union[str, List[str], None]) -> None:
        prof = self.data.setdefault("profiles", {}).setdefault(self.active_profile(), {})
        if value is None:
            prof.pop(role, None)
        else:
            prof[role] = value

    def get_pattern(self, role: str) -> str:
        v = self.get_value(role)
        if isinstance(v, list):
            return str(v[0]) if v else ""
        return str(v) if v is not None else ""

    def get_candidates(self, role: str) -> List[str]:
        v = self.get_value(role)
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        s = str(v).strip()
        return [s] if s else []


class ChannelSetupDialog(QtWidgets.QDialog):
    """Simple editor for channel mappings."""

    def __init__(self, manager: ChannelConfigManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Setup channels")
        self.manager = manager

        # Default dialog size (slightly wider/taller for readability)
        self.resize(770, 420)

        layout = QtWidgets.QVBoxLayout(self)

        # Profile row
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Beamline profile:"))
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.addItems(self.manager.profiles())
        idx = self.profile_combo.findText(self.manager.active_profile())
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        else:
            self.profile_combo.setEditText(self.manager.active_profile())
        row.addWidget(self.profile_combo, 1)

        # Intuitive workflow: select a profile from the list and apply it using
        # the button next to the list.
        self.btn_use = QtWidgets.QPushButton("Use selected")
        row.addWidget(self.btn_use)
        layout.addLayout(row)

        # Mapping file location (kept subtle to avoid distracting new users)
        self.link_show_location = QtWidgets.QLabel('<a href="show">Show config file location</a>')
        self.link_show_location.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.link_show_location.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        self.link_show_location.setOpenExternalLinks(False)
        self.link_show_location.linkActivated.connect(lambda _=None: self._show_config_file_location())
        layout.addWidget(self.link_show_location)

        note = QtWidgets.QLabel(
            "Enter HDF5 dataset *names or substrings* for each role.\n"
            "Select a profile to view/edit its mapping. Click 'Use selected' to make it the active beamline.\n"
            "For I0 and Energy you can provide multiple candidates separated by commas (first match wins)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        # Table: Role / Pattern
        self.table = QtWidgets.QTableWidget(len(ROLE_ORDER), 2)
        self.table.setHorizontalHeaderLabels(["Role", "Dataset name / substring"])
        try:
            self.table.horizontalHeader().setStretchLastSection(True)
        except Exception:
            pass
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        layout.addWidget(self.table, 1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        # Cancel: close dialog without applying the selected profile or saving edits
        self.btn_cancel = QtWidgets.QPushButton("Cancel")

        # Delete profile
        self.btn_delete = QtWidgets.QPushButton("Delete")

        # Save changes: persist edits to the current profile (with overwrite guard)
        self.btn_ok = QtWidgets.QPushButton("Save changes")
        self.btn_use.setDefault(True)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        # Wire
        # Only switch profiles when the user explicitly selects an existing one.
        try:
            self.profile_combo.activated[str].connect(self._on_profile_selected)
        except Exception:
            self.profile_combo.activated.connect(self._on_profile_selected_index)
        self.btn_ok.clicked.connect(self._on_save)
        self.btn_use.clicked.connect(self._on_use_selected)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_delete.clicked.connect(self._on_delete)

        # Track edits: enable "Save changes" only when needed, and avoid creating profiles while typing.
        try:
            self.table.itemChanged.connect(self._on_table_item_changed)
        except Exception:
            pass
        try:
            le = self.profile_combo.lineEdit()
            if le is not None:
                le.textEdited.connect(self._on_profile_text_edited)
        except Exception:
            pass

        # Initially nothing is "dirty" until the user edits.
        try:
            self.btn_ok.setEnabled(False)
        except Exception:
            pass

        self._populate_table_for_profile(self.manager.active_profile())

        # Track which existing profile is currently selected (to apply on 'Use selected').
        self._selected_profile_name = str(self.manager.active_profile()).strip()

    def _current_profile_name(self) -> str:
        return str(self.profile_combo.currentText()).strip() or "FlexPES-A"

    def _open_json_file(self) -> None:
        """Open the mapping JSON file in the user's default editor/viewer."""
        path = str(self.manager.json_path())
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "File not found", f"Mapping file not found:\n{path}")
            return
        try:
            url = QtCore.QUrl.fromLocalFile(path)
            ok = QtGui.QDesktopServices.openUrl(url)
            if ok is False:
                QtWidgets.QMessageBox.information(self, "Open file", f"Could not open file automatically.\nPath:\n{path}")
        except Exception:
            QtWidgets.QMessageBox.information(self, "Open file", f"Could not open file automatically.\nPath:\n{path}")


    def _on_profile_selected(self, name: str) -> None:
        """Switch to an existing profile selected from the drop-down.

        Selecting a profile loads its mapping for preview/editing.

        Use "Use selected" to make it the active beamline without saving changes.
        """
        name = str(name).strip()
        if not name:
            return
        if name not in self.manager.profiles():
            return

        # If there are unsaved edits, ask whether to discard them.
        if getattr(self, "_dirty", False):
            resp = QtWidgets.QMessageBox.question(
                self,
                "Discard unsaved changes?",
                "You have unsaved changes in the current profile.\n\nDiscard them and switch profile?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if resp != QtWidgets.QMessageBox.StandardButton.Yes:
                # Revert combo to the loaded profile name
                try:
                    prev = str(getattr(self, "_loaded_profile_name", "")).strip()
                    if prev:
                        idx = self.profile_combo.findText(prev)
                        if idx >= 0:
                            self.profile_combo.setCurrentIndex(idx)
                        else:
                            self.profile_combo.setEditText(prev)
                except Exception:
                    pass
                return
        # Do not change the application's active profile yet; only preview/load the mapping.
        self._selected_profile_name = name
        self._populate_table_for_profile(name)
    def _on_profile_selected_index(self, idx: int) -> None:
        try:
            name = self.profile_combo.itemText(int(idx))
        except Exception:
            return
        self._on_profile_selected(name)


    def _on_profile_changed(self, name: str) -> None:
        """(Deprecated) Kept for backwards compatibility; do not create profiles while typing."""
        name = str(name).strip()
        if not name:
            return
        if name not in self.manager.profiles():
            return
        self.manager.set_active_profile(name)
        self._populate_table_for_profile(name)

    def _on_profile_text_edited(self, _txt: str) -> None:
        """Called when user types in the profile name field."""
        self._update_save_button_state()

    def _on_table_item_changed(self, _item: QtWidgets.QTableWidgetItem) -> None:
        """Mark dialog as dirty when user edits mapping values."""
        try:
            if self.table.signalsBlocked():
                return
        except Exception:
            pass
        self._dirty = True
        self._update_save_button_state()

    def _normalized_mapping(self, mapping: Dict[str, Union[str, List[str], None]]) -> Dict[str, Union[str, List[str]]]:
        """Normalize mapping for comparison and saving."""
        out: Dict[str, Union[str, List[str]]] = {}
        for role in ROLE_ORDER:
            v = mapping.get(role, None)
            if role in ("I0", "Energy"):
                vals: List[str] = []
                if isinstance(v, list):
                    vals = [str(x).strip() for x in v if str(x).strip()]
                elif isinstance(v, str):
                    vals = [x.strip() for x in v.split(",") if x.strip()]
                if vals:
                    out[role] = vals
            else:
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        out[role] = s
        return out

    def _mapping_for_profile(self, name: str) -> Dict[str, Union[str, List[str]]]:
        prof = self.manager.data.get("profiles", {}).get(name, {}) if name else {}
        raw: Dict[str, Union[str, List[str], None]] = {role: prof.get(role, None) for role in ROLE_ORDER}
        return self._normalized_mapping(raw)

    def _find_duplicate_patterns(self, mapping: Dict[str, Union[str, List[str]]]) -> Dict[str, List[str]]:
        """Return {pattern: [roles...]} for patterns assigned to more than one role.

        We compare patterns case-insensitively after stripping whitespace.
        """
        pat_roles: Dict[str, set] = {}
        for role, v in mapping.items():
            vals: List[str]
            if isinstance(v, list):
                vals = [str(x) for x in v]
            else:
                vals = [str(v)]
            for p in vals:
                key = str(p).strip()
                if not key:
                    continue
                k = key.lower()
                pat_roles.setdefault(k, set()).add(role)

        duplicates: Dict[str, List[str]] = {}
        for k, roles in pat_roles.items():
            if len(roles) > 1:
                duplicates[k] = sorted(list(roles))
        return duplicates

    def _update_save_button_state(self) -> None:
        """Enable/disable Save button, and adjust its label."""
        name = self._current_profile_name()
        if not name:
            try:
                self.btn_ok.setEnabled(False)
            except Exception:
                pass
            return

        profiles = self.manager.data.get("profiles", {})
        loaded = str(getattr(self, "_loaded_profile_name", "")).strip()

        # If user typed the name of another existing profile, disallow saving into it:
        # to modify an existing profile, the user should select it from the list first.
        if name in profiles and loaded and name != loaded:
            try:
                self.btn_ok.setText("Save changes")
                self.btn_ok.setEnabled(False)
                self.btn_ok.setToolTip("Select an existing profile from the list to edit it.")
            except Exception:
                pass
            return

        # Determine whether there are changes to save.
        if name in profiles and loaded == name:
            # Recompute diff to avoid enabling Save if user reverted changes.
            current = self._normalized_mapping(self._read_table())
            original = self._mapping_for_profile(name)
            changed = (current != original)
            self._dirty = bool(changed)
            try:
                self.btn_ok.setText("Save changes")
                self.btn_ok.setToolTip("Save modifications to the current profile.")
                # Require an Energy channel before allowing saves.
                if changed and ("Energy" not in current):
                    self.btn_ok.setEnabled(False)
                    self.btn_ok.setToolTip("Set an Energy channel before saving this profile.")
                else:
                    self.btn_ok.setEnabled(bool(changed))
            except Exception:
                pass
            return

        # New profile name
        try:
            self.btn_ok.setText("Create profile")
            self.btn_ok.setToolTip("Create a new profile with this name.")
            current = self._normalized_mapping(self._read_table())
            # Require an Energy channel before allowing creation.
            if "Energy" not in current:
                self.btn_ok.setEnabled(False)
                self.btn_ok.setToolTip("Set an Energy channel before creating a new profile.")
            else:
                # Allow creating only if at least one role is filled (Energy alone is allowed).
                self.btn_ok.setEnabled(bool(current))
        except Exception:
            pass
    def _populate_table_for_profile(self, name: str) -> None:
        self.table.blockSignals(True)
        try:
            for r, role in enumerate(ROLE_ORDER):
                it_role = QtWidgets.QTableWidgetItem(role)
                it_role.setFlags(it_role.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, it_role)

                v = self.manager.get_value_for_profile(name, role)
                if isinstance(v, list):
                    txt = ", ".join([str(x) for x in v])
                else:
                    txt = "" if v is None else str(v)
                it_val = QtWidgets.QTableWidgetItem(txt)
                self.table.setItem(r, 1, it_val)
        finally:
            self.table.blockSignals(False)

        # Track what is currently loaded so we can warn on overwrite.
        self._loaded_profile_name = str(name).strip()
        self._dirty = False
        self._update_save_button_state()
    def _read_table(self) -> Dict[str, Union[str, List[str]]]:
        out: Dict[str, Union[str, List[str]]] = {}
        for r, role in enumerate(ROLE_ORDER):
            item = self.table.item(r, 1)
            txt = "" if item is None else str(item.text()).strip()
            if role in ("I0", "Energy"):
                vals = [t.strip() for t in txt.split(",") if t.strip()]
                if vals:
                    out[role] = vals
            else:
                if txt:
                    out[role] = txt
        return out

    def _on_save(self) -> None:
        name = self._current_profile_name()
        if not name:
            return

        profiles = self.manager.data.setdefault("profiles", {})
        loaded = str(getattr(self, "_loaded_profile_name", "")).strip()

        # Prevent accidental overwrite of another existing profile name that was typed manually.
        if name in profiles and loaded and name != loaded:
            QtWidgets.QMessageBox.information(
                self,
                "Select profile to edit",
                f"'{name}' is an existing profile.\n\n"
                "To use it, select it from the drop-down list.\n"
                "To edit it, first select it from the list, then modify values and press 'Save changes'.",
            )
            return

        current_norm = self._normalized_mapping(self._read_table())

        # Validate: Energy channel is required for a usable profile.
        if "Energy" not in current_norm:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing Energy channel",
                "Please set an Energy channel before saving a beamline profile.",
            )
            return

        # Validate: prevent the same dataset/pattern being assigned to multiple roles.
        duplicates = self._find_duplicate_patterns(current_norm)
        if duplicates:
            lines = []
            for pat, roles in sorted(duplicates.items(), key=lambda kv: kv[0]):
                lines.append(f"  • '{pat}' → {', '.join(roles)}")
            msg = (
                "The same dataset name/substring is assigned to more than one role.\n\n"
                "Please make each role unique.\n\n"
                "Conflicts:\n" + "\n".join(lines)
            )
            QtWidgets.QMessageBox.warning(self, "Duplicate channel assignments", msg)
            return

        # If profile exists and we are updating it, confirm overwrite when there are actual changes.
        if name in profiles and loaded == name:
            original_norm = self._mapping_for_profile(name)
            if current_norm == original_norm:
                # Nothing to save, but still activate this existing profile.
                try:
                    self.manager.data["active_profile"] = name
                    self.manager.save_to_user()
                except Exception:
                    pass
                self.accept()
                return

            extra = ""
            if name == "FlexPES-A":
                extra = "\n\nNote: 'FlexPES-A' is the default preset. Consider saving under a new name instead."
            resp = QtWidgets.QMessageBox.question(
                self,
                "Overwrite existing profile?",
                f"You are about to modify the existing setup '{name}'.\n\nProceed?{extra}",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if resp != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        # Create new profile if needed
        if name not in profiles:
            profiles[name] = {}

        prof = profiles[name]
        for role in ROLE_ORDER:
            if role in current_norm:
                prof[role] = current_norm[role]
            else:
                prof.pop(role, None)

        self.manager.data["active_profile"] = name

        try:
            self.manager.save_to_user()
        except Exception:
            # Do not block closing if saving fails; user can still proceed.
            pass

        # Refresh combo items if a new profile name was typed
        if self.profile_combo.findText(name) < 0:
            self.profile_combo.addItem(name)

        # Update loaded state
        self._loaded_profile_name = name
        self._dirty = False

        self.accept()

    def _on_use_selected(self) -> None:
        """Apply the selected *existing* profile and close the dialog.

        This is the intuitive path for users who simply want to switch beamline setups:
        select a profile from the list and click 'Use selected' (no saving needed).
        """
        name = self._current_profile_name()
        if not name:
            return

        profiles = self.manager.data.get("profiles", {})

        # Only existing profiles can be "used" without saving first.
        if name not in profiles:
            QtWidgets.QMessageBox.information(
                self,
                "Profile not saved",
                f"'{name}' does not exist yet.\n\n"
                "To create and use a new profile, enter the name and press 'Save changes' first.",
            )
            return

        # If there are unsaved edits in the table, ask what to do.
        if getattr(self, "_dirty", False):
            mb = QtWidgets.QMessageBox(self)
            mb.setIcon(QtWidgets.QMessageBox.Icon.Warning)
            mb.setWindowTitle("Unsaved changes")
            mb.setText("You have unsaved changes in the current profile.\n\nWhat would you like to do?")
            btn_save = mb.addButton("Save changes", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            btn_discard = mb.addButton("Discard", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = mb.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
            mb.exec()
            clicked = mb.clickedButton()

            if clicked == btn_save:
                # _on_save() will handle overwrite guards and close the dialog on success.
                self._on_save()
                return
            if clicked == btn_cancel:
                return

            # Discard: restore the last saved values for the selected profile.
            try:
                self._populate_table_for_profile(name)
            except Exception:
                pass

        # Apply active profile and close.
        try:
            self.manager.data["active_profile"] = name
            self.manager.save_to_user()
        except Exception:
            pass

        self.accept()

    def _on_delete(self) -> None:
        """Delete the currently selected profile (with confirmation)."""
        name = ""
        try:
            name = self._current_profile_name()
        except Exception:
            try:
                name = str(self.profile_combo.currentText()).strip()
            except Exception:
                name = ""
        if not name:
            return

        # Protect default shipping profile
        if name.strip() == "FlexPES-A":
            try:
                QtWidgets.QMessageBox.information(
                    self,
                    "Protected profile",
                    "The default profile 'FlexPES-A' cannot be deleted."
                )
            except Exception:
                pass
            return

        mb = QtWidgets.QMessageBox(self)
        mb.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        mb.setWindowTitle("Delete profile")
        mb.setText(f"Delete beamline profile '{name}'?")
        mb.setInformativeText("This cannot be undone.")
        btn_delete = mb.addButton("Delete", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        try:
            mb.exec()
        except Exception:
            mb.exec()
        if mb.clickedButton() != btn_delete:
            return

        try:
            profs = self.manager.data.get("profiles", {})
            if isinstance(profs, dict):
                profs.pop(name, None)

            # If we deleted the active profile, fall back to FlexPES-A or first available.
            if self.manager.data.get("active_profile") == name:
                if "FlexPES-A" in profs:
                    self.manager.data["active_profile"] = "FlexPES-A"
                else:
                    self.manager.data["active_profile"] = next(iter(profs.keys()), "")

            self.manager.save_to_user()
        except Exception:
            return

        # Refresh combo content
        new_active = str(self.manager.data.get("active_profile", "")).strip()
        try:
            self.profile_combo.blockSignals(True)
            self.profile_combo.clear()
            self.profile_combo.addItems(self.manager.profiles())
            idx = self.profile_combo.findText(new_active)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
            else:
                self.profile_combo.setEditText(new_active)
        finally:
            try:
                self.profile_combo.blockSignals(False)
            except Exception:
                pass

        # Reload table for the now-selected profile
        try:
            self._populate_table_for_profile(str(self.profile_combo.currentText()).strip())
        except Exception:
            pass
        try:
            self._dirty = False
            self._update_save_button_state()
        except Exception:
            pass


    def _show_config_file_location(self) -> None:
        """Show the location of the JSON mapping file (and allow opening/copying)."""
        # Determine the mapping file path
        try:
            path = str(self.manager.json_path())
        except Exception:
            path = str(getattr(self.manager, 'mapping_path', ''))
        if not path:
            path = "<unknown>"

        mb = QtWidgets.QMessageBox(self)
        mb.setWindowTitle("Channel mapping file")
        mb.setIcon(QtWidgets.QMessageBox.Icon.Information)
        mb.setText("Channel mapping file location:")
        mb.setInformativeText(path)

        btn_open = mb.addButton("Open", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        btn_copy = mb.addButton("Copy path", QtWidgets.QMessageBox.ButtonRole.ActionRole)
        mb.addButton("Close", QtWidgets.QMessageBox.ButtonRole.RejectRole)

        mb.exec()
        clicked = mb.clickedButton()

        if clicked == btn_copy:
            try:
                QtWidgets.QApplication.clipboard().setText(path)
            except Exception:
                pass
            return

        if clicked == btn_open:
            if not path or path == "<unknown>":
                QtWidgets.QMessageBox.warning(self, "Channel mapping file", "The mapping file location is unknown.")
                return
            try:
                open_target = path
                if not os.path.exists(open_target):
                    open_target = os.path.dirname(path) or path
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(open_target))
            except Exception:
                pass
            return


