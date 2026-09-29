"""
Utilities for handling missing values (NaNs) in spectra matrices.

Policy (v2.3.6):
- Always restrict to the common overlap energy range to remove edge NaNs.
- If only isolated interior NaNs exist (single NaN bracketed by finite values), repair automatically and notify the user (OK).
- If gaps of >= 2 consecutive NaNs exist, warn the user and ask OK/Cancel before attempting repair.
  Repair is performed by linear interpolation between the bracketing finite points.
- Never extrapolate: if a missing run touches the boundary after overlap trimming, we abort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Sequence

import numpy as np
from PyQt6.QtWidgets import QMessageBox


@dataclass
class GapInfo:
    label: str
    start_idx: int
    end_idx: int
    length: int
    x0: float
    x1: float


@dataclass
class NanReport:
# overlap trimming
    trimmed: bool
    x_min: float
    x_max: float
    n_removed_left: int
    n_removed_right: int

# isolated NaNs
    isolated_points_total: int
    isolated_spectra_count: int

# gaps (>=2)
    gap_count_total: int
    gap_spectra_labels: List[str]
    largest_gap: Optional[GapInfo]
    top_gaps: List[GapInfo]


def _first_last_finite(y: np.ndarray) -> Tuple[Optional[int], Optional[int]]:
    f = np.isfinite(y)
    if not np.any(f):
        return None, None
    idx = np.flatnonzero(f)
    return int(idx[0]), int(idx[-1])


def _find_nan_runs(y: np.ndarray) -> List[Tuple[int, int]]:
    """Return list of (start, end) indices for contiguous non-finite runs."""
    m = ~np.isfinite(y)
    if not np.any(m):
        return []
    # run-length encoding
    idx = np.flatnonzero(m)
    runs = []
    start = idx[0]
    prev = idx[0]
    for i in idx[1:]:
        if i == prev + 1:
            prev = i
        else:
            runs.append((int(start), int(prev)))
            start = i
            prev = i
    runs.append((int(start), int(prev)))
    return runs


def _interpolate_segment(x: np.ndarray, y: np.ndarray, start: int, end: int) -> bool:
    """
    Interpolate y[start:end+1] linearly between bracketing points.
    Returns True if interpolation succeeded, False if not bracketed (no extrapolation).
    """
    left = start - 1
    right = end + 1
    if left < 0 or right >= y.size:
        return False
    if (not np.isfinite(y[left])) or (not np.isfinite(y[right])):
        return False
    x0, x1 = float(x[left]), float(x[right])
    y0, y1 = float(y[left]), float(y[right])
    if x1 == x0:
        # Degenerate axis; fall back to constant fill
        y[start:end+1] = y0
        return True
    xs = x[start:end+1].astype(float)
    y[start:end+1] = y0 + (y1 - y0) * (xs - x0) / (x1 - x0)
    return True


def _build_report(
    x: np.ndarray,
    Y: np.ndarray,
    labels: Sequence[str],
    n_left: int,
    n_right: int,
) -> NanReport:
    x_min = float(x[0])
    x_max = float(x[-1])
    trimmed = (n_left > 0) or (n_right > 0)

    isolated_points_total = 0
    isolated_spectra_count = 0
    gap_count_total = 0
    gap_spectra = set()
    gaps: List[GapInfo] = []

    for j in range(Y.shape[0]):
        y = Y[j]
        runs = _find_nan_runs(y)
        if not runs:
            continue
        # since overlap trim ensures edges are finite, any run here should be interior
        has_isolated = False
        for s, e in runs:
            length = e - s + 1
            if length == 1:
                # isolated only if bracketed by finite values
                if s > 0 and s < y.size - 1 and np.isfinite(y[s-1]) and np.isfinite(y[s+1]):
                    isolated_points_total += 1
                    has_isolated = True
                else:
                    # Treat as a gap (unbracketed single NaN) -> will require confirmation
                    gap_count_total += 1
                    gap_spectra.add(labels[j])
                    gaps.append(GapInfo(labels[j], s, e, length, float(x[s]), float(x[e])))
            else:
                gap_count_total += 1
                gap_spectra.add(labels[j])
                gaps.append(GapInfo(labels[j], s, e, length, float(x[s]), float(x[e])))
        if has_isolated:
            isolated_spectra_count += 1

    gaps_sorted = sorted(gaps, key=lambda g: (g.length, g.x1 - g.x0), reverse=True)
    largest_gap = gaps_sorted[0] if gaps_sorted else None
    top_gaps = gaps_sorted[:3]

    return NanReport(
        trimmed=trimmed,
        x_min=x_min,
        x_max=x_max,
        n_removed_left=n_left,
        n_removed_right=n_right,
        isolated_points_total=isolated_points_total,
        isolated_spectra_count=isolated_spectra_count,
        gap_count_total=gap_count_total,
        gap_spectra_labels=sorted(gap_spectra),
        largest_gap=largest_gap,
        top_gaps=top_gaps,
    )


def prepare_matrix_with_nan_policy(
    parent,
    x: np.ndarray,
    Y: np.ndarray,
    labels: Sequence[str],
    action_label: str = "analysis",
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Apply the app's NaN policy to (x, Y). Returns cleaned (x, Y) or None if user cancels.

    Notes
    -----
    - This function may show modal dialogs (QMessageBox).
    - It never extrapolates; if interpolation isn't possible, it aborts with a message.
    """
    if x is None or Y is None:
        return None
    x = np.asarray(x).ravel()
    Y = np.asarray(Y, dtype=float)
    if Y.ndim != 2:
        raise ValueError("Y must be a 2D matrix (n_spectra, n_points).")
    if Y.shape[1] != x.size:
        raise ValueError("x and Y have incompatible shapes.")

    # --- Step 1: overlap trimming based on first/last finite points per spectrum
    firsts = []
    lasts = []
    for j in range(Y.shape[0]):
        f, l = _first_last_finite(Y[j])
        if f is None or l is None:
            QMessageBox.critical(
                parent,
                "Cannot proceed",
                f'The dataset contains a spectrum with no finite values ("{labels[j]}").',
            )
            return None
        firsts.append(f)
        lasts.append(l)

    i0 = int(max(firsts))
    i1 = int(min(lasts)) + 1  # exclusive
    if i0 >= i1:
        QMessageBox.critical(
            parent,
            "Cannot proceed",
            "The selected spectra do not share a common finite overlap range.\n"
            "Please remove problematic spectra or fix the source data.",
        )
        return None

    n_left = i0
    n_right = x.size - i1
    x2 = x[i0:i1]
    Y2 = Y[:, i0:i1].copy()

    # --- Step 2: analyze remaining NaNs (interior only)
    report = _build_report(x2, Y2, labels, n_left=n_left, n_right=n_right)

    # If there are gaps (>=2 consecutive NaNs or unbracketed single NaN), ask user
    if report.gap_count_total > 0:
        # Mention spectra with gaps
        gap_labels = report.gap_spectra_labels
        max_list = 12
        if len(gap_labels) > max_list:
            shown = ", ".join(gap_labels[:max_list])
            extra = len(gap_labels) - max_list
            gap_list_str = f"{shown} (+{extra} more)"
        else:
            gap_list_str = ", ".join(gap_labels) if gap_labels else "—"

        lines = [
            "Found gaps of missing values (2 or more consecutive points) inside the selected spectra.",
            f"Interpolating across gaps may influence {action_label}.",
            "",
            f"Common overlap energy range: {report.x_min:.3f} – {report.x_max:.3f}",
            f"Affected spectra: {len(gap_labels)} of {Y2.shape[0]}",
            f"Total gaps: {report.gap_count_total}",
        ]
        if report.largest_gap is not None:
            g = report.largest_gap
            lines.append(
                f'Largest gap: {g.length} points ({g.x0:.3f} – {g.x1:.3f}) in "{g.label}"'
            )
        lines += [
            "",
            "Gaps found in spectra:",
            gap_list_str,
        ]
        if report.top_gaps:
            lines += ["", "Worst gaps:"]
            for g in report.top_gaps:
                lines.append(f'• "{g.label}" : {g.length} points ({g.x0:.3f} – {g.x1:.3f})')

        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Missing-value gaps detected")
        msg.setText("\n".join(lines))
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        resp = msg.exec()
        if resp != QMessageBox.StandardButton.Ok:
            return None

        # User accepted: attempt to repair ALL NaN runs (including isolated ones) by interpolation
        for j in range(Y2.shape[0]):
            y = Y2[j]
            runs = _find_nan_runs(y)
            for s, e in runs:
                ok = _interpolate_segment(x2, y, s, e)
                if not ok:
                    QMessageBox.critical(
                        parent,
                        "Cannot proceed",
                        f'Cannot repair missing values in "{labels[j]}" '
                        f'around {float(x2[s]):.3f} – {float(x2[e]):.3f}.\n'
                        "The missing region touches a boundary or cannot be bracketed.\n"
                        "No extrapolation will be performed.",
                    )
                    return None

        if np.isnan(Y2).any():
            QMessageBox.critical(
                parent,
                "Cannot proceed",
                f"The dataset still contains missing values after repair.\n"
                f"{action_label.capitalize()} cannot run with NaNs.",
            )
            return None

        # After OK and repair, proceed without an extra dialog (user already acknowledged the warning).
        return x2, Y2

    # No gaps. If there are isolated NaNs, repair automatically.
    did_repair_isolated = report.isolated_points_total > 0
    if did_repair_isolated:
        for j in range(Y2.shape[0]):
            y = Y2[j]
            runs = _find_nan_runs(y)
            for s, e in runs:
                length = e - s + 1
                if length == 1:
                    # isolated (bracketed)
                    ok = _interpolate_segment(x2, y, s, e)
                    if not ok:
                        # Should not happen for bracketed isolated, but keep safe
                        QMessageBox.critical(
                            parent,
                            "Cannot proceed",
                            f'Cannot repair an isolated missing point in "{labels[j]}".',
                        )
                        return None

    # If any trimming happened or isolated repair happened, notify with OK-only dialog.
    if report.trimmed or did_repair_isolated:
        lines = [
            f"Energy range restricted to common overlap: {report.x_min:.3f} – {report.x_max:.3f}"
        ]
        if report.trimmed:
            removed = []
            if report.n_removed_left > 0:
                removed.append(f"{report.n_removed_left} left")
            if report.n_removed_right > 0:
                removed.append(f"{report.n_removed_right} right")
            lines.append(f"Removed {', '.join(removed)} edge point(s) to avoid incomplete spectra.")
        if did_repair_isolated:
            lines.append(
                f"Repaired {report.isolated_points_total} isolated missing point(s) "
                f"in {report.isolated_spectra_count} spectrum/spectra (linear interpolation)."
            )
        lines.append("")
        lines.append("Press OK to continue.")

        QMessageBox.information(parent, "Missing values handled", "\n".join(lines))

    # Ensure no NaNs remain (should be true here)
    if np.isnan(Y2).any():
        QMessageBox.critical(
            parent,
            "Cannot proceed",
            f"The dataset contains missing values.\n{action_label.capitalize()} cannot run with NaNs.",
        )
        return None

    return x2, Y2


def finite_minmax(x: np.ndarray) -> Optional[Tuple[float, float]]:
    """Return finite (min, max) for x, ignoring NaNs/inf. None if no finite values."""
    x = np.asarray(x).ravel()
    f = np.isfinite(x)
    if not np.any(f):
        return None
    xf = x[f].astype(float)
    return float(np.min(xf)), float(np.max(xf))
