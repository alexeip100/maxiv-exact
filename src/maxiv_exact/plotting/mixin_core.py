# Core plotting/UI glue methods remaining after splitting the heavy plotting logic. / This module intentionally contains methods that still touch bot...

from __future__ import annotations

import re

import numpy as np

from PyQt6.QtWidgets import (
    QMessageBox,
    QDialog,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QSizePolicy,
    QWidget,
    QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument, QKeySequence, QFont, QShortcut

from ..widgets.help_browser import HelpBrowser
from ..utils.help_text import get_usage_html, get_whats_new_payload


class CorePlottingMixin:
    def _normalize_hdf5_key(hdf5_key):
        """Normalize an HDF5 access key to a string.

        h5py expects group/dataset access keys to be bytes or str. In rare cases
        the stored key can become a tuple (e.g. values from `.items()` or a tuple
        of path segments). This helper converts such values into a usable HDF5
        path string.
        """
        try:
            if isinstance(hdf5_key, bytes):
                return hdf5_key.decode("utf-8", errors="replace")
            if isinstance(hdf5_key, str):
                return hdf5_key
            if isinstance(hdf5_key, tuple):
# Common case: (name, obj) coming from `.items()`.
                if len(hdf5_key) >= 1 and isinstance(hdf5_key[0], (str, bytes)):
                    first = hdf5_key[0]
                    if isinstance(first, bytes):
                        first = first.decode("utf-8", errors="replace")
# If all elements are str/bytes, treat as path segments.
                    if all(isinstance(x, (str, bytes)) for x in hdf5_key):
                        parts = []
                        for x in hdf5_key:
                            if isinstance(x, bytes):
                                x = x.decode("utf-8", errors="replace")
                            x = (x or "").strip("/")
                            if x:
                                parts.append(x)
                        if not parts:
                            return ""
                        path = "/".join(parts)
# Preserve absolute path if the first part looked absolute.
                        if str(first).startswith("/"):
                            path = "/" + path.lstrip("/")
                        return path
                    return str(first)
# Fallback for odd tuple shapes.
                return str(hdf5_key)
# Last resort.
            return str(hdf5_key)
        except Exception:
            return str(hdf5_key)


    def shorten_label(self, hdf5_path: str) -> str:
        """Return a compact label like 'TEY in entry0001' from an HDF5 dataset path.
        Heuristics follow the old app_window.py behavior."""
        try:
            path = (hdf5_path or "").strip("/")
            tokens = path.split("/") if path else []
            last = tokens[-1] if tokens else path
            label = last
            low = (last or "").lower()
            if "ch1" in low:
                label = "TEY"
            elif "ch3" in low:
                label = "PEY"
            elif "roi2_dtc" in low or "roi2" in low:
                label = "TFY"
            elif "roi1_dtc" in low or "roi1" in low:
                label = "PFY"
            entry = ""
            for t in tokens:
                if t.startswith("entry"):
                    entry = t
                    break
            return f"{label} in {entry}" if entry else label
        except Exception:
            return str(hdf5_path)

# ------------ Waterfall ------------
    def _filter_empty_plot_data(self):
        """Drop invalid 1D payloads (empty arrays, scalars) from plot_data.

        Some HDF5 datasets may be empty or unexpectedly scalar-like. These can
        break plotting (e.g. len() of unsized object). We keep only 1D arrays
        with at least one element.
        """
        try:
            cleaned = {}
            for k, v in getattr(self, "plot_data", {}).items():
                try:
                    arr = np.asarray(v)
                    if arr.ndim != 1:
                        continue
                    if arr.size == 0:
                        continue
                    cleaned[k] = arr
                except Exception:
                    continue
            self.plot_data = cleaned
        except Exception:
            pass


# ------------ Plotted tab helpers ------------ / (moved to plotting: pass_to_plotted_no_clear)

# (moved to plotting: _add_reference_curve_to_plotted)

# (moved to plotting: clear_plotted_data)


    def on_tab_changed(self, index):
        if index == 0:
            self.update_plot_raw()
            if hasattr(self, "raw_tree"):
                self.raw_tree.update()
        elif index == 1:
            self.update_plot_processed()
            if hasattr(self, "proc_tree"):
                self.proc_tree.update()


    def _legend_label_from_entry_number(self, key: str, line=None) -> str:
        """Derive a short legend label from an entry identifier.

        Example: 'entry6567/...' or 'entry6567: TEY' -> '6567'.
        If no entry number can be detected, falls back to an existing label.
        """
        import re

# Synthetic summed curves ("__SUM__/...") do not have an entry number. / In "Entry number" mode we want their intrinsic display names (e.g. the
        try:
            h5 = str(key).split("##", 1)[1] if (key and "##" in str(key)) else str(key or "")
            if h5.lstrip("/").startswith("__SUM__/"):
                base = getattr(self, "curve_display_names", {}).get(key)
                if base:
                    return str(base)
                meta = getattr(self, "plotted_metadata", {}).get(key, {}) if hasattr(self, "plotted_metadata") else {}
                if isinstance(meta, dict):
                    lbl = meta.get("label") or meta.get("display_name")
                    if lbl:
                        return str(lbl)
        except Exception:
            pass

# Synthetic summed curves ("__SUM__/...") do not have an entry number. / In "Entry number" mode we want their intrinsic display names (e.g. the
        try:
            h5 = str(key).split("##", 1)[1] if (key and "##" in str(key)) else str(key or "")
            if h5.lstrip("/").startswith("__SUM__/"):
                base = getattr(self, "curve_display_names", {}).get(key)
                if base:
                    return str(base)
# Fall back to plotted metadata label if present
                meta = getattr(self, "plotted_metadata", {}).get(key, {}) if hasattr(self, "plotted_metadata") else {}
                if isinstance(meta, dict):
                    lbl = meta.get("label") or meta.get("display_name")
                    if lbl:
                        return str(lbl)
        except Exception:
            pass
        candidates = []
        try:
            meta = getattr(self, "plotted_metadata", {}).get(key, {}) if hasattr(self, "plotted_metadata") else {}
            if isinstance(meta, dict):
                candidates.append(meta.get("source_entry") or "")
                candidates.append(meta.get("source_file") or "")
        except Exception:
            pass
        try:
            if line is not None and hasattr(line, "get_label"):
                candidates.append(line.get_label() or "")
        except Exception:
            pass
        candidates.append(str(key or ""))

        for txt in candidates:
            try:
                s = str(txt)
            except Exception:
                continue
            if not s:
                continue
# Try the first path segment if present
            seg = s.split("/", 1)[0]
            m = re.search(r"entry\s*(\d+)", seg, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"entry\s*(\d+)", s, flags=re.IGNORECASE)
            if m:
                return m.group(1)
# Fallback
        try:
            if line is not None and hasattr(line, "get_label"):
                return str(line.get_label() or key)
        except Exception:
            pass
        return str(key)


    def update_pass_button_state(self):
        try:
            cond_sum = bool(getattr(self, "chk_sum", None) and self.chk_sum.isChecked())

            # Count only curves that are actually part of the current Processed Data
            # selection. ``raw_visibility`` can retain stale/auxiliary keys, which used
            # to make Pass appear disabled even when exactly one processed curve was
            # checked.
            try:
                if hasattr(self, "_visible_processed_keys"):
                    vc = len(self._visible_processed_keys())
                else:
                    pdata = getattr(self, "plot_data", {}) or {}
                    vis = getattr(self, "raw_visibility", {}) or {}
                    vc = sum(1 for key in pdata if vis.get(key, False))
            except Exception:
                vc = self.visible_curves_count()

            group_cond = False
            try:
                if (not cond_sum) and vc >= 2:
                    mode = str(getattr(self, "combo_bg").currentText()) if hasattr(self, "combo_bg") else ""
                    if str(mode) in ("Automatic", "Auto") and getattr(self, "chk_show_without_bg", None) is not None and self.chk_show_without_bg.isChecked():
                        cb = getattr(self, "chk_group_bg", None)
                        if cb is not None and cb.isEnabled() and cb.isChecked():
                            group_cond = True
            except Exception:
                group_cond = False

            if getattr(self, "pass_button", None):
                self.pass_button.setEnabled(bool(cond_sum or vc == 1 or group_cond))
        except Exception:
            pass

# _on_group_bg_checkbox_toggled moved to plotting/mixin_group_bg.py

# _set_group_bg_mode moved to plotting/mixin_group_bg.py

# _on_group_bg_slope_checkbox_toggled moved to plotting/mixin_group_bg.py

# _update_group_bg_checkbox_state moved to plotting/mixin_group_bg.py

# _update_group_bg_slope_checkbox_state moved to plotting/mixin_group_bg.py

    def show_about_info(self):
        info_text = (
            "EXACT: Exploration of X-ray Absorption: Characterization and Treatment\n\n"
            f"Software Version: {self.VERSION_NUMBER}\n"
            f"Date: {self.CREATION_DATETIME}\n\n"
            "Created by: Alexei Preobrajenski (MAX IV Laboratory)\n"
            "License: MIT\n\n"
            "EXACT is a Python software package with an interactive graphical interface for browsing, pre-processing, plotting and decomposing X-ray absorption spectra stored in HDF5 files. It was originally developed for data collected at the FlexPES beamline at MAX IV Laboratory."
        )
        box = QMessageBox(self)
        box.setWindowTitle("About EXACT")
        box.setText(info_text)
        try:
            from maxiv_exact.icon import application_icon

            pixmap = application_icon().pixmap(96, 96)
            if not pixmap.isNull():
                box.setIconPixmap(pixmap)
        except Exception:
            pass
        box.exec()

    
    def show_usage_info(self, md_filename: str = "usage_controls.md", window_title: str = "Usage — EXACT"):
        """Show the modeless Help browser with TOC, search, and font-size controls."""
        existing = getattr(self, "_help_dialog", None)
        if existing is not None:
            try:
                if getattr(self, "_help_md_filename", None) == md_filename and existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
                existing.close()
            except Exception:
                pass

        try:
            usage_html = get_usage_html(md_filename, 17)
        except Exception:
            usage_html = "<p><b>Help text could not be loaded.</b></p>"

        dlg = QDialog(None, Qt.WindowType.Window)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._help_dialog = dlg
        self._help_md_filename = md_filename

        def _forget_help_dialog(*_args):
            if getattr(self, "_help_dialog", None) is dlg:
                self._help_dialog = None
                self._help_md_filename = None

        dlg.destroyed.connect(_forget_help_dialog)

        help_name = "What is what?" if md_filename == "usage_controls.md" else "How to?"
        pane_subtitle = (
            "GUI elements and analysis methods"
            if md_filename == "usage_controls.md"
            else "Practical workflows and troubleshooting"
        )
        dlg.setWindowTitle(f"Help — {help_name}")
        dlg.resize(1240, 800)
        dlg.setMinimumSize(980, 680)
        dlg.setSizeGripEnabled(True)

        try:
            dlg.setWindowFlags(
                dlg.windowFlags()
                | Qt.WindowType.WindowMinimizeButtonHint
                | Qt.WindowType.WindowMaximizeButtonHint
                | Qt.WindowType.WindowCloseButtonHint
            )
        except Exception:
            pass

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QWidget(dlg)
        header.setObjectName("helpHeader")
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setMaximumHeight(44)
        header.setStyleSheet(
            "QWidget#helpHeader { background: palette(alternate-base); border: 1px solid palette(mid); }"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 8, 5)
        header_layout.setSpacing(8)

        pane_title = QLabel(pane_subtitle)
        pane_title.setObjectName("helpPaneTitle")
        pane_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        pane_title.setStyleSheet(
            "QLabel#helpPaneTitle { font-weight: 700; font-style: italic; "
            "color: palette(link); padding: 0; }"
        )
        header_layout.addWidget(pane_title)
        header_layout.addStretch(1)

        header_layout.addWidget(QLabel("Font size:"))
        font_spin = QSpinBox()
        font_spin.setRange(8, 28)
        font_spin.setSingleStep(1)
        font_spin.setValue(17)
        font_spin.setToolTip("Set the base Help text size. Headings and navigation scale with it.")
        header_layout.addWidget(font_spin)

        header_layout.addSpacing(10)
        header_layout.addWidget(QLabel("Find:"))
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search help...")
        try:
            search_edit.setClearButtonEnabled(True)
        except Exception:
            pass
        search_edit.setToolTip("Press Enter for next, Shift+Enter for previous.")
        search_edit.setMinimumWidth(220)
        header_layout.addWidget(search_edit)

        prev_btn = QPushButton("Prev")
        prev_btn.setToolTip("Find the previous match.")
        header_layout.addWidget(prev_btn)
        next_btn = QPushButton("Next")
        next_btn.setToolTip("Find the next match.")
        header_layout.addWidget(next_btn)
        layout.addWidget(header, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal, dlg)

        toc_panel = QWidget()
        toc_layout = QVBoxLayout(toc_panel)
        toc_layout.setContentsMargins(0, 0, 0, 0)
        toc_layout.setSpacing(5)
        toc_title = QLabel("Table of Contents")
        toc_title.setObjectName("tocTitle")
        toc_title.setStyleSheet(
            "QLabel#tocTitle { font-weight: 700; color: palette(link); "
            "background: palette(button); border: 1px solid palette(mid); padding: 5px 7px; }"
        )
        toc_layout.addWidget(toc_title)

        toc = QTreeWidget()
        toc.setHeaderHidden(True)
        toc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        toc.setMinimumWidth(255)
        toc_layout.addWidget(toc, 1)

        def _set_toc_style(px: int):
            try:
                base = int(px)
            except Exception:
                base = 17
            sizes = {
                1: min(20, max(12, round(base * 0.84))),
                2: min(18, max(11, round(base * 0.76))),
                3: min(16, max(10, round(base * 0.68))),
            }
            toc_title_font = QFont(toc_title.font())
            toc_title_font.setPointSize(sizes[1])
            toc_title_font.setBold(True)
            toc_title.setFont(toc_title_font)
            pane_title_font = QFont(pane_title.font())
            pane_title_font.setPointSize(sizes[1])
            pane_title_font.setBold(True)
            pane_title_font.setItalic(True)
            pane_title.setFont(pane_title_font)
            try:
                toc.setStyleSheet(
                    "QTreeWidget { border: 1px solid palette(mid); padding: 3px; }"
                    "QTreeWidget::item { padding: 3px 4px; }"
                    "QTreeWidget::item:selected {"
                    " background: palette(highlight); color: palette(highlighted-text);"
                    " border-left: 4px solid palette(link);"
                    " }"
                    "QTreeWidget::branch { margin-right: 2px; }"
                )
                root = toc.invisibleRootItem()
                stack = [root.child(i) for i in range(root.childCount())]
                while stack:
                    item = stack.pop()
                    level = int(item.data(0, Qt.ItemDataRole.UserRole.value + 1) or 3)
                    font = QFont(toc.font())
                    font.setPointSize(sizes.get(level, sizes[3]))
                    font.setBold(level == 1)
                    font.setWeight(QFont.Weight.DemiBold if level == 2 else (QFont.Weight.Bold if level == 1 else QFont.Weight.Normal))
                    item.setFont(0, font)
                    if level == 1:
                        item.setSizeHint(0, item.sizeHint(0).expandedTo(item.sizeHint(0)))
                    stack.extend(item.child(i) for i in range(item.childCount()))
            except Exception:
                pass

        _set_toc_style(font_spin.value())

        browser = HelpBrowser()
        browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        browser.setStyleSheet("font-size: 17px; selection-background-color: #ffeb3b; selection-color: #111111;")
        browser.setMinimumWidth(380)
        browser.setHtml(usage_html)

        def _do_help_search(backward: bool = False):
            text = (search_edit.text() or "").strip()
            if not text:
                return
            flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
            try:
                found = browser.find(text, flags)
            except Exception:
                found = False
            if not found:
                try:
                    cursor = browser.textCursor()
                    cursor.movePosition(cursor.End if backward else cursor.Start)
                    browser.setTextCursor(cursor)
                    found = browser.find(text, flags)
                except Exception:
                    found = False
            if not found:
                try:
                    QMessageBox.information(dlg, "Search", f'No matches for "{text}".')
                except Exception:
                    pass

        try:
            next_btn.clicked.connect(lambda: _do_help_search(False))
            prev_btn.clicked.connect(lambda: _do_help_search(True))
            search_edit.returnPressed.connect(lambda: _do_help_search(False))
        except Exception:
            pass

        try:
            sc_find = QShortcut(QKeySequence.StandardKey.Find, dlg)
            sc_find.activated.connect(lambda: (search_edit.setFocus(), search_edit.selectAll()))
            sc_next = QShortcut(QKeySequence("F3"), dlg)
            sc_next.activated.connect(lambda: _do_help_search(False))
            sc_prev = QShortcut(QKeySequence("Shift+F3"), dlg)
            sc_prev.activated.connect(lambda: _do_help_search(True))
            sc_prev_enter = QShortcut(QKeySequence("Shift+Return"), dlg)
            sc_prev_enter.activated.connect(lambda: _do_help_search(True))
        except Exception:
            pass

        try:
            toc.clear()
            current_h1 = None
            current_h2 = None
            for level, title, anchor in getattr(browser, "_help_anchors", []) or []:
                item = QTreeWidgetItem([title])
                item.setData(0, Qt.ItemDataRole.UserRole, anchor)
                item.setData(0, Qt.ItemDataRole.UserRole.value + 1, level)
                if level == 1:
                    toc.addTopLevelItem(item)
                    current_h1 = item
                    current_h2 = None
                elif level == 2:
                    if current_h1 is None:
                        toc.addTopLevelItem(item)
                    else:
                        current_h1.addChild(item)
                    current_h2 = item
                else:
                    parent = current_h2 or current_h1
                    if parent is None:
                        toc.addTopLevelItem(item)
                    else:
                        parent.addChild(item)
            toc.collapseAll()
            if toc.topLevelItemCount():
                toc.topLevelItem(0).setExpanded(True)
            _set_toc_style(font_spin.value())

            _expansion_guard = {"active": False}

            def _keep_one_major_branch(item):
                if _expansion_guard["active"] or item.parent() is not None:
                    return
                _expansion_guard["active"] = True
                try:
                    for idx in range(toc.topLevelItemCount()):
                        other = toc.topLevelItem(idx)
                        if other is not item:
                            other.setExpanded(False)
                finally:
                    _expansion_guard["active"] = False

            toc.itemExpanded.connect(_keep_one_major_branch)

            def _jump_to_section(item, _col=0):
                anchor = item.data(0, Qt.ItemDataRole.UserRole)
                if anchor:
                    browser.scrollToAnchor(str(anchor))
            toc.itemClicked.connect(_jump_to_section)
        except Exception:
            pass

        splitter.addWidget(toc_panel)
        splitter.addWidget(browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([390, 830])
        layout.addWidget(splitter, 1)

        def _apply_help_font(px: int):
            try:
                px = int(px)
            except Exception:
                px = 17
            try:
                browser.setStyleSheet(f"font-size: {px}px;")
                browser.setHtml(get_usage_html(md_filename, px))
            except Exception:
                pass
            try:
                _set_toc_style(px)
            except Exception:
                pass

        font_spin.valueChanged.connect(_apply_help_font)
        dlg.show()
        try:
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass



    def show_whats_new_info(self, max_versions: int = 5):
        """Show a 'What's new' dialog built from docs/CHANGELOG.md.

        The TOC lists the latest versions (H3 headings). If the newest changelog
        entry does not match the installed package version, an apology message
        is shown (to avoid confusion).
        """
        try:
            from .. import __version__
            current_version = str(__version__)
        except Exception:
            current_version = ""

        try:
            usage_html, latest_version = get_whats_new_payload(current_version=current_version, max_versions=max_versions)
        except Exception:
            usage_html, latest_version = ("<p><b>Changelog could not be loaded.</b></p>", "")

        # If changelog does not start with the current version, warn the user.
        try:
            if current_version and latest_version and str(latest_version).strip() != str(current_version).strip():
                QMessageBox.information(
                    self,
                    "What's new?",
                    f"Sorry — the newest changelog entry is {latest_version}, but this app version is {current_version}. "
                    "The 'What's new' view may not reflect the exact installed version."
                )
        except Exception:
            pass

        # Reuse the same dialog layout as Usage (TOC/search/font-size)
        dlg = QDialog(self)
        dlg.setWindowTitle("What's new — EXACT")
        dlg.resize(900, 650)
        dlg.setSizeGripEnabled(True)

        try:
            dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        except Exception:
            pass

        layout = QVBoxLayout(dlg)

        # --- Controls row: font size + search
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)

        controls_row.addWidget(QLabel("Font size:"))
        font_spin = QSpinBox()
        font_spin.setRange(8, 28)
        font_spin.setSingleStep(1)
        font_spin.setValue(18)
        font_spin.setToolTip("Set the base Help text size. Headings and navigation scale with it.")
        controls_row.addWidget(font_spin)

        controls_row.addSpacing(12)
        controls_row.addWidget(QLabel("Find:"))

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search…")
        try:
            search_edit.setClearButtonEnabled(True)
        except Exception:
            pass
        search_edit.setToolTip("Press Enter for next, Shift+Enter for previous.")
        search_edit.setMinimumWidth(220)
        controls_row.addWidget(search_edit)

        prev_btn = QPushButton("Prev")
        prev_btn.setToolTip("Find the previous match.")
        controls_row.addWidget(prev_btn)

        next_btn = QPushButton("Next")
        next_btn.setToolTip("Find the next match.")
        controls_row.addWidget(next_btn)

        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, dlg)

        toc = QTreeWidget()
        toc.setHeaderHidden(True)
        toc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        def _set_toc_style(px: int):
            try:
                px = int(px)
            except Exception:
                px = 14
            try:
                toc.setStyleSheet(
                    "QTreeWidget {"
                    f" font-size: {px}px;"
                    " }"
                    "QTreeWidget::item { color: palette(link); }"
                    "QTreeWidget::item:selected { color: palette(text); }"
                )
            except Exception:
                pass

        _set_toc_style(font_spin.value())
        toc.setMinimumWidth(200)
        toc.setMaximumWidth(360)

        browser = HelpBrowser()
        browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        browser.setStyleSheet("font-size: 18px; selection-background-color: #ffeb3b; selection-color: #111111;")
        browser.setHtml(usage_html)

        def _do_help_search(backward: bool = False):
            text = (search_edit.text() or "").strip()
            if not text:
                return
            flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
            try:
                found = browser.find(text, flags)
            except Exception:
                found = False

            if not found:
                try:
                    cursor = browser.textCursor()
                    cursor.movePosition(cursor.End if backward else cursor.Start)
                    browser.setTextCursor(cursor)
                    found = browser.find(text, flags)
                except Exception:
                    found = False

            if not found:
                try:
                    QMessageBox.information(dlg, "Search", f'No matches for "{text}".')
                except Exception:
                    pass

        def _search_next():
            _do_help_search(backward=False)

        def _search_prev():
            _do_help_search(backward=True)

        next_btn.clicked.connect(_search_next)
        prev_btn.clicked.connect(_search_prev)

        def _on_return_pressed():
            # Enter: next; Shift+Enter: previous
            try:
                if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                    _search_prev()
                else:
                    _search_next()
            except Exception:
                _search_next()

        search_edit.returnPressed.connect(_on_return_pressed)

        # Ctrl+F focuses search
        try:
            QShortcut(QKeySequence.StandardKey.Find, dlg, activated=lambda: search_edit.setFocus())
        except Exception:
            pass

        # Build TOC from extracted heading anchors (H1/H2/H3)
        try:
            toc.clear()
            current_h1 = None
            current_h2 = None

            for level, title, anchor in getattr(browser, "_help_anchors", []) or []:
                item = QTreeWidgetItem([title])
                item.setData(0, Qt.ItemDataRole.UserRole, anchor)

                try:
                    f = toc.font()
                    if level in (1, 2):
                        f.setBold(True)
                    else:
                        f.setBold(False)
                    item.setFont(0, f)
                except Exception:
                    pass

                if level == 1:
                    toc.addTopLevelItem(item)
                    current_h1 = item
                    current_h2 = None
                elif level == 2:
                    if current_h1 is None:
                        toc.addTopLevelItem(item)
                    else:
                        current_h1.addChild(item)
                    current_h2 = item
                else:
                    parent = current_h2 or current_h1
                    if parent is None:
                        toc.addTopLevelItem(item)
                    else:
                        parent.addChild(item)

            toc.expandAll()

            def _jump_to_section(item, _col=0):
                anchor = item.data(0, Qt.ItemDataRole.UserRole)
                if anchor:
                    browser.scrollToAnchor(str(anchor))

            toc.itemClicked.connect(_jump_to_section)
        except Exception:
            pass

        splitter.addWidget(toc)
        splitter.addWidget(browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 640])

        layout.addWidget(splitter)

        def _apply_font(px: int):
            try:
                px = int(px)
            except Exception:
                px = 18
            try:
                browser.setStyleSheet(f"font-size: {px}px;")
            except Exception:
                pass
            _set_toc_style(max(10, int(px * 0.78)))

        font_spin.valueChanged.connect(_apply_font)

        dlg.exec()
    def clear_all_except_plotted(self):
        if hasattr(self, "tree"):
            for i in range(self.tree.topLevelItemCount()):
                self.recursive_uncheck(self.tree.topLevelItem(i), 1)
        if hasattr(self, "raw_tree"):
            for i in range(self.raw_tree.topLevelItemCount()):
                self.recursive_uncheck(self.raw_tree.topLevelItem(i), 0)

        self.raw_tree_reset = False
        self.raw_visibility.clear()
        self.region_states.clear()
        self.proc_region_states.clear()
        self.plot_data.clear()
        try:
            if hasattr(self, "_raw_key_sources"):
                self._raw_key_sources.clear()
        except Exception:
            pass
        self.energy_cache.clear()
        self.cb_all_tey.setChecked(False)
        self.cb_all_pey.setChecked(False)
        self.cb_all_tfy.setChecked(False)
        self.cb_all_pfy.setChecked(False)
        self.combo_bg.setCurrentIndex(0)
        self.spin_preedge.setValue(5)
        self.chk_normalize.setChecked(False)
        self.combo_norm.setEnabled(False)

# Pick default I0 channel according to channel mapping (beamline profile).
        defaults = ["b107a_em_03_ch2", "b107a_em_04_ch2", "Pt_No"]
        try:
            cc = getattr(self, "channel_config", None)
            if cc is not None:
                cands = cc.get_candidates("I0")
                if cands:
                    defaults = list(cands)
        except Exception:
            pass
        for default in defaults:
            idx = self.combo_norm.findText(str(default))
            if idx != -1:
                self.combo_norm.setCurrentIndex(idx)
                break
        fm = self.combo_norm.fontMetrics()
        self.combo_norm.setMinimumWidth(fm.boundingRect(self.combo_norm.currentText()).width() + 20)

        self.chk_sum.setChecked(False)
        self.chk_show_without_bg.setChecked(False)
        self.reset_manual_mode()
        self.scalar_display_raw.setText("")
        self.update_plot_raw()
        self.update_plot_processed()
        self.update_pass_button_state()
        self.raw_tree.repaint()

    def clear_all(self):
        if hasattr(self, "tree"):
            for i in range(self.tree.topLevelItemCount()):
                self.recursive_uncheck(self.tree.topLevelItem(i), 1)
        self.plot_data.clear()
        self.energy_cache.clear()
        self.cb_all_tey.setChecked(False)
        self.cb_all_pey.setChecked(False)
        self.cb_all_tfy.setChecked(False)
        self.cb_all_pfy.setChecked(False)
        self.region_states.clear()
        self.proc_region_states.clear()
        self.update_plot_raw()
        self.update_plot_processed()
        self.combo_bg.setCurrentIndex(0)
        self.chk_normalize.setChecked(False)
        self.chk_sum.setChecked(False)
        self.chk_show_without_bg.setChecked(False)
        self.reset_manual_mode()
        self.scalar_display_raw.setText("")
# Clear plotted data (keep grid settings like the "Clear Plotted" button)
        try:
            self.clear_plotted_data()
        except Exception:
# Fallback: minimal clear if helper is unavailable
            self.plotted_ax.clear()
            self.plotted_ax.set_xlabel("Photon energy (eV)")
            self.plotted_ax.set_ylabel("XAS intensity (arb. units)")
            self.canvas_plotted_fig.tight_layout()
            self.canvas_plotted.draw()
            self.plotted_curves.clear()
            self.plotted_lines.clear()
            self.plotted_list.clear()
            try:
                self.custom_labels.clear()
            except Exception:
                pass
            self.original_line_data.clear()
        self.update_pass_button_state()
        # A cleared session starts again from the Raw Data workflow.
        try:
            self.data_tabs.setCurrentIndex(0)
        except Exception:
            pass

# ------------ Left tree interactions ------------ / (moved to plotting: toggle_plot)

# (moved to plotting: display_data)

# (moved to plotting: plot_curves)

# (moved to plotting: update_plot_raw)

# (moved to plotting: _plot_multiple_no_bg)

# (moved to plotting: _visible_processed_keys)

# (moved to plotting: _get_drawn_processed_xy)

# _compute_group_auto_backgrounds moved to plotting/mixin_group_bg.py

# _group_equalize_area_jump_and_zero_preedge moved to plotting/mixin_group_bg.py

# _plot_multiple_with_group_auto_bg moved to plotting/mixin_group_bg.py

    def on_curve_remove_requested(self, key):
        """Handle request to remove a plotted curve from list and axes.

        Shows a confirmation dialog and, on acceptance, removes the
        corresponding line and updates Waterfall / legend layout.
        """
# Confirm with the user
        reply = QMessageBox.question(
            self,
            "Remove curve",
            "Do you want to remove this curve?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

# Remove from stored structures
        line = self.plotted_lines.pop(key, None) if hasattr(self, "plotted_lines") else None
        if line is not None:
            try:
                line.remove()
            except Exception:
                pass

        if hasattr(self, "plotted_curves"):
            try:
                self.plotted_curves.discard(key)
            except Exception:
                pass

        if hasattr(self, "original_line_data"):
            try:
                self.original_line_data.pop(key, None)
            except Exception:
                pass

        if hasattr(self, "custom_labels"):
            try:
# Preserve labels for synthetic sum curves; otherwise their / user-provided names would revert to the generic "sum" when
                parts = str(key).split("##", 1)
                is_sum = False
                if len(parts) == 2:
                    try:
                        _abs, h5 = parts
                        is_sum = str(h5).lstrip("/").startswith("__SUM__/")
                    except Exception:
                        is_sum = False
                if not is_sum:
                    self.custom_labels.pop(key, None)
            except Exception:
                pass

# Remove the corresponding list item
        if hasattr(self, "plotted_list"):
            try:
                for i in range(self.plotted_list.count()):
                    item = self.plotted_list.item(i)
                    widget = self.plotted_list.itemWidget(item)
                    if widget and getattr(widget, "key", None) == key:
                        self.plotted_list.takeItem(i)
                        break
            except Exception:
                pass

# Recompute Waterfall layout (which also rescales axes)
        try:
            if hasattr(self, "recompute_waterfall_layout"):
                self.recompute_waterfall_layout()
            else:
# Fallback: at least rescale axes and redraw
                if hasattr(self, "rescale_plotted_axes"):
                    self.rescale_plotted_axes()
                if hasattr(self, "canvas_plotted"):
                    self.canvas_plotted.draw()
        except Exception:
            pass

# Update legend to reflect remaining curves
        try:
            if hasattr(self, "update_legend"):
                self.update_legend()
        except Exception:
            pass


# ------------ Right-panel trees (raw/proc) ------------

