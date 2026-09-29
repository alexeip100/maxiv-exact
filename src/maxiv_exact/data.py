
"""Auto-generated DataMixin extracted from ui.py."""
import os
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")  # allow concurrent readers before h5py import
import time
import h5py
import numpy as np
import re
import logging
import json
import sys
from . import hdf5_loading as h5load
logger = logging.getLogger(__name__)
from importlib.resources import files
from PyQt6.QtWidgets import QApplication, QFileDialog, QTreeWidgetItem, QDialog, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QProcess



class DataMixin:
    def _ensure_raw_key_sources(self):
        """Ensure the raw-plot key → sources map exists.

        We use this to keep overlapping selection mechanisms independent:
          - role checkboxes (All TEY/PEY/TFY/PFY)
          - "All in channel" selection
          - manual per-dataset checks in the HDF5 tree

        Each plotted curve key ("abs_path##hdf5_path") can have multiple
        sources. Removing one source should not remove the curve if another
        source still requests it.
        """
        if not hasattr(self, "_raw_key_sources") or not isinstance(getattr(self, "_raw_key_sources"), dict):
            self._raw_key_sources = {}

    def _add_raw_key_source(self, key: str, source: str) -> None:
        self._ensure_raw_key_sources()
        try:
            s = self._raw_key_sources.get(key)
            if not isinstance(s, set):
                s = set()
            s.add(str(source))
            self._raw_key_sources[key] = s
        except Exception:
            pass

    def _remove_raw_key_source(self, key: str, source: str) -> bool:
        """Remove a source from a key. Returns True if the key should be deleted."""
        self._ensure_raw_key_sources()
        try:
            s = self._raw_key_sources.get(key)
            if isinstance(s, set):
                s.discard(str(source))
                if not s:
                    self._raw_key_sources.pop(key, None)
                    return True
                self._raw_key_sources[key] = s
                return False
            # If we had no tracking info, fall back to "delete".
            return True
        except Exception:
            return True

    def _iter_tree_items(self):
        """Yield all QTreeWidgetItems from the main HDF5 structure tree."""
        tree = getattr(self, "tree", None)
        if tree is None:
            return

        def _walk(item):
            yield item
            for i in range(item.childCount()):
                yield from _walk(item.child(i))

        for i in range(tree.topLevelItemCount()):
            yield from _walk(tree.topLevelItem(i))

    def _normalize_hdf5_key(self, hdf5_key):
        """Return the HDF5-relative path part from tree/legacy payloads."""
        return h5load.normalize_hdf5_path(
            hdf5_key,
            known_file_paths=getattr(self, "hdf5_files", {}),
        )

    def _uncheck_tree_items_for_filter(self, filter_str: str) -> None:
        """Uncheck matching items in the left HDF5 tree.

        Used to keep the tree state consistent when a bulk selection mechanism
        removes curves.
        """
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        try:
            tree.blockSignals(True)
            for item in self._iter_tree_items() or []:
                try:
                    payload = h5load.split_tree_payload(
                        item.data(0, Qt.ItemDataRole.UserRole),
                        known_file_paths=getattr(self, "hdf5_files", {}) or {},
                    )
                    if payload is None:
                        continue
                    _abs_path, hdf5_path = payload
                    if not isinstance(hdf5_path, str):
                        continue
                    if filter_str and filter_str in hdf5_path and item.checkState(0) == Qt.CheckState.Checked:
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                except Exception:
                    continue
        finally:
            try:
                tree.blockSignals(False)
            except Exception:
                pass

    def clear_group_visibility(self, filter_str: str) -> None:
        """Remove all curves matching filter_str, regardless of their source.

        Also unchecks matching items in the left tree to keep UI consistent.
        """
        self._ensure_raw_key_sources()
        try:
            for key in list(getattr(self, "plot_data", {}).keys()):
                try:
                    parts = key.split("##", 1)
                    if len(parts) != 2:
                        continue
                    _abs_path, hdf5_path = parts
                    if filter_str and filter_str in hdf5_path:
                        self.plot_data.pop(key, None)
                        self.raw_visibility.pop(key, None)
                        self._raw_key_sources.pop(key, None)
                except Exception:
                    continue
        finally:
            try:
                self._uncheck_tree_items_for_filter(filter_str)
            except Exception:
                pass
            try:
                self.update_plot_raw()
            except Exception:
                pass
            try:
                self.update_pass_button_state()
            except Exception:
                pass
    def _open_h5_read(self, path, retries: int = 3):
        """
        Open HDF5 file for reading with SWMR and retry a few times if busy.
        This helps tolerate concurrent writes by another process.
        """

        last_error = None
        for i in range(max(1, int(retries))):
            try:
                # Try modern SWMR-compatible open
                logger.debug("trying SWMR=true, locking=false")
                return h5py.File(path, "r", swmr=True, libver="latest", locking=False)
                # return h5py.File(path, "r", libver="latest", locking=False)
            except TypeError as e:
                # Older h5py: swmr/libver not supported; fall back safely
                logger.debug("trying defaults (TypeError): %s", e)
                return h5py.File(path, "r")
            except OSError as e:
                # Common transient case: file temporarily locked or being written
                last_error = e
                time.sleep(0.05 * (i + 1))  # short exponential backoff
            except Exception as e:
                last_error = e
                time.sleep(0.05 * (i + 1))

        # Final fallback: try without SWMR, even if locked=False only
        try:
            logger.debug("trying locking=False, last_error=%s", last_error)
            return h5py.File(path, "r", locking=False)
        except Exception as e:
            # Give up after retries
            raise last_error or e

    def group_datasets(self, include_sums: bool = True):
        """Group currently loaded 1D datasets into energy "regions".

        Default behavior (fallback): regions are determined from the measured
        energy axis start/end (pcap_energy_av via lookup_energy).

        Improved behavior (preferred): if the HDF5 entry contains a scan "title"
        string that encodes the intended scan window (E_start, E_end), then we
        group by those intended endpoints instead of the measured endpoints.

        This helps collapse multiple interrupted scans (same intended start/end
        but truncated measured end) into a single region labeled as
        "(E_start – unfinished)".

        If title parsing fails for an entry, we fall back to the measured
        start/end behavior.

        Returns
        -------
        list of dict
            Each dict has keys:
              - "keys": list of dataset keys
              - "min": representative region start (float, used for sorting)
              - "max": representative region end (float, used for sorting)
              - "label": pre-formatted label for the region (optional)
              - "unfinished": bool (optional)
        """

        tol_E = 0.01  # eV tolerance for grouping endpoints

        # Region overrides (used for synthetic curves like summed sub-groups)
        overrides = getattr(self, "_region_overrides", {}) or {}

        # Cache parsed intended endpoints per (abs_path, entry_name)
        if not hasattr(self, "_intent_cache"):
            self._intent_cache = {}

        float_re = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

        def _safe_float(tok: str):
            m = float_re.search(str(tok))
            return float(m.group(0)) if m else None

        def _extract_entry_name(hdf5_path: str):
            p = str(hdf5_path).lstrip("/")
            if not p:
                return None
            return p.split("/", 1)[0]

        def _read_entry_title(abs_path: str, entry_name: str):
            cache_key = (abs_path, entry_name)
            if cache_key in self._intent_cache:
                return self._intent_cache[cache_key]

            title = None
            try:
                with self._open_h5_read(abs_path) as f:
                    # Typical: /entryXXXX/title as a dataset
                    if entry_name in f:
                        g = f[entry_name]
                        if "title" in g:
                            try:
                                t = g["title"][()]
                                if isinstance(t, bytes):
                                    title = t.decode("utf-8", errors="ignore")
                                else:
                                    title = str(t)
                            except Exception:
                                title = None
                        # Sometimes "title" can be an attribute
                        if title is None and hasattr(g, "attrs"):
                            try:
                                t = g.attrs.get("title", None)
                                if isinstance(t, bytes):
                                    title = t.decode("utf-8", errors="ignore")
                                elif t is not None:
                                    title = str(t)
                            except Exception:
                                title = None
            except Exception:
                title = None

            self._intent_cache[cache_key] = title
            return title

        def _parse_intended_energy(title: str, e_start_meas: float, e_end_meas: float):
            """Parse intended (E_start, E_end) from a scan title.

            We look for patterns: <motor_name> <float> <float>. The title often
            contains two motors; we try to pick the energy motor based on name
            heuristics and closeness to measured start.
            """
            if not title:
                return None

            toks = str(title).split()
            triplets = []  # (motor, e0, e1)
            for i in range(len(toks) - 2):
                motor = toks[i]
                e0 = _safe_float(toks[i + 1])
                e1 = _safe_float(toks[i + 2])
                if e0 is None or e1 is None:
                    continue
                # Basic sanity
                if not (np.isfinite(e0) and np.isfinite(e1)):
                    continue
                if abs(e1 - e0) < 1e-6:
                    continue
                triplets.append((motor, float(e0), float(e1)))

            if not triplets:
                return None

            # Prefer motors that look like energy/mono
            preferred = []
            for motor, e0, e1 in triplets:
                m = str(motor).lower()
                if ("mono" in m) or ("energy" in m) or (m in {"e", "en"}):
                    preferred.append((motor, e0, e1))
            candidates = preferred if preferred else triplets

            # Choose candidate with closest start to measured start
            best = None
            best_cost = None
            for motor, e0, e1 in candidates:
                es, ee = (e0, e1) if e1 >= e0 else (e1, e0)
                # Energy plausibility
                if ee <= es:
                    continue
                if not (0.0 <= es <= 50000.0 and 0.0 <= ee <= 50000.0):
                    continue
                cost = abs(es - e_start_meas)
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = (es, ee)
            return best

        def _estimate_step(x_use: np.ndarray):
            try:
                xf = x_use[np.isfinite(x_use)]
                if xf.size < 3:
                    return 0.0
                d = np.diff(xf)
                d = d[np.isfinite(d)]
                # keep positive diffs only
                d = d[d > 0]
                if d.size == 0:
                    return 0.0
                # remove obvious outliers
                med = float(np.median(d))
                d = d[(d > 0.1 * med) & (d < 10 * med)]
                return float(np.median(d)) if d.size else med
            except Exception:
                return 0.0

        # Collect items as (key, region_start, region_end, label, unfinished_flag)
        items = []
        def _is_sum_hdf5_path(hdf5_path: str) -> bool:
            try:
                p = str(hdf5_path).lstrip("/")
                return p.startswith("__SUM__/")
            except Exception:
                return False

        for key, y_data in getattr(self, "plot_data", {}).items():
            try:
                parts = str(key).split("##", 1)
                if len(parts) != 2:
                    continue
                abs_path, hdf5_path = parts

                # Use explicit region override when provided (keeps summed curves in the same Region as sources)
                if include_sums and key in overrides:
                    try:
                        ov = overrides.get(key) or {}
                        region_start = float(ov.get("start"))
                        region_end = float(ov.get("end"))
                        unfinished = bool(ov.get("unfinished", False))
                        label = str(ov.get("label") or "")
                        if not label:
                            if unfinished:
                                label = f"({region_start:.3f}–unfinished)"
                            else:
                                label = f"({region_start:.3f}–{region_end:.3f} eV)"
                        items.append((key, region_start, region_end, label, unfinished))
                        continue
                    except Exception:
                        # If override is malformed, fall back to computed behavior
                        pass
                if not include_sums and _is_sum_hdf5_path(hdf5_path):
                    continue
                parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                entry_name = _extract_entry_name(hdf5_path)
                if not entry_name:
                    continue

                if y_data is None:
                    continue
                y_arr = np.asarray(y_data).ravel()
                if y_arr.size == 0:
                    continue

                # Measured energy axis (prefers pcap_energy_av)
                try:
                    x_data = lookup_energy(self, abs_path, parent, int(y_arr.size))
                except Exception:
                    x_data = np.arange(int(y_arr.size), dtype=float)
                if getattr(x_data, "size", 0) == 0:
                    continue
                x_arr = np.asarray(x_data).ravel()

                n = int(min(x_arr.size, y_arr.size))
                if n <= 0:
                    continue
                x_use = x_arr[:n]
                finite = np.isfinite(x_use)
                if not np.any(finite):
                    x_use = np.arange(n, dtype=float)
                    finite = np.isfinite(x_use)

                i0 = int(np.argmax(finite))
                i1 = int(len(finite) - 1 - np.argmax(finite[::-1]))
                e_start_meas = float(x_use[i0])
                e_end_meas = float(x_use[i1])
                if not (np.isfinite(e_start_meas) and np.isfinite(e_end_meas)):
                    continue
                if e_end_meas < e_start_meas:
                    e_start_meas, e_end_meas = e_end_meas, e_start_meas

                step = _estimate_step(x_use)
                tol_start = max(0.02, 2.0 * step) if step > 0 else 0.02
                tol_end_match = max(0.05, 3.0 * step) if step > 0 else 0.05
                tol_unfinished = max(0.2, 5.0 * step) if step > 0 else 0.2

                # Intended endpoints from title (if available)
                intended = None
                title = _read_entry_title(abs_path, entry_name)
                if title:
                    intended = _parse_intended_energy(title, e_start_meas, e_end_meas)
                    # Validate intention vs measured start
                    if intended is not None:
                        es_i, ee_i = intended
                        if abs(es_i - e_start_meas) > tol_start:
                            intended = None
                        # If measured end is *above* intended end by too much, likely wrong parse
                        if intended is not None and (e_end_meas > ee_i + tol_end_match):
                            intended = None

                if intended is None:
                    # Fallback: group by measured endpoints
                    region_start = e_start_meas
                    region_end = e_end_meas
                    unfinished = False
                    label = f"({region_start:.3f}–{region_end:.3f} eV)"
                else:
                    es_i, ee_i = intended
                    region_start = float(es_i)
                    region_end = float(ee_i)
                    unfinished = (e_end_meas < (ee_i - tol_unfinished))
                    if unfinished:
                        label = f"({region_start:.3f}–unfinished)"
                    else:
                        label = f"({region_start:.3f}–{region_end:.3f} eV)"

                items.append((key, region_start, region_end, label, unfinished))
            except Exception:
                continue

        if not items:
            return []

        # ---- Order-independent tolerance clustering (union-find) ----
        n_items = len(items)
        uf_parent = list(range(n_items))
        uf_rank = [0] * n_items

        def uf_find(i):
            while uf_parent[i] != i:
                uf_parent[i] = uf_parent[uf_parent[i]]
                i = uf_parent[i]
            return i

        def uf_union(a, b):
            ra, rb = uf_find(a), uf_find(b)
            if ra == rb:
                return
            if uf_rank[ra] < uf_rank[rb]:
                uf_parent[ra] = rb
            elif uf_rank[ra] > uf_rank[rb]:
                uf_parent[rb] = ra
            else:
                uf_parent[rb] = ra
                uf_rank[ra] += 1

        # Reduce comparisons by bucketing on start energy
        start_bins = {}
        for i, (_, es, ee, _lbl, unfinished) in enumerate(items):
            b = int(np.floor(es / tol_E))
            for bb in (b - 1, b, b + 1):
                for j in start_bins.get(bb, []):
                    _k2, es2, ee2, _lbl2, unfinished2 = items[j]
                    if unfinished != unfinished2:
                        continue
                    if abs(es - es2) <= tol_E and abs(ee - ee2) <= tol_E:
                        uf_union(i, j)
            start_bins.setdefault(b, []).append(i)

        clusters = {}
        for i, (key, es, ee, lbl, unfinished) in enumerate(items):
            r = uf_find(i)
            clusters.setdefault(r, {"keys": [], "starts": [], "ends": [], "labels": [], "unfinished": unfinished})
            clusters[r]["keys"].append(key)
            clusters[r]["starts"].append(es)
            clusters[r]["ends"].append(ee)
            clusters[r]["labels"].append(lbl)

        out = []
        for c in clusters.values():
            ref_start = float(np.median(c["starts"]))
            ref_end = float(np.median(c["ends"]))
            unfinished = bool(c.get("unfinished", False))
            # Prefer the most common label (stable) rather than formatting anew
            label = None
            try:
                from collections import Counter
                label = Counter(c.get("labels", [])).most_common(1)[0][0]
            except Exception:
                label = None

            d = {"keys": c["keys"], "min": ref_start, "max": ref_end}
            if label:
                d["label"] = label
            if unfinished:
                d["unfinished"] = True
            out.append(d)

        out.sort(key=lambda g: (g.get("min", 0.0), g.get("unfinished", False), g.get("max", 0.0)))
        return out

    def set_group_visibility(self, filter_str: str, visible: bool, source: str = "group"):
        """
        Show or hide all 1D datasets across all opened HDF5 files whose HDF5
        relative path contains `filter_str` (typically the channel name).

        On visible=True:
            - Read each matching 1D dataset once
            - Store into self.plot_data[abs_path##relpath]
            - Mark self.raw_visibility[...] = True

        On visible=False:
            - Remove matching keys from self.plot_data and self.raw_visibility

        Notes:
            - Does NOT touch the 'All in channel' combobox or its checkbox.
            - Uses a re-entrancy guard to avoid being called recursively.
            - Assumes helpers/attrs: self.hdf5_files (dict of abs paths),
              self._open_h5_read(path), self.update_plot_raw(), self.update_pass_button_state(),
              and dicts self.plot_data, self.raw_visibility.
        """
        self._ensure_raw_key_sources()

        # Re-entrancy guard
        if getattr(self, "_in_set_group_visibility", False):
            return
        self._in_set_group_visibility = True

        try:
            files = list(getattr(self, "hdf5_files", {}).keys())
            if not files:
                # Nothing to do
                return

            for abs_path in files:
                try:
                    with self._open_h5_read(abs_path) as f:
                        visit_counter = [0]

                        def _visit(name, obj):
                            try:
                                visit_counter[0] += 1
                                if visit_counter[0] % 25 == 0:
                                    try:
                                        QApplication.processEvents()
                                    except Exception:
                                        pass
                                import h5py
                                # Only 1D datasets
                                if not isinstance(obj, h5py.Dataset):
                                    return
                                if getattr(obj, "ndim", 0) != 1:
                                    return
                                if getattr(obj, "size", 0) == 0:
                                    return
                                # Prefer data from the "measurement" group only; ignore "plot_1" and other derived groups.
                                norm = "/" + str(name).strip("/") + "/"
                                if "/measurement/" not in norm:
                                    return
                                # Require channel substring match in relpath
                                if filter_str and filter_str not in name:
                                    return

                                key = f"{abs_path}##{name}"
                                if visible:
                                    # Read y-array; x-array handling is elsewhere (e.g., in plotting)
                                    try:
                                        y = obj[()]
                                    except Exception:
                                        return
                                    try:
                                        y = np.asarray(y)
                                    except Exception:
                                        return
                                    if y.ndim != 1 or y.size == 0:
                                        return
                                    # Only populate y if absent; avoid clobbering existing data.
                                    if key not in self.plot_data:
                                        self.plot_data[key] = y
                                    self.raw_visibility[key] = True
                                    self._add_raw_key_source(key, source)
                                else:
                                    # Remove only this source. Delete the key only if no sources remain.
                                    should_delete = self._remove_raw_key_source(key, source)
                                    if should_delete:
                                        self.plot_data.pop(key, None)
                                        self.raw_visibility.pop(key, None)

                            except Exception:
                                # Ignore per-item errors; keep scanning
                                pass

                        f.visititems(_visit)

                except Exception:
                    # Ignore per-file errors; continue with remaining files
                    continue

            # Single refresh at the end for performance and UI stability
            try:
                self.update_plot_raw()
            finally:
                # Keep pass button / other state in sync
                try:
                    self.update_pass_button_state()
                except Exception:
                    pass

        finally:
            self._in_set_group_visibility = False


    def update_file_label(self):
        self.file_label.setText("\n".join(self.hdf5_files.keys()) if self.hdf5_files else "No file open")

    def close_file(self):
    # No persistent h5py.File handles are kept; just clear state
        self.hdf5_files.clear()
        try:
            self._hdf5_all_channel_cache.clear()
        except Exception:
            self._hdf5_all_channel_cache = {}
        self.file_label.setText("No file open")
        self.tree.clear()
        self.plot_data.clear()
        try:
            if hasattr(self, "_raw_key_sources"):
                self._raw_key_sources.clear()
        except Exception:
            pass
        self.energy_cache.clear()
        self.raw_visibility.clear()
        self.update_plot_raw()
        self.update_plot_processed()
        self.combo_bg.setCurrentIndex(0)
        self.combo_poly.setCurrentIndex(0)
        self.chk_normalize.setChecked(False)
        self.chk_sum.setChecked(False)
        self.chk_show_without_bg.setChecked(False)
        self.cb_all_tey.setChecked(False)
        self.cb_all_pey.setChecked(False)
        self.cb_all_tfy.setChecked(False)
        self.cb_all_pfy.setChecked(False)
        self.region_states.clear()
        self.proc_region_states.clear()
        self.reset_manual_mode()
        self.scalar_display_raw.setText("")
        self.plotted_ax.clear()
        self.plotted_ax.set_xlabel("Photon energy (eV)")
        self.plotted_ax.set_ylabel("XAS intensity (arb. units)")
        self.canvas_plotted_fig.tight_layout()
        self.canvas_plotted.draw()
        self.plotted_curves.clear()
        self.plotted_lines.clear()
        self.plotted_list.clear()
        self.original_line_data.clear()
        self.update_file_label()
        self.update_pass_button_state()
        # Ensure the 'All in channel' combo is populated after opening files
        QTimer.singleShot(0, getattr(self, '_refresh_all_in_channel_combo', lambda: None))
        # Refresh 'All in channel' combo and checkbox
        try:
            if hasattr(self, 'combo_all_channel'):
                self.combo_all_channel.clear()
            if hasattr(self, 'cb_all_in_channel'):
                self.cb_all_in_channel.setChecked(False)
            setattr(self, '_last_all_channel_filter', None)
            QTimer.singleShot(0, getattr(self, '_refresh_all_in_channel_combo', lambda: None))
        except Exception:
            pass

    def close_single_hdf5_file(self, abs_path):
        """
        Close a single HDF5 file and remove its data from internal state,
        without affecting other open files.
        """
        try:
            abs_path = os.path.abspath(abs_path)
        except Exception:
            abs_path = str(abs_path)

        # Validate registry
        if not isinstance(getattr(self, "hdf5_files", None), dict):
            return
        if abs_path not in self.hdf5_files:
            return

        # Remove the file from the registry
        try:
            self.hdf5_files.pop(abs_path, None)
        except Exception:
            pass

        # Remove raw/processed data and visibility flags for this file
        try:
            keys_to_remove = [
                key for key in list(getattr(self, "plot_data", {}).keys())
                if isinstance(key, str) and key.startswith(abs_path + "##")
            ]
        except Exception:
            keys_to_remove = []
        for key in keys_to_remove:
            try:
                self.plot_data.pop(key, None)
            except Exception:
                pass
            # Drop intrinsic display name (used for synthetic curves)
            try:
                cdn = getattr(self, "curve_display_names", None)
                if isinstance(cdn, dict):
                    cdn.pop(key, None)
            except Exception:
                pass
            try:
                self.raw_visibility.pop(key, None)
            except Exception:
                pass
            try:
                if hasattr(self, "_raw_key_sources") and isinstance(getattr(self, "_raw_key_sources"), dict):
                    self._raw_key_sources.pop(key, None)
            except Exception:
                pass

        # Drop cached energy arrays for this file
        try:
            cache = getattr(self, "energy_cache", None)
            if isinstance(cache, dict):
                for key in list(cache.keys()):
                    if isinstance(key, str) and key.startswith(abs_path + "::"):
                        cache.pop(key, None)
        except Exception:
            pass

        # Remove curves belonging to this file from the Plotted tab
        try:
            plotted_curves = getattr(self, "plotted_curves", None)
            plotted_lines = getattr(self, "plotted_lines", None)
            plotted_list = getattr(self, "plotted_list", None)
            plotted_metadata = getattr(self, "plotted_metadata", {})
            original_line_data = getattr(self, "original_line_data", {})
            custom_labels = getattr(self, "custom_labels", {})

            keys_for_file = set()

            # Prefer explicit metadata if present
            if isinstance(plotted_metadata, dict):
                for key, meta in list(plotted_metadata.items()):
                    try:
                        if meta.get("source_file") == abs_path:
                            keys_for_file.add(key)
                    except Exception:
                        continue

            # Fallback: match on storage key prefix
            if isinstance(plotted_curves, (set, list)):
                for key in list(plotted_curves):
                    if isinstance(key, str) and key.startswith(abs_path + "##"):
                        keys_for_file.add(key)

            for key in keys_for_file:
                # Remove line from axes
                try:
                    if isinstance(plotted_lines, dict):
                        line = plotted_lines.pop(key, None)
                        if line is not None:
                            try:
                                line.remove()
                            except Exception:
                                pass
                except Exception:
                    pass

                # Remove bookkeeping structures
                try:
                    if isinstance(plotted_curves, set):
                        plotted_curves.discard(key)
                    elif isinstance(plotted_curves, list):
                        if key in plotted_curves:
                            plotted_curves.remove(key)
                except Exception:
                    pass
                try:
                    if isinstance(original_line_data, dict):
                        original_line_data.pop(key, None)
                except Exception:
                    pass
                try:
                    if isinstance(custom_labels, dict):
                        custom_labels.pop(key, None)
                except Exception:
                    pass
                try:
                    if isinstance(plotted_metadata, dict):
                        plotted_metadata.pop(key, None)
                except Exception:
                    pass

                # Remove from the list widget
                try:
                    if plotted_list is not None:
                        from PyQt6.QtCore import Qt as _Qt  # local alias to avoid surprises
                        for row in range(plotted_list.count() - 1, -1, -1):
                            item = plotted_list.item(row)
                            key_role = item.data(_Qt.ItemDataRole.UserRole)
                            widget = plotted_list.itemWidget(item)
                            widget_key = getattr(widget, "key", None) if widget is not None else None
                            if key_role == key or widget_key == key:
                                plotted_list.takeItem(row)
                except Exception:
                    pass
        except Exception:
            pass

        # If no files remain, fall back to the full reset
        try:
            if not self.hdf5_files:
                self.close_file()
                return
        except Exception:
            pass

        # Otherwise, refresh labels and plots
        try:
            self.update_file_label()
        except Exception:
            pass
        try:
            self.update_plot_raw()
        except Exception:
            pass
        try:
            self.update_plot_processed()
        except Exception:
            pass

        # Refresh 'All in channel' controls
        try:
            if hasattr(self, "combo_all_channel"):
                self.combo_all_channel.clear()
            if hasattr(self, "cb_all_in_channel"):
                self.cb_all_in_channel.setChecked(False)
            setattr(self, "_last_all_channel_filter", None)
            QTimer.singleShot(0, getattr(self, "_refresh_all_in_channel_combo", lambda: None))
        except Exception:
            pass

        # Refresh Plotted axes and legend
        try:
            if hasattr(self, "recompute_waterfall_layout"):
                self.recompute_waterfall_layout()
            else:
                if hasattr(self, "rescale_plotted_axes"):
                    self.rescale_plotted_axes()
                if hasattr(self, "canvas_plotted"):
                    self.canvas_plotted.draw()
        except Exception:
            pass
        try:
            if hasattr(self, "update_legend"):
                self.update_legend()
        except Exception:
            pass


    def _is_supported_hdf5_path(self, path) -> bool:
        """Return True for local files with supported HDF5 extensions."""
        return h5load.is_supported_hdf5_file(path)

    def _show_status_message(self, text: str, timeout_ms: int = 4000) -> None:
        """Best-effort status-bar message helper."""
        try:
            self.statusBar().showMessage(str(text), int(timeout_ms))
        except Exception:
            pass

    def _find_loaded_hdf5_by_basename(self, abs_path_or_name):
        """Find an already loaded HDF5 file by file name only, not full path."""
        return h5load.find_loaded_by_basename(
            abs_path_or_name,
            getattr(self, "hdf5_files", {}) or {},
        )

    def _tree_item_for_hdf5_path(self, abs_path):
        """Return the top-level file item for an HDF5 path, if present."""
        try:
            abs_path = h5load.normalize_abs_path(abs_path)
            tree = getattr(self, "tree", None)
            if tree is None:
                return None
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                payload = h5load.split_tree_payload(
                    item.data(0, Qt.ItemDataRole.UserRole),
                    known_file_paths=getattr(self, "hdf5_files", {}) or {},
                )
                if payload is None:
                    continue
                item_abs, item_h5 = payload
                if item_abs == abs_path and not item_h5:
                    return item
        except Exception:
            pass
        return None

    def _update_tree_abs_path(self, item, old_abs_path, new_abs_path) -> None:
        """Update stored abs_path values in an existing HDF5 tree branch."""
        if item is None:
            return
        old_abs_path = h5load.normalize_abs_path(old_abs_path)
        new_abs_path = h5load.normalize_abs_path(new_abs_path)
        try:
            payload = h5load.split_tree_payload(
                item.data(0, Qt.ItemDataRole.UserRole),
                known_file_paths=getattr(self, "hdf5_files", {}) or {},
            )
            if payload is not None:
                item_abs, h5_path = payload
                if item_abs == old_abs_path:
                    item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(new_abs_path, h5_path))
        except Exception:
            pass
        try:
            for i in range(item.childCount()):
                self._update_tree_abs_path(item.child(i), old_abs_path, new_abs_path)
        except Exception:
            pass

    def _remap_storage_key(self, key, old_abs_path, new_abs_path):
        """Replace the abs_path prefix in storage keys of the form abs_path##hdf5_path."""
        return h5load.remap_storage_key(key, old_abs_path, new_abs_path)

    def _remap_path_prefix_dict_keys(self, attr_name: str, old_abs_path: str, new_abs_path: str) -> None:
        """Best-effort remap of dict keys that use the storage-key prefix."""
        try:
            d = getattr(self, attr_name, None)
            if not isinstance(d, dict):
                return
            new_d = {}
            changed = False
            for k, v in d.items():
                nk = self._remap_storage_key(k, old_abs_path, new_abs_path)
                if nk != k:
                    changed = True
                new_d[nk] = v
            if changed:
                setattr(self, attr_name, new_d)
        except Exception:
            pass

    def _replace_source_path_references(self, old_abs_path, new_abs_path) -> None:
        """Best-effort remap when a same-named file is refreshed from a new path.

        The common beamline case refreshes the same file path, so this normally does
        nothing.  If a same-named file is dropped from another folder, remap the most
        important in-memory keys so existing processed/plotted work remains connected
        to the refreshed source where possible.
        """
        try:
            old_abs_path = os.path.abspath(str(old_abs_path))
            new_abs_path = os.path.abspath(str(new_abs_path))
        except Exception:
            old_abs_path = str(old_abs_path)
            new_abs_path = str(new_abs_path)
        if old_abs_path == new_abs_path:
            return

        # File registry
        try:
            if isinstance(getattr(self, "hdf5_files", None), dict):
                self.hdf5_files.pop(old_abs_path, None)
                self.hdf5_files[new_abs_path] = True
        except Exception:
            pass

        # Cached channel metadata follows the source path as well.
        try:
            cache = getattr(self, "_hdf5_all_channel_cache", None)
            if isinstance(cache, dict) and old_abs_path in cache:
                cache[new_abs_path] = cache.pop(old_abs_path)
        except Exception:
            pass

        # Raw/processed/plotted bookkeeping keyed by abs_path##hdf5_path.
        for attr in (
            "plot_data", "raw_visibility", "_raw_key_sources", "curve_display_names",
            "_curve_color_map", "plotted_lines", "original_line_data", "custom_labels",
            "plotted_metadata",
        ):
            self._remap_path_prefix_dict_keys(attr, old_abs_path, new_abs_path)

        # Sets/lists of plotted storage keys.
        try:
            pc = getattr(self, "plotted_curves", None)
            if isinstance(pc, set):
                self.plotted_curves = {self._remap_storage_key(k, old_abs_path, new_abs_path) for k in pc}
            elif isinstance(pc, list):
                self.plotted_curves = [self._remap_storage_key(k, old_abs_path, new_abs_path) for k in pc]
        except Exception:
            pass

        # Energy cache keys use abs_path::parent.
        try:
            cache = getattr(self, "energy_cache", None)
            if isinstance(cache, dict):
                prefix = old_abs_path + "::"
                new_cache = {}
                for k, v in cache.items():
                    if isinstance(k, str) and k.startswith(prefix):
                        new_cache[new_abs_path + k[len(old_abs_path):]] = v
                    else:
                        new_cache[k] = v
                self.energy_cache = new_cache
        except Exception:
            pass

        # Summed curve source lists may contain raw storage keys.
        try:
            sources = getattr(self, "_summed_curve_sources", None)
            if isinstance(sources, dict):
                new_sources = {}
                for k, vals in sources.items():
                    nk = self._remap_storage_key(k, old_abs_path, new_abs_path)
                    try:
                        nvals = [self._remap_storage_key(v, old_abs_path, new_abs_path) for v in vals]
                    except Exception:
                        nvals = vals
                    new_sources[nk] = nvals
                self._summed_curve_sources = new_sources
        except Exception:
            pass

        # Update source_file metadata values and Matplotlib line dataset keys.
        try:
            md = getattr(self, "plotted_metadata", None)
            if isinstance(md, dict):
                for meta in md.values():
                    if isinstance(meta, dict) and meta.get("source_file") == old_abs_path:
                        meta["source_file"] = new_abs_path
        except Exception:
            pass
        try:
            lines = getattr(self, "plotted_lines", None)
            if isinstance(lines, dict):
                for k, line in lines.items():
                    try:
                        if getattr(line, "dataset_key", None) == old_abs_path:
                            line.dataset_key = new_abs_path
                        elif isinstance(getattr(line, "dataset_key", None), str):
                            line.dataset_key = self._remap_storage_key(line.dataset_key, old_abs_path, new_abs_path)
                    except Exception:
                        pass
        except Exception:
            pass

        # Update plotted list item keys and embedded widgets.
        try:
            plotted_list = getattr(self, "plotted_list", None)
            if plotted_list is not None:
                for row in range(plotted_list.count()):
                    item = plotted_list.item(row)
                    if item is None:
                        continue
                    try:
                        key = item.data(Qt.ItemDataRole.UserRole)
                        item.setData(Qt.ItemDataRole.UserRole, self._remap_storage_key(key, old_abs_path, new_abs_path))
                    except Exception:
                        pass
                    try:
                        widget = plotted_list.itemWidget(item)
                        if widget is not None and hasattr(widget, "key"):
                            widget.key = self._remap_storage_key(widget.key, old_abs_path, new_abs_path)
                    except Exception:
                        pass
        except Exception:
            pass

    def _make_hdf5_tree_child(self, abs_path, hdf5_path, display_name, h5_obj):
        """Create a tree item for an HDF5 group/dataset, preserving lazy loading."""
        child_item = QTreeWidgetItem([str(display_name)])
        child_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, hdf5_path))
        try:
            if isinstance(h5_obj, h5py.Group) and h5_obj.keys():
                child_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                child_item.addChild(QTreeWidgetItem(["(click to expand)"]))
            elif isinstance(h5_obj, h5py.Dataset) and h5_obj.ndim == 1:
                key = f"{abs_path}##{hdf5_path}"
                state = Qt.CheckState.Checked if getattr(self, "raw_visibility", {}).get(key, False) else Qt.CheckState.Unchecked
                child_item.setCheckState(0, state)
        except Exception:
            pass
        return child_item

    def _tree_item_has_dummy_child(self, item) -> bool:
        try:
            return item.childCount() == 1 and item.child(0).text(0) == "(click to expand)" and not item.child(0).data(0, Qt.ItemDataRole.UserRole)
        except Exception:
            return False

    def _refresh_loaded_hdf5_tree_branch(self, h5_file, item, abs_path, hdf5_path: str) -> None:
        """Add missing HDF5 children to already-loaded tree branches.

        Existing items, check states, and expanded branches are preserved.  Unexpanded
        lazy branches keep their dummy child; they will load from the refreshed file
        when the user expands them.
        """
        try:
            if hdf5_path:
                if hdf5_path not in h5_file:
                    return
                obj = h5_file[hdf5_path]
            else:
                obj = h5_file
            if not isinstance(obj, (h5py.File, h5py.Group)):
                return
        except Exception:
            return

        # If a non-root branch is still lazy, leave it lazy. Root/file items are
        # refreshed immediately so newly appended entries become visible at once.
        try:
            if hdf5_path and self._tree_item_has_dummy_child(item):
                return
            if self._tree_item_has_dummy_child(item):
                item.removeChild(item.child(0))
        except Exception:
            pass

        existing = {}
        try:
            for i in range(item.childCount()):
                ch = item.child(i)
                payload = h5load.split_tree_payload(
                    ch.data(0, Qt.ItemDataRole.UserRole),
                    known_file_paths=getattr(self, "hdf5_files", {}) or {},
                )
                if payload is not None:
                    existing[payload[1]] = ch
        except Exception:
            existing = {}

        try:
            for name in obj.keys():
                child_path = f"{hdf5_path}/{name}" if hdf5_path else str(name)
                if child_path not in existing:
                    try:
                        item.addChild(self._make_hdf5_tree_child(abs_path, child_path, name, obj[name]))
                    except Exception:
                        pass
                else:
                    child_item = existing.get(child_path)
                    if child_item is not None and child_item.childCount() > 0 and not self._tree_item_has_dummy_child(child_item):
                        self._refresh_loaded_hdf5_tree_branch(h5_file, child_item, abs_path, child_path)
        except Exception:
            pass

    def refresh_hdf5_file(self, existing_abs_path, new_abs_path):
        """Refresh an already loaded same-named HDF5 file in place.

        Existing raw selections and plotted/processed work are kept where possible.
        Newly discovered HDF5 entries/datasets are added to the left tree.  This is
        intended for append-only acquisition files that grow while the GUI is open.
        """
        existing_abs_path = os.path.abspath(str(existing_abs_path))
        new_abs_path = os.path.abspath(str(new_abs_path))

        # Validate readability before changing application state.
        try:
            with self._open_h5_read(new_abs_path) as f:
                has_children = len(f.keys()) > 0
        except Exception as exc:
            raise RuntimeError(f"Could not refresh HDF5 file:\n{new_abs_path}\n\n{exc}") from exc

        item = self._tree_item_for_hdf5_path(existing_abs_path)
        if item is None:
            # Conservative fallback: load normally if the tree item cannot be found.
            return self.load_hdf5_file(new_abs_path)

        try:
            tree = getattr(self, "tree", None)
            if tree is not None:
                tree.blockSignals(True)

            if existing_abs_path != new_abs_path:
                self._replace_source_path_references(existing_abs_path, new_abs_path)
                self._update_tree_abs_path(item, existing_abs_path, new_abs_path)
            else:
                self.hdf5_files[new_abs_path] = True

            item.setText(0, os.path.basename(new_abs_path))
            item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(new_abs_path, ""))
            if has_children:
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                with self._open_h5_read(new_abs_path) as f:
                    self._refresh_loaded_hdf5_tree_branch(f, item, new_abs_path, "")
            item.setExpanded(True)
        finally:
            try:
                tree = getattr(self, "tree", None)
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass

        try:
            self.populate_norm_channels(new_abs_path)
        except Exception:
            pass
        try:
            QTimer.singleShot(0, getattr(self, "_refresh_all_in_channel_combo", lambda: None))
        except Exception:
            pass
        try:
            self.update_file_label()
        except Exception:
            pass
        try:
            self._show_status_message(f"Refreshed {os.path.basename(new_abs_path)}", 4000)
        except Exception:
            pass

    def load_hdf5_paths(self, file_paths, source: str = "dialog") -> None:
        """Load/refresh HDF5 files with new-file disk I/O in a worker thread."""
        paths = list(file_paths or [])
        if not paths:
            return

        # Do not start overlapping HDF5 scans.  This protects both the tree
        # state and network-backed h5py reads while leaving the rest of the GUI
        # responsive.
        process = getattr(self, "_hdf5_load_process", None)
        try:
            if process is not None and process.state() != QProcess.ProcessState.NotRunning:
                self._show_status_message("An HDF5 file is already being loaded.", 4000)
                return
        except Exception:
            pass

        # IMPORTANT: do not touch the filesystem from the GUI thread here.
        # In particular, os.path.isfile()/stat() on Wi-Fi or network shares can
        # block the Qt event loop for seconds before the worker even starts.
        # Validate only the extension/name here; the background process is
        # responsible for opening the file and reporting missing/unreadable paths.
        valid_paths, skipped = h5load.split_supported_hdf5_paths(
            paths,
            dedupe_by_basename=True,
            require_exists=False,
        )
        if not valid_paths:
            if skipped:
                QMessageBox.warning(
                    self,
                    "No HDF5 files loaded",
                    "No supported HDF5 files were found.\n\nSkipped:\n" + "\n".join(skipped),
                )
            return

        duplicates = []
        new_paths = []
        for abs_path in valid_paths:
            existing = self._find_loaded_hdf5_by_basename(abs_path)
            if existing:
                duplicates.append((existing, abs_path))
            else:
                new_paths.append(abs_path)

        # Refresh keeps existing expanded/check-state structure.  Keep that
        # established path synchronous for now; only genuinely new file I/O is
        # moved to the worker thread in this conservative first step.
        refresh_duplicates = False
        if duplicates:
            try:
                names = "\n".join(f"• {os.path.basename(new)}" for _old, new in duplicates)
                reply = QMessageBox.question(
                    self,
                    "Refresh already loaded HDF5 file(s)",
                    "The following HDF5 file name(s) are already loaded:\n\n"
                    f"{names}\n\n"
                    "Refresh them from disk?\n\n"
                    "Existing processed/plotted work will be kept where possible. "
                    "New curves found in the refreshed file(s) will be added.",
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                refresh_duplicates = (reply == QMessageBox.StandardButton.Ok)
            except Exception:
                refresh_duplicates = False

        failures = []
        refreshed_count = 0
        if refresh_duplicates:
            try:
                if hasattr(self, "_begin_busy"):
                    self._begin_busy("Refreshing HDF5 file..." if len(duplicates) == 1 else "Refreshing HDF5 files...")
                for existing_abs, new_abs in duplicates:
                    try:
                        if hasattr(self, "_set_busy_message"):
                            self._set_busy_message(f"Refreshing {os.path.basename(new_abs)}...")
                        self.refresh_hdf5_file(existing_abs, new_abs)
                        refreshed_count += 1
                    except Exception as exc:
                        failures.append(f"{os.path.basename(new_abs)}: {exc}")
            finally:
                try:
                    if hasattr(self, "_end_busy"):
                        self._end_busy()
                except Exception:
                    pass
        elif duplicates:
            skipped.extend(os.path.basename(new_abs) for _existing_abs, new_abs in duplicates)

        if failures:
            QMessageBox.critical(
                self,
                "HDF5 loading failed",
                "Some HDF5 files could not be refreshed.\n\n" + "\n".join(failures),
            )
        if skipped:
            QMessageBox.warning(
                self,
                "Skipped files",
                "Some files were not loaded.\n\nSkipped:\n" + "\n".join(skipped),
            )

        if refreshed_count:
            self._show_status_message(f"HDF5 file(s) refreshed {refreshed_count}", 5000)

        if not new_paths:
            return

        try:
            self.region_states.clear()
            self.proc_region_states.clear()
        except Exception:
            pass

        self._hdf5_async_failures = []
        self._hdf5_async_loaded_count = 0
        self._hdf5_process_stdout_buffer = ""
        self._hdf5_process_paths = list(new_paths)
        if hasattr(self, "_begin_busy"):
            first_name = os.path.basename(new_paths[0]) if len(new_paths) == 1 else "HDF5 files"
            self._begin_busy(f"Loading {first_name}...")

        # Use a separate process rather than QThread. Native HDF5/h5py calls can
        # block hard enough (especially on network storage) that a Python/Qt
        # worker thread still starves the GUI event loop. QProcess gives the
        # loader its own interpreter and native HDF5 state.
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_hdf5_process_stdout)
        process.readyReadStandardError.connect(self._read_hdf5_process_stderr)
        process.finished.connect(self._finish_hdf5_process_load)
        process.errorOccurred.connect(self._hdf5_process_error)
        self._hdf5_load_process = process

        # Defer process launch until Qt has returned to the event loop once.
        # This lets the busy row paint immediately and avoids doing even process
        # startup work in the same callback that handled the file selection/drop.
        worker_args = ["-m", "maxiv_exact.hdf5_worker", *new_paths]
        QTimer.singleShot(0, lambda p=process, a=worker_args: p.start(sys.executable, a))

    def _record_hdf5_async_failure(self, abs_path, message):
        self._hdf5_async_failures = list(getattr(self, "_hdf5_async_failures", []))
        self._hdf5_async_failures.append(f"{os.path.basename(str(abs_path))}: {message}")

    def _apply_loaded_hdf5_payload(self, payload):
        """Apply worker-produced plain metadata to Qt widgets in the GUI thread."""
        abs_path = os.path.abspath(str(payload.get("abs_path", "")))
        if not abs_path:
            return
        tree = getattr(self, "tree", None)
        try:
            if tree is not None:
                tree.blockSignals(True)
            self.hdf5_files[abs_path] = True
            file_item = QTreeWidgetItem([os.path.basename(abs_path)])
            file_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, ""))

            for desc in payload.get("root_children", []) or []:
                name = str(desc.get("name", ""))
                hdf5_path = str(desc.get("path", name))
                child_item = QTreeWidgetItem([name])
                child_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, hdf5_path))
                if desc.get("kind") == "group" and desc.get("has_children"):
                    child_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                    child_item.addChild(QTreeWidgetItem(["(click to expand)"]))
                elif desc.get("kind") == "dataset" and desc.get("is_1d_dataset"):
                    key = f"{abs_path}##{hdf5_path}"
                    state = Qt.CheckState.Checked if getattr(self, "raw_visibility", {}).get(key, False) else Qt.CheckState.Unchecked
                    child_item.setCheckState(0, state)
                file_item.addChild(child_item)

            self.tree.addTopLevelItem(file_item)
            file_item.setExpanded(True)
        finally:
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass

        self._apply_norm_channels(payload.get("norm_channels", []) or [])

        # Cache the recursive 1-D channel scan produced by the worker.  The
        # previous implementation re-opened and recursively traversed the HDF5
        # file from _refresh_all_in_channel_combo() in the GUI thread, which
        # could freeze the application for the entire duration on network files.
        try:
            cache = getattr(self, "_hdf5_all_channel_cache", None)
            if not isinstance(cache, dict):
                cache = {}
                self._hdf5_all_channel_cache = cache
            cache[abs_path] = list(payload.get("all_channels", []) or [])
            QTimer.singleShot(0, getattr(self, "_refresh_all_in_channel_combo", lambda: None))
        except Exception:
            pass
        self._hdf5_async_loaded_count = int(getattr(self, "_hdf5_async_loaded_count", 0)) + 1

    def _apply_norm_channels(self, channel_names):
        """Populate the normalization combo from worker-scanned channel names."""
        try:
            self.combo_norm.clear()
            for name in channel_names or []:
                self.combo_norm.addItem(str(name))
        except Exception:
            return

        default_candidates = ["b107a_em_03_ch2", "b107a_em_04_ch2", "Pt_No"]
        try:
            cc = getattr(self, "channel_config", None)
            if cc is not None:
                cands = cc.get_candidates("I0")
                if cands:
                    default_candidates = list(cands)
        except Exception:
            pass

        for cand in default_candidates:
            cand = str(cand).strip()
            if not cand:
                continue
            idx = self.combo_norm.findText(cand)
            if idx != -1:
                self.combo_norm.setCurrentIndex(idx)
                return
        for i in range(self.combo_norm.count()):
            txt = str(self.combo_norm.itemText(i))
            for cand in default_candidates:
                cand = str(cand).strip()
                if cand and cand in txt:
                    self.combo_norm.setCurrentIndex(i)
                    return

    def _finish_hdf5_async_load(self):
        try:
            self.combo_poly.setCurrentIndex(2)
        except Exception:
            pass
        try:
            self.update_file_label()
        except Exception:
            pass
        try:
            if hasattr(self, "_end_busy"):
                self._end_busy()
        except Exception:
            pass

        failures = list(getattr(self, "_hdf5_async_failures", []))
        loaded_count = int(getattr(self, "_hdf5_async_loaded_count", 0))
        if failures:
            QMessageBox.critical(
                self,
                "HDF5 loading failed",
                "Some HDF5 files could not be loaded.\n\n" + "\n".join(failures),
            )
        if loaded_count:
            self._show_status_message(f"HDF5 file(s) loaded {loaded_count}", 5000)

    def _read_hdf5_process_stdout(self):
        process = getattr(self, "_hdf5_load_process", None)
        if process is None:
            return
        try:
            chunk = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        except Exception:
            return
        self._hdf5_process_stdout_buffer = str(getattr(self, "_hdf5_process_stdout_buffer", "")) + chunk
        while "\n" in self._hdf5_process_stdout_buffer:
            line, self._hdf5_process_stdout_buffer = self._hdf5_process_stdout_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            kind = str(event.get("type", ""))
            if kind == "progress":
                if hasattr(self, "_set_busy_message"):
                    self._set_busy_message(str(event.get("message", "Loading HDF5 file...")))
            elif kind == "file_ready":
                self._apply_loaded_hdf5_payload(event.get("payload", {}) or {})
            elif kind == "file_failed":
                self._record_hdf5_async_failure(str(event.get("path", "")), str(event.get("message", "Unknown error")))

    def _read_hdf5_process_stderr(self):
        process = getattr(self, "_hdf5_load_process", None)
        if process is None:
            return
        try:
            chunk = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        except Exception:
            chunk = ""
        if chunk:
            logger.warning("HDF5 loader process: %s", chunk)
            self._hdf5_process_last_stderr = chunk

    def _hdf5_process_error(self, _error):
        process = getattr(self, "_hdf5_load_process", None)
        if process is None:
            return
        try:
            if process.state() == QProcess.ProcessState.NotRunning and not getattr(self, "_hdf5_async_loaded_count", 0):
                msg = str(getattr(self, "_hdf5_process_last_stderr", "")).strip() or process.errorString()
                if msg:
                    self._record_hdf5_async_failure("loader process", msg)
        except Exception:
            pass

    def _finish_hdf5_process_load(self, _exit_code=0, _exit_status=None):
        # Drain any final output before closing the busy state.
        self._read_hdf5_process_stdout()
        self._read_hdf5_process_stderr()
        self._finish_hdf5_async_load()
        process = getattr(self, "_hdf5_load_process", None)
        if process is not None:
            process.deleteLater()
        self._hdf5_load_process = None
        self._hdf5_process_paths = []
        self._hdf5_process_stdout_buffer = ""

    def open_file(self):
        dialog = QFileDialog(self, "Open HDF5 File(s)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)          # keep control over size
        dialog.setOption(QFileDialog.Option.DontUseCustomDirectoryIcons, True)  # <<< SPEED-UP: no per-item icon lookups
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilter("HDF5 Files (*.h5 *.hdf5)")
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        dialog.setSizeGripEnabled(True)

        # Try to default to the installed example_data directory, if available
        try:
            example_dir = files("maxiv_exact") / "example_data"
            if os.path.isdir(str(example_dir)):
                dialog.setDirectory(str(example_dir))
        except Exception:
            # Fall back to Qt's default directory behaviour if anything goes wrong
            pass

        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint)

        screen_geom = QApplication.primaryScreen().availableGeometry()
        dialog.resize(int(screen_geom.width()*0.60), int(screen_geom.height()*0.60))
        dialog.move(screen_geom.center() - dialog.rect().center())

        if dialog.exec() == QDialog.DialogCode.Accepted:
            file_paths = dialog.selectedFiles()
            if file_paths:
                self.load_hdf5_paths(file_paths, source="dialog")

    def load_hdf5_file(self, abs_path):
        """
        Non-locking: do not keep h5py.File handles open.
        Add a top-level item and a dummy child for lazy expansion.
        """
        try:
            abs_path = os.path.abspath(str(abs_path))

            # Validate readability before modifying application state.
            try:
                with self._open_h5_read(abs_path) as f:
                    has_children = len(f.keys()) > 0
            except Exception as exc:
                raise RuntimeError(f"Could not open HDF5 file:\n{abs_path}\n\n{exc}") from exc

            tree = getattr(self, "tree", None)
            try:
                if tree is not None:
                    tree.blockSignals(True)

                self.hdf5_files[abs_path] = True

                file_item = QTreeWidgetItem([os.path.basename(abs_path)])
                file_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, ""))

                if has_children:
                    file_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                    file_item.addChild(QTreeWidgetItem(["(click to expand)"]))

                self.tree.addTopLevelItem(file_item)
                file_item.setExpanded(True)
            finally:
                try:
                    if tree is not None:
                        tree.blockSignals(False)
                except Exception:
                    pass

            # If signals were blocked during insertion, populate the first level explicitly.
            try:
                if has_children:
                    self.load_subtree(file_item)
            except Exception:
                pass

            # Ensure this scans internally with short-lived opens too
            self.populate_norm_channels(abs_path)
            # Refresh 'All in channel' combo after loading this file
            QTimer.singleShot(0, getattr(self, '_refresh_all_in_channel_combo', lambda: None))
            # Update 'All in channel' combo now that files are loaded
            QTimer.singleShot(0, getattr(self, '_refresh_all_in_channel_combo', lambda: None))

        except Exception as e:
            try:
                self.file_label.setText(f"Error opening file: {e}")
            except Exception:
                pass
            raise

    def populate_norm_channels(self, abs_path):
        """Populate normalization channels using a short-lived file open (non-locking)."""
        self.combo_norm.clear()
        # Default I0 candidates come from the active channel-mapping profile (beamline).
        # The *first* candidate is treated as the preferred default.
        default_candidates = ["b107a_em_03_ch2", "b107a_em_04_ch2", "Pt_No"]
        try:
            cc = getattr(self, "channel_config", None)
            if cc is not None:
                cands = cc.get_candidates("I0")
                if cands:
                    default_candidates = list(cands)
        except Exception:
            pass

        try:
            with (self._open_h5_read(abs_path)) as f:
                for key in f.keys():
                    entry = f[key]
                    if "measurement" in entry:
                        meas_group = entry["measurement"]
                        for ds_name, ds_obj in meas_group.items():
                            if isinstance(ds_obj, h5py.Dataset) and ds_obj.ndim == 1:
                                self.combo_norm.addItem(ds_name)
                        break
        except Exception:
            pass

        # Prefer exact match in candidate order (first candidate wins).
        for cand in default_candidates:
            cand = str(cand).strip()
            if not cand:
                continue
            idx = self.combo_norm.findText(cand)
            if idx != -1:
                self.combo_norm.setCurrentIndex(idx)
                return

        # Substring fallback (still using candidate order).
        for i in range(self.combo_norm.count()):
            txt = str(self.combo_norm.itemText(i))
            for cand in default_candidates:
                cand = str(cand).strip()
                if cand and cand in txt:
                    self.combo_norm.setCurrentIndex(i)
                    return
    def load_subtree(self, item):
        payload = h5load.split_tree_payload(
            item.data(0, Qt.ItemDataRole.UserRole),
            known_file_paths=getattr(self, "hdf5_files", {}) or {},
        )
        if payload is None:
            return
        abs_path, hdf5_path = payload
        try:
            with (self._open_h5_read(abs_path)) as f:
                if hdf5_path == "":
                    if item.childCount() == 1 and item.child(0).text(0) == "(click to expand)":
                        item.removeChild(item.child(0))
                        for key in f.keys():
                            child_item = QTreeWidgetItem([key])
                            child_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, key))
                            sub_obj = f[key]
                            if isinstance(sub_obj, h5py.Group) and sub_obj.keys():
                                child_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                                child_item.addChild(QTreeWidgetItem(["(click to expand)"]))
                            elif isinstance(sub_obj, h5py.Dataset) and sub_obj.ndim == 1:
                                child_item.setCheckState(0, Qt.CheckState.Unchecked)
                            item.addChild(child_item)
                    return

                if hdf5_path in f:
                    obj = f[hdf5_path]
                    if isinstance(obj, h5py.Group):
                        if item.childCount() == 1 and item.child(0).text(0) == "(click to expand)":
                            item.removeChild(item.child(0))
                            for key in obj.keys():
                                child_item = QTreeWidgetItem([key])
                                child_item.setData(0, Qt.ItemDataRole.UserRole, h5load.make_tree_payload(abs_path, f"{hdf5_path}/{key}"))
                                sub_obj = obj[key]
                                if isinstance(sub_obj, h5py.Group) and sub_obj.keys():
                                    child_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                                    child_item.addChild(QTreeWidgetItem(["(click to expand)"]))
                                elif isinstance(sub_obj, h5py.Dataset) and sub_obj.ndim == 1:
                                    child_item.setCheckState(0, Qt.CheckState.Unchecked)
                                item.addChild(child_item)
        except Exception:
            pass

    def _compute_raw_curve(self):
        if not self.plot_data:
            return None, None
        if self.chk_sum.isChecked():
            sum_y, x_ref = None, None
            for combined_label, y_data in self.plot_data.items():
                if not self.raw_visibility.get(combined_label, True):
                    continue
                parts = combined_label.split("##", 1)
                if len(parts) != 2:
                    continue
                abs_path, hdf5_path = parts
                parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                x_data = lookup_energy(self, abs_path, parent, len(y_data))
                if sum_y is None:
                    sum_y = y_data.copy()
                    x_ref = x_data
                else:
                    m = min(len(sum_y), len(y_data))
                    sum_y = sum_y[:m] + y_data[:m]
                    x_ref = x_ref[:m]
            return x_ref, sum_y
        else:
            for combined_label, y_data in self.plot_data.items():
                if not self.raw_visibility.get(combined_label, True):
                    continue
                parts = combined_label.split("##", 1)
                if len(parts) == 2:
                    abs_path, hdf5_path = parts
                    parent = hdf5_path.rsplit("/", 1)[0] if "/" in hdf5_path else ""
                    return (
                        lookup_energy(self, abs_path, parent, len(y_data)),
                        y_data
                    )
        return None, None


def lookup_energy(viewer, abs_path: str, parent: str, length: int):
    """
    Return the energy axis for a given 1D dataset.

    Preference order:
    1) An explicit x/energy dataset under the same parent group, e.g.
       - f"{parent}/x"
       - f"{parent}/energy"
       - f"{parent}/photon_energy"
    2) Fallback to original behaviour using "pcap_energy_av" or "mono_traj_energy"
       either under the same parent or at the file root.
    3) If none found, return a simple arange(length).
    """
    cache = getattr(viewer, "energy_cache", None)
    if cache is None:
        cache = viewer.energy_cache = {}
    key = f"{abs_path}::{parent}"
    if key in cache:
        return cache[key][0]

    x = None
    try:
        with viewer._open_h5_read(abs_path) as f:
            # 1) Explicit x/energy datasets near the parent
            search_roots = []
            if parent:
                search_roots.append(parent)
            else:
                search_roots.append("")
            # Candidate names for the energy axis can be extended via the
            # channel mapping ("Energy" role).
            candidates = ["pcap_energy_av", "mono_traj_energy", "x", "energy", "photon_energy"]
            try:
                cc = getattr(viewer, "channel_config", None)
                if cc is not None:
                    extra = cc.get_candidates("Energy")
                    for name in extra:
                        name = str(name)
                        if name and name not in candidates:
                            candidates.append(name)
            except Exception:
                pass
            for root in search_roots:
                for name in candidates:
                    p = f"{root}/{name}" if root else name
                    try:
                        arr = f[p][...]
                        try:
                            arr = arr.squeeze()
                        except Exception:
                            pass
                        if getattr(arr, "size", 0) > 0:
                            x = arr
                            break
                    except Exception:
                        continue
                if x is not None:
                    break

            # 2) Fallback to original pcap/mono_traj search
            if x is None:
                cands = []
                if parent:
                    cands += [f"{parent}/pcap_energy_av", f"{parent}/mono_traj_energy"]
                else:
                    cands += ["pcap_energy_av", "mono_traj_energy"]
                for p in cands:
                    try:
                        arr = f[p][...]
                        try:
                            arr = arr.squeeze()
                        except Exception:
                            pass
                        if getattr(arr, "size", 0) > 0:
                            x = arr
                            break
                    except Exception:
                        continue
    except Exception:
        x = None

    if x is None:
        x = np.arange(length)
    cache[key] = (x, False)
    return x
def collect_available_1d_datasets(self):
        """Return a sorted list of unique relative paths for all 1D datasets across opened HDF5 files.
        Relative path is with respect to the group (no leading slash)."""
        import h5py
        rels = set()
        files = list(getattr(self, "hdf5_files", {}).keys()) if hasattr(self, "hdf5_files") else []
        for abs_path in files:
            try:
                with self._open_h5_read(abs_path) as f:
                    def _visit(name, obj):
                        try:
                            if isinstance(obj, h5py.Dataset):
                                shp = tuple(getattr(obj, "shape", ()) or ())
                                if len(shp) == 1:
                                    norm = "/" + str(name).strip("/") + "/"
                                    if "/measurement/" not in norm:
                                        return
                                    s = name.lstrip("/")
                                    rels.add(s)
                        except Exception:
                            pass
                    f.visititems(_visit)
            except Exception:
                pass
        out = sorted(rels, key=lambda s: s.lower())
        return out
