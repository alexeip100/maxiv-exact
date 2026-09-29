"""Auto-generated ExportMixin extracted from ui.py."""
import os
import time
import csv
import re
import numpy as np
from .compat import trapezoid
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QDialog
from PyQt6.QtCore import Qt

class ExportMixin:
    def _csv_save_start_dir(self, data_default_dir=""):
        """Return the session-only CSV save directory.

        The first save after application startup uses the current data folder.
        Once the user successfully saves elsewhere, that folder is offered for
        subsequent CSV saves during the same application session.
        """
        remembered = str(getattr(self, "_last_csv_save_dir", "") or "").strip()
        return remembered or str(data_default_dir or "")

    def _remember_csv_save_path(self, file_path):
        """Remember a successful CSV save directory for this app session only."""
        try:
            directory = os.path.dirname(os.path.abspath(str(file_path)))
        except Exception:
            directory = ""
        if directory:
            self._last_csv_save_dir = directory

    def _csv_save_dialog(self, title, default_dir="", default_filename=""):
        """Non-fullscreen save dialog for CSV."""
        start_dir = self._csv_save_start_dir(default_dir)
        dlg = QFileDialog(self, title, start_dir)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setFileMode(QFileDialog.FileMode.AnyFile)
        dlg.setNameFilter("CSV Files (*.csv)")
        dlg.setDefaultSuffix("csv")
        dlg.resize(900, 600)
        dlg.setMinimumSize(700, 500)
        if default_filename:
            dlg.selectFile(default_filename)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            files = dlg.selectedFiles()
            path = files[0] if files else ""
            if path:
                self._remember_csv_save_path(path)
            return path
        return ""

    def _csv_open_dialog(self, title, default_dir=""):
        """Non-fullscreen open dialog for CSV (multi-select)."""
        dlg = QFileDialog(self, title, default_dir)
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dlg.setNameFilter("CSV Files (*.csv);;All Files (*)")
        dlg.resize(900, 600)
        dlg.setMinimumSize(700, 500)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selectedFiles() or []
        return ""

    def export_ascii_plotted(self):
        """Export visible curves from the Plotted Data panel to CSV.

        Column naming rules:
          - Legend = 'Entry number': headers keep the entry prefix (entry#### -> entry####). All curves must have an entry id.
          - Legend = 'User-defined': headers are the user-defined curve names. Placeholder '<select curve name>' is not allowed.
          - Legend = 'None': export is blocked (no labeling scheme).
        """

        # Determine visible curves in the *current* plotted-list order
        visible_keys = []
        try:
            if hasattr(self, "plotted_list") and self.plotted_list is not None:
                for row in range(self.plotted_list.count()):
                    item = self.plotted_list.item(row)
                    if item is None:
                        continue
                    key = item.data(Qt.ItemDataRole.UserRole)
                    if key in self.plotted_lines and self.plotted_lines[key].get_visible():
                        visible_keys.append(key)
        except Exception:
            visible_keys = []

        if not visible_keys:
            try:
                visible_keys = [k for k, ln in self.plotted_lines.items() if ln.get_visible()]
            except Exception:
                visible_keys = []

        if not visible_keys:
            QMessageBox.warning(self, "Export", "No visible curves to export.")
            return

        # Legend mode (created in ui.py)
        try:
            legend_mode = str(self.legend_mode_combo.currentText()).strip()
        except Exception:
            legend_mode = "User-defined"
        legend_mode_norm = legend_mode.lower()

        if legend_mode_norm == "none":
            QMessageBox.warning(
                self,
                "Export Not Possible",
                "CSV export requires curve names.\n\n"
                "Set Legend to 'Entry number' or 'User-defined' before exporting."
            )
            return

        def _entry_digits_from_meta(key: str):
            # Prefer plotted metadata
            try:
                meta = getattr(self, "plotted_metadata", {}) or {}
                src_entry = (meta.get(key, {}) or {}).get("source_entry", "") or ""
                m = re.search(r"entry(\d+)", str(src_entry))
                if m:
                    return m.group(1)
            except Exception:
                pass
            # Fallback: parse from key/path itself
            try:
                m = re.search(r"entry(\d+)", str(key))
                if m:
                    return m.group(1)
            except Exception:
                pass
            return None

        # Collect x/y and headers
        first_line = self.plotted_lines[visible_keys[0]]
        x_data = np.asarray(first_line.get_xdata())
        min_len = len(x_data)

        headers = []
        y_columns = []

        if legend_mode_norm.startswith("entry"):
            for key in visible_keys:
                entry_num = _entry_digits_from_meta(key)
                if not entry_num:
                    QMessageBox.warning(
                        self,
                        "Export Not Possible",
                        "Legend is set to 'Entry number', but at least one visible curve has no 'entry####' identifier "
                        "(for example, a curve imported from CSV).\n\n"
                        "Either switch Legend to 'User-defined' and assign names to all curves, or export only curves "
                        "that originate from HDF5 entries."
                    )
                    return
                ln = self.plotted_lines[key]
                y = np.asarray(ln.get_ydata())
                min_len = min(min_len, len(y))
                headers.append(f"entry{entry_num}")
                y_columns.append(y)
        else:
            # Require explicit user-defined names for ALL visible curves
            for key in visible_keys:
                try:
                    lbl = (getattr(self, "custom_labels", {}) or {}).get(key)
                except Exception:
                    lbl = None
                lbl = "" if lbl is None else str(lbl).strip()
                if (not lbl) or (lbl == "<select curve name>"):
                    QMessageBox.warning(
                        self,
                        "Export Not Possible",
                        "Legend is set to 'User-defined', but at least one visible curve still has no user-defined name "
                        "(it shows '<select curve name>').\n\n"
                        "Please name all curves (click legend entries) or switch Legend to 'Entry number'."
                    )
                    return
                ln = self.plotted_lines[key]
                y = np.asarray(ln.get_ydata())
                min_len = min(min_len, len(y))
                headers.append(lbl)
                y_columns.append(y)

        # Sanitize and ensure unique headers
        clean = []
        counts = {}
        for h in headers:
            h2 = str(h).replace("\n", " ").replace("\r", " ").replace(",", " ").strip()
            if h2 == "<select curve name>":
                QMessageBox.warning(self, "Export Not Possible", "Invalid curve name '<select curve name>'.")
                return
            base = h2 if h2 else "curve"
            n = counts.get(base, 0) + 1
            counts[base] = n
            clean.append(base if n == 1 else f"{base}_{n}")

        x_out = x_data[:min_len]
        y_out = [np.asarray(y)[:min_len] for y in y_columns]
        header_row = ["X"] + clean

        # Handle missing values (NaNs) consistently (overlap trimming + optional interpolation)
        try:
            from maxiv_exact.utils.nan_policy import prepare_matrix_with_nan_policy
        except Exception:
            prepare_matrix_with_nan_policy = None

        if prepare_matrix_with_nan_policy is not None:
            try:
                Ymat = np.vstack([np.asarray(col, dtype=float) for col in y_out])
            except Exception:
                Ymat = None

            if Ymat is not None and Ymat.ndim == 2 and Ymat.shape[0] == len(clean) and Ymat.shape[1] == len(x_out):
                cleaned = prepare_matrix_with_nan_policy(
                    self,
                    np.asarray(x_out),
                    Ymat,
                    clean,
                    action_label="CSV export",
                )
                if cleaned is None:
                    return
                x_out, Ymat = cleaned
                y_out = [Ymat[i, :] for i in range(Ymat.shape[0])]

        # Default dir: any opened HDF5 dir
        any_file = None
        try:
            any_file = next(iter(getattr(self, "hdf5_files", []) or []), None)
        except Exception:
            any_file = None
        default_dir = os.path.dirname(any_file) if any_file else ""

        file_path = self._csv_save_dialog("Export CSV", default_dir, "")
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header_row)
                for i in range(min_len):
                    row = [f"{x_out[i]:.6g}"] + [f"{col[i]:.6g}" for col in y_out]
                    writer.writerow(row)
        except Exception as ex:
            QMessageBox.critical(self, "Export Error", f"Failed to write CSV:\n{ex}")


    def import_csv_plotted(self):
        """
        Import one or more CSV files (previously exported) and plot them directly
        in the *Plotted Data* panel.

        Expected format:
          - First row: header, with first column being X and remaining columns being Y-series labels.
          - Data rows: numeric values, comma-separated (other common delimiters are also accepted).
        """
        # Choose a reasonable default directory (the directory of any opened HDF5 file, if available)
        any_file = None
        try:
            any_file = next(iter(getattr(self, "hdf5_files", []) or []), None)
        except Exception:
            any_file = None
        default_dir = os.path.dirname(any_file) if any_file else ""

        file_paths = self._csv_open_dialog("Import CSV", default_dir)
        if not file_paths:
            return

        def _is_float(s):
            try:
                float(s)
                return True
            except Exception:
                return False

        imported_count = 0
        errors = []

        for fp in file_paths:
            try:
                # --- Read CSV (robust delimiter detection + optional header) ---
                with open(fp, "r", newline="") as f:
                    sample = f.read(4096)
                    f.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",;	")
                    except Exception:
                        dialect = csv.excel  # comma by default

                    reader = csv.reader(f, dialect)
                    rows = []
                    for row in reader:
                        if not row:
                            continue
                        # allow comments
                        if str(row[0]).strip().startswith("#"):
                            continue
                        rows.append([str(c).strip() for c in row])

                if not rows:
                    raise ValueError("empty file")

                first = rows[0]
                has_header = not all(_is_float(c) for c in first if c != "")
                if has_header:
                    header = first
                    data_rows = rows[1:]
                else:
                    header = ["X"] + [f"Y{i}" for i in range(1, max(len(first), 2))]
                    data_rows = rows

                if len(header) < 2:
                    raise ValueError("CSV must have at least two columns (X and one Y)")

                ncols = len(header)

                x_vals = []
                y_vals = [[] for _ in range(ncols - 1)]

                for row in data_rows:
                    if not row:
                        continue
                    if len(row) < 2:
                        continue
                    # pad short rows
                    if len(row) < ncols:
                        row = row + [""] * (ncols - len(row))
                    # parse x
                    try:
                        x = float(row[0])
                    except Exception:
                        continue
                    x_vals.append(x)
                    # parse y's
                    for j in range(1, ncols):
                        try:
                            y = float(row[j])
                        except Exception:
                            y = float("nan")
                        y_vals[j - 1].append(y)

                x_arr = np.asarray(x_vals, dtype=float)
                if x_arr.size < 2:
                    raise ValueError("not enough numeric rows to import")

                file_stem = os.path.splitext(os.path.basename(fp))[0]

                # Add each Y column as a separate curve
                for j, y_list in enumerate(y_vals):
                    y_arr = np.asarray(y_list, dtype=float)
                    if y_arr.size != x_arr.size:
                        n = min(x_arr.size, y_arr.size)
                        x_use = x_arr[:n]
                        y_use = y_arr[:n]
                    else:
                        x_use = x_arr
                        y_use = y_arr

                    mask = np.isfinite(x_use) & np.isfinite(y_use)
                    x_use = x_use[mask]
                    y_use = y_use[mask]
                    if x_use.size < 2:
                        continue

                    col_name = ""
                    try:
                        col_name = str(header[j + 1]).strip()
                    except Exception:
                        col_name = f"Y{j+1}"
                    if not col_name:
                        col_name = f"Y{j+1}"

                    # Labeling logic:
                    # - if file contains multiple Y columns, prefix with file name
                    # - otherwise, just use file name unless the column header is informative
                    if ncols > 2:
                        label = f"{file_stem}: {col_name}"
                    else:
                        # single Y column
                        if has_header and col_name.lower() not in ("y", "y1", "intensity", "intensity1", "value"):
                            label = f"{file_stem}: {col_name}"
                        else:
                            label = file_stem

                    # unique internal key
                    ts = int(time.time() * 1000)
                    storage_key = f"csv##{file_stem}##{col_name}##{ts}##{j}"

                    meta = {
                        "is_reference": False,
                        "is_imported": True,
                        "source": "csv",
                        "file": fp,
                        "column": col_name,
                    }

                    if hasattr(self, "_add_reference_curve_to_plotted"):
                        self._add_reference_curve_to_plotted(storage_key, x_use, y_use, label, meta=meta)
                    else:
                        try:
                            line, = self.plotted_ax.plot(x_use, y_use, label=str(label))
                            if not hasattr(self, "plotted_lines"):
                                self.plotted_lines = {}
                            self.plotted_lines[storage_key] = line
                        except Exception:
                            pass

                    imported_count += 1

            except Exception as ex:
                errors.append(f"{os.path.basename(fp)}: {ex}")

        # Rescale and redraw
        try:
            if hasattr(self, "rescale_plotted_axes"):
                self.rescale_plotted_axes()
            else:
                self.plotted_ax.relim()
                self.plotted_ax.autoscale_view()
        except Exception:
            pass
        try:
            if hasattr(self, "canvas_plotted"):
                self.canvas_plotted.draw_idle()
        except Exception:
            pass

        if errors:
            # Keep message short; show first several errors
            msg = "Some files could not be imported:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n... ({len(errors) - 10} more)"
            QMessageBox.warning(self, "Import CSV", msg)
        elif imported_count == 0:
            QMessageBox.information(self, "Import CSV", "No curves were imported (no valid numeric data found).")

    def export_ascii(self):
        if not self.plot_data:
            return

# ---
        # 0.  Sanity check: one curve, or summed
        # --------------------------------------------------------------
        visible_keys = [k for k in self.plot_data if self.raw_visibility.get(k, False)]
        num_visible  = len(visible_keys)
        if num_visible > 1 and not self.chk_sum.isChecked():
            QMessageBox.warning(self, "Export Not Possible",
                                "Please sum the curves up first or select only one curve.")
            return

# ---
        # 1.  Build default file name
        # --------------------------------------------------------------
        any_file   = next(iter(self.hdf5_files), None)
        default_dir = os.path.dirname(any_file) if any_file else ""

        entries = {parts[1].split("/")[0] if len(parts) == 2 else "unknown"
                   for parts in (k.split("##", 1) for k in visible_keys)}
        entries_sorted = sorted(entries)
        if len(entries_sorted) == 1:
            file_id_part = f"entry{entries_sorted[0].replace('entry','')}"
        else:
            file_id_part = "entries" + "_".join(e.replace('entry','') for e in entries_sorted)

        default_name = f"ProcessedScan_for_{file_id_part}.csv"
        default_dir = self._csv_save_start_dir(default_dir)
        default_path = os.path.join(default_dir, default_name)

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save ASCII File", default_path, "CSV Files (*.csv)"
        )
        if not save_path:
            return
        self._remember_csv_save_path(save_path)

# ---
        # 2.  Get arrays + post-norm mode
        # --------------------------------------------------------------
        arrays = self.prepare_arrays_for_export()
        if arrays is None:
            return

        norm_mode      = arrays.pop("norm_mode", "None")   # remove & keep others intact
        x_array        = arrays["x"]
        y_raw_array    = arrays["y_raw"]
        y_norm_array   = arrays["y_norm"]
        y_bkg_array    = arrays["y_bkgd"]
        y_final_array  = arrays["y_final"]

# ---
        # 3.  Column 2 / 3 headers depend on “Sum” tickbox
        # --------------------------------------------------------------
        if self.chk_sum.isChecked() and num_visible > 1:
            col2, col3 = "Y_original_sum", "Y_norm_to_I0_sum"
        else:
            col2, col3 = "Y_original", "Y_norm_to_I0"

# ---
        # 4.  Dynamic header for the last column
        # --------------------------------------------------------------
        if   norm_mode == "Area":
            col5 = "Y_norm_to_I0_without_bckg_norm_to_area"
        elif norm_mode == "Max":
            col5 = "Y_norm_to_I0_without_bckg_norm_to_max"
        elif norm_mode == "Jump":
            col5 = "Y_norm_to_I0_without_bckg_norm_to_jump"
        else:  # "None"
            col5 = "Y_norm_to_I0_without_bckg_no_norm"

# ---
        # 5.  Write CSV
        # --------------------------------------------------------------
        try:
            with open(save_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["X", col2, col3, "Y_bckd", col5])
                for i in range(len(x_array)):
                    writer.writerow([
                        f"{x_array[i]:.6g}",
                        f"{y_raw_array[i]:.6g}",
                        f"{y_norm_array[i]:.6g}",
                        f"{y_bkg_array[i]:.6g}",
                        f"{y_final_array[i]:.6g}",
                    ])
        except Exception as ex:
            print("Error writing CSV:", ex)

    def prepare_arrays_for_export(self):
# ---
        # 0.  Guards + fetch raw & main curves
        # ------------------------------------------------------------------
        x_raw, y_raw = self._compute_raw_curve()
        if x_raw is None or y_raw is None:
            return None

        x_norm, y_norm = self.compute_main_curve()
        if x_norm is None or y_norm is None:
            return None

# ---
        # 1.  Length alignment
        # ------------------------------------------------------------------
        m = min(len(x_raw), len(x_norm))
        x_out   = x_norm[:m]
        y_raw   = y_raw[:m]
        y_norm  = y_norm[:m]

# ---
        # 2.  Background
        # ------------------------------------------------------------------
        y_bkg   = self._compute_background(x_out, y_norm)
        y_final = y_norm - y_bkg

# ---
        # 3.  Post-normalisation = contents of the combo box
        # ------------------------------------------------------------------
        norm_mode = self.combo_post_norm.currentText() \
                    if self.combo_post_norm.isEnabled() else "None"

        if   norm_mode == "Max":
            denom = np.max(np.abs(y_final))
            if denom:
                y_final /= denom

        elif norm_mode == "Jump":
            denom = y_final[-1]
            if denom:
                y_final /= denom

        elif norm_mode == "Area":
            area = trapezoid(y_final, x_out)
            if area:
                y_final /= area
        # “None” → leave y_final untouched

        return {
            "x"        : x_out,
            "y_raw"    : y_raw,
            "y_norm"   : y_norm,
            "y_bkgd"   : y_bkg,
            "y_final"  : y_final,
            "norm_mode": norm_mode,   # ← pass the choice upstream
        }
