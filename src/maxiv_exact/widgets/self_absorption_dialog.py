"""Isolated diagnostic GUI for the PFY self-absorption prototype."""
from __future__ import annotations

from importlib.resources import files
import math
import html
import re
import numpy as np
import markdown

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from ..experimental_background import fit_experimental_background
from ..reference import ReferenceDatabase
from ..self_absorption import (
    calibrate,
    correction_strength_label,
    denominator_term,
    flexpes_geometry,
    forward_fraction_distribution,
    gaussian_emission_profile,
    invert_thick,
    invert_thick_distribution,
    relative_condition_amplification_distribution,
)
from ..self_absorption_bg import build_reference_model, compound_mu_total


def _poly_background(x, y, fraction: float, degree: int):
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    idx = np.where(valid)[0]
    if idx.size < 2:
        return np.zeros_like(y)
    n = max(2, int(round(float(fraction) * idx.size)))
    use = idx[:min(n, idx.size)]
    deg = max(0, min(int(degree), len(use) - 1))
    x0 = float(np.mean(x[use])); span = float(np.ptp(x[use])) or 1.0
    p = np.polyfit((x[use] - x0) / span, y[use], deg)
    return np.polyval(p, (x - x0) / span)


def _render_mathjax_help(source: str) -> str:
    """Convert Markdown to HTML while preserving math for local MathJax rendering.

    MathJax, not Markdown or a code-span renderer, handles both inline and
    display math. Tokens keep Markdown from consuming TeX backslashes.
    """
    markers: list[tuple[str, str]] = []

    def protect(expression: str, display: bool) -> str:
        token = f"EXACTMATH{len(markers):05d}TOKEN"
        delimiters = (r"\[", r"\]") if display else (r"\(", r"\)")
        markers.append((token, delimiters[0] + expression.strip() + delimiters[1]))
        return token

    source = re.sub(r"```(?:tex|latex)\s*\n(.*?)\n```",
                    lambda m: "\n\n" + protect(m.group(1), True) + "\n\n",
                    source, flags=re.S | re.I)
    source = re.sub(r"\$\$(.*?)\$\$", lambda m: "\n\n" + protect(m.group(1), True) + "\n\n", source, flags=re.S)
    source = re.sub(r"\\\[(.*?)\\\]", lambda m: "\n\n" + protect(m.group(1), True) + "\n\n", source, flags=re.S)
    source = re.sub(r"\\\((.*?)\\\)", lambda m: protect(m.group(1), False), source, flags=re.S)
    source = re.sub(r"(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)",
                    lambda m: protect(m.group(1), False), source)
    rendered = markdown.markdown(source, extensions=['tables', 'fenced_code'])
    for token, expression in markers:
        rendered = rendered.replace(token, html.escape(expression, quote=False))
    # Qt WebEngine loads this bundled local script; it never contacts a CDN.
    return ('''<!doctype html><html><head><meta charset="utf-8">
<style>
body {font: 15px/1.48 Arial, sans-serif; margin: 18px 26px; color: #202020;}
h1 {font-size: 1.6em; margin-top: 1.35em;} h2 {font-size: 1.24em; margin-top: 1.15em;}
h3 {font-size: 1.08em;} p, li {line-height: 1.48;} li {margin: 0.28em 0;}
mjx-container[display="true"] {margin: 1.1em 0 !important; overflow-x: auto; overflow-y: hidden;}
code, pre {font-family: Consolas, monospace;} table {border-collapse: collapse;}
td,th {padding: 5px 9px; border: 1px solid #aaa;}
a {color: #215b9a;}
</style>
<script>
window.MathJax = {
  tex: {inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']],
        processEscapes: true, packages: {'[+]': ['noerrors', 'noundefined']}},
  svg: {fontCache: 'local'}, options: {skipHtmlTags: ['script','noscript','style','textarea','pre','code']}
};
</script>
<script src="tex-svg-full.js"></script></head><body>''' + rendered + "</body></html>")


class _HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Self-absorption correction — Help")
        self.resize(940, 760)
        lay = QVBoxLayout(self)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            browser = QWebEngineView(self)
            browser.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            source = files("maxiv_exact").joinpath("docs/self_absorption_help.md").read_text(encoding="utf-8")
            base = files("maxiv_exact").joinpath("resources/mathjax")
            browser.setHtml(_render_mathjax_help(source), QUrl.fromLocalFile(str(base) + "/"))
            lay.addWidget(browser)
        except Exception as exc:
            # Do not incorrectly diagnose every ImportError as a missing package.
            # Initialization-order, DLL and Qt-plugin failures need their real text.
            import traceback
            details = QPlainTextEdit(self)
            details.setReadOnly(True)
            details.setPlainText(
                "Self-absorption Help could not initialize Qt WebEngine.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                + traceback.format_exc()
                + "\nCheck that PyQt6-WebEngine is installed in the Python "
                  "environment running EXACT."
            )
            lay.addWidget(details)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(close); lay.addLayout(row)


class SelfAbsorptionDialog(QDialog):
    """Experimental correction workflow. Results remain local to this dialog."""

    def __init__(self, energy_eV, pfy_i0, label: str = "PFY", parent=None):
        super().__init__(parent)
        self.setWindowTitle("PFY self-absorption correction — experimental — EXACT")
        # Keep native Windows minimise/maximise controls and allow free resizing.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(1410, 850)
        self.setMinimumSize(900, 570)
        self.x = np.asarray(energy_eV, dtype=float).ravel()
        self.y = np.asarray(pfy_i0, dtype=float).ravel()
        self.label = str(label)
        self.db = ReferenceDatabase()
        self._manual_points = []
        self._drag_manual = None
        self._build_ui()
        self._connect()
        self._seed_ranges()
        self._update_emission_controls()
        self.recalculate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        note = QLabel(
            "Experimental thick-sample workflow. Fluorescence can be represented by one physical energy "
            "or by a fixed Gaussian energy distribution. Results remain inside this dialog and do not "
            "propagate to Processed/Plotted Data."
        )
        note.setWordWrap(True); root.addWidget(note)

        split = QSplitter(Qt.Orientation.Horizontal); root.addWidget(split, 1)

        left = QWidget(); ll = QVBoxLayout(left)
        self.fig = Figure(figsize=(11, 9), constrained_layout=True)
        self.ax_exp = self.fig.add_subplot(321)
        self.ax_ref = self.fig.add_subplot(322)
        self.ax_out = self.fig.add_subplot(323)
        self.ax_diag = self.fig.add_subplot(324)
        self.ax_cal = self.fig.add_subplot(325)
        self.ax_ratio = self.fig.add_subplot(326)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, left)
        ll.addWidget(self.toolbar); ll.addWidget(self.canvas, 1)
        split.addWidget(left)

        # The settings scroll separately; diagnostics stay visible at all times.
        right = QSplitter(Qt.Orientation.Vertical)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        panel = QWidget(); self.form_root = QVBoxLayout(panel)
        scroll.setWidget(panel); right.addWidget(scroll)
        self.diagnostic_panel = QGroupBox("Diagnostics — live values and warnings")
        diagnostic_layout = QVBoxLayout(self.diagnostic_panel)
        self.lbl_status = QPlainTextEdit()
        self.lbl_status.setReadOnly(True)
        self.lbl_status.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.lbl_status.setPlaceholderText("Calculation diagnostics will appear here.")
        diagnostic_layout.addWidget(self.lbl_status)
        right.addWidget(self.diagnostic_panel)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        right.setSizes([440, 260])
        self.settings_diagnostics_splitter = right
        split.addWidget(right); split.setSizes([1010, 400])

        g_sample = QGroupBox("Sample / fluorescence model"); f = QFormLayout(g_sample)
        self.edit_formula = QLineEdit("NiO")
        self.edit_element = QLineEdit("Ni")
        self.combo_edge = QComboBox(); self.combo_edge.addItems(["K", "L3", "L2", "L1", "M5", "M4"]); self.combo_edge.setCurrentText("L3")
        self.combo_emission_model = QComboBox(); self.combo_emission_model.addItems(["Single energy", "Gaussian"])
        self.spin_ef = QDoubleSpinBox(); self.spin_ef.setRange(1, 50000); self.spin_ef.setDecimals(2); self.spin_ef.setValue(855.0); self.spin_ef.setSuffix(" eV")
        self.spin_fwhm = QDoubleSpinBox(); self.spin_fwhm.setRange(0.10, 1000.0); self.spin_fwhm.setDecimals(2); self.spin_fwhm.setValue(5.0); self.spin_fwhm.setSuffix(" eV")
        self.spin_fwhm.setToolTip("Physical fluorescence-emission FWHM before detector broadening. Do not enter the SDD energy resolution.")
        self.spin_ef.setToolTip("Physical fluorescence photon energy (single model) or Gaussian center. Do not enter the Xspress3 MCA channel number.")
        self.combo_source = QComboBox(); self.combo_source.addItem("Chantler / XrayDB"); self.combo_source.setEnabled(False)
        f.addRow("Input curve:", QLabel(self.label))
        f.addRow("Composition:", self.edit_formula)
        f.addRow("Absorbing element:", self.edit_element)
        f.addRow("Edge:", self.combo_edge)
        f.addRow("Fluorescence model:", self.combo_emission_model)
        f.addRow("Physical E_f / center:", self.spin_ef)
        f.addRow("Gaussian FWHM:", self.spin_fwhm)
        f.addRow("Reference:", self.combo_source)
        self.form_root.addWidget(g_sample)

        g_geo = QGroupBox("Geometry"); f = QFormLayout(g_geo)
        self.spin_alpha = QDoubleSpinBox(); self.spin_alpha.setRange(0.1, 89.9); self.spin_alpha.setDecimals(2); self.spin_alpha.setValue(80.0); self.spin_alpha.setSuffix("°")
        self.spin_gamma = QDoubleSpinBox(); self.spin_gamma.setRange(0.0, 89.0); self.spin_gamma.setDecimals(2); self.spin_gamma.setValue(30.0); self.spin_gamma.setSuffix("°")
        self.lbl_beta = QLabel("—"); self.lbl_g = QLabel("—")
        f.addRow("Incidence α:", self.spin_alpha); f.addRow("Detector-plane tilt γ:", self.spin_gamma); f.addRow("Calculated exit β:", self.lbl_beta); f.addRow("Geometry factor G:", self.lbl_g)
        self.form_root.addWidget(g_geo)

        g_exp = QGroupBox("Experimental PFY background"); f = QFormLayout(g_exp)
        self.combo_exp_bg = QComboBox(); self.combo_exp_bg.addItems(["Auto", "Manual", "None"])
        self.spin_exp_pre = QDoubleSpinBox(); self.spin_exp_pre.setRange(1.0, 80.0); self.spin_exp_pre.setValue(12.0); self.spin_exp_pre.setSuffix(" %")
        self.spin_exp_deg = QSpinBox(); self.spin_exp_deg.setRange(0, 3); self.spin_exp_deg.setValue(1)
        self.chk_match_tail = QCheckBox("Match final 5% slope (soft constraint)")
        self.chk_match_tail.setChecked(False)
        self.chk_match_tail.setToolTip("Match slope fitted to last 5% of measured PFY; this is a weighted least-squares condition, not an exact match. Auto BG only.")
        self.btn_seed_manual = QPushButton("Seed / reset manual anchors")
        self.lbl_manual_hint = QLabel("Manual: drag blue anchors in the Experimental plot."); self.lbl_manual_hint.setWordWrap(True)
        f.addRow("Mode:", self.combo_exp_bg); f.addRow("Pre-edge fraction:", self.spin_exp_pre); f.addRow("Polynomial degree:", self.spin_exp_deg); f.addRow(self.chk_match_tail); f.addRow(self.btn_seed_manual); f.addRow(self.lbl_manual_hint)
        self.form_root.addWidget(g_exp)

        g_ref = QGroupBox("Reference attenuation background"); f = QFormLayout(g_ref)
        self.spin_ref_pre = QDoubleSpinBox(); self.spin_ref_pre.setRange(1.0, 80.0); self.spin_ref_pre.setValue(12.0); self.spin_ref_pre.setSuffix(" %")
        self.lbl_p = QLabel("—"); self.lbl_fit = QLabel("—")
        self.lbl_muf_name = QLabel("μ_f at E_f:"); self.lbl_muf = QLabel("—")
        self.lbl_gmuf_name = QLabel("G μ_f:"); self.lbl_gmuf = QLabel("—")
        self.lbl_murange = QLabel("—"); self.lbl_musens = QLabel("—")
        f.addRow("Tabulated pre-edge fraction:", self.spin_ref_pre)
        f.addRow("Fit μ_bg=A E^-p, p:", self.lbl_p)
        f.addRow("Pre-edge fit RMS:", self.lbl_fit)
        f.addRow(self.lbl_muf_name, self.lbl_muf)
        f.addRow(self.lbl_gmuf_name, self.lbl_gmuf)
        f.addRow("μ_f range (±2σ):", self.lbl_murange)
        f.addRow("Attenuation variation:", self.lbl_musens)
        self.form_root.addWidget(g_ref)

        g_cal = QGroupBox("Post-edge calibration"); f = QFormLayout(g_cal)
        self.spin_cal_lo = QDoubleSpinBox(); self.spin_cal_hi = QDoubleSpinBox()
        for s in (self.spin_cal_lo, self.spin_cal_hi):
            s.setDecimals(2); s.setSuffix(" eV")
        self.lbl_c = QLabel("—"); self.lbl_ymax = QLabel("—"); self.lbl_strength = QLabel("—"); self.lbl_condmax = QLabel("—")
        f.addRow("Calibration start:", self.spin_cal_lo); f.addRow("Calibration end:", self.spin_cal_hi); f.addRow("Scale C:", self.lbl_c); f.addRow("max y=I/C:", self.lbl_ymax); f.addRow("Correction strength:", self.lbl_strength); f.addRow("Max relative amplification:", self.lbl_condmax)
        self.form_root.addWidget(g_cal)

        self.form_root.addStretch(1)

        buttons = QHBoxLayout(); self.btn_recalc = QPushButton("Recalculate"); self.btn_help = QPushButton("Help"); self.btn_close = QPushButton("Close")
        buttons.addWidget(self.btn_recalc); buttons.addStretch(); buttons.addWidget(self.btn_help); buttons.addWidget(self.btn_close); root.addLayout(buttons)

    def _connect(self):
        controls = [self.edit_formula, self.edit_element, self.combo_edge, self.combo_emission_model, self.spin_ef, self.spin_fwhm,
                    self.spin_alpha, self.spin_gamma, self.combo_exp_bg, self.spin_exp_pre, self.spin_exp_deg,
                    self.spin_ref_pre, self.spin_cal_lo, self.spin_cal_hi]
        for w in controls:
            sig = getattr(w, "valueChanged", None) or getattr(w, "currentIndexChanged", None) or getattr(w, "editingFinished", None)
            if sig is not None:
                try: sig.connect(self.recalculate)
                except Exception: pass
        self.chk_match_tail.toggled.connect(self.recalculate)
        self.combo_exp_bg.currentIndexChanged.connect(self._update_bg_controls)
        self.spin_exp_deg.valueChanged.connect(self._update_bg_controls)
        self._update_bg_controls()
        self.combo_emission_model.currentIndexChanged.connect(self._update_emission_controls)
        self.btn_recalc.clicked.connect(self.recalculate)
        self.btn_seed_manual.clicked.connect(self._seed_manual)
        self.btn_help.clicked.connect(lambda: _HelpDialog(self).exec())
        self.btn_close.clicked.connect(self.accept)
        self.canvas.mpl_connect("pick_event", self._on_pick)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

    def _update_emission_controls(self, *args):
        is_gaussian = self.combo_emission_model.currentText() == "Gaussian"
        self.spin_fwhm.setEnabled(is_gaussian)
        self.lbl_murange.setEnabled(is_gaussian)
        self.lbl_musens.setEnabled(is_gaussian)
        if is_gaussian:
            self.lbl_muf_name.setText("Weighted mean μ_f:")
            self.lbl_gmuf_name.setText("G ⟨μ_f⟩ (diagnostic):")
        else:
            self.lbl_muf_name.setText("μ_f at E_f:")
            self.lbl_gmuf_name.setText("G μ_f:")
            self.lbl_murange.setText("—")
            self.lbl_musens.setText("—")

    def _seed_ranges(self):
        lo = float(np.nanmin(self.x)); hi = float(np.nanmax(self.x)); span = hi - lo
        for s in (self.spin_cal_lo, self.spin_cal_hi): s.setRange(lo, hi)
        self.spin_cal_lo.setValue(lo + 0.80 * span); self.spin_cal_hi.setValue(hi)
        self._seed_manual()

    def _seed_manual(self):
        bg = _poly_background(self.x, self.y, self.spin_exp_pre.value()/100.0, self.spin_exp_deg.value())
        n = max(2, self.spin_exp_deg.value() + 1)
        idx = np.linspace(0, len(self.x)-1, n).round().astype(int)
        self._manual_points = [[float(self.x[i]), float(bg[i])] for i in np.unique(idx)]
        self.recalculate()

    def _manual_background(self):
        if len(self._manual_points) < 2:
            return _poly_background(self.x, self.y, self.spin_exp_pre.value()/100.0, self.spin_exp_deg.value())
        pts = np.asarray(self._manual_points, dtype=float)
        deg = min(self.spin_exp_deg.value(), len(pts)-1)
        x0 = float(np.mean(pts[:,0])); span = float(np.ptp(pts[:,0])) or 1.0
        p = np.polyfit((pts[:,0]-x0)/span, pts[:,1], deg)
        return np.polyval(p, (self.x-x0)/span)

    def _update_bg_controls(self, *args):
        self.chk_match_tail.setEnabled(self.combo_exp_bg.currentText() == "Auto" and self.spin_exp_deg.value() > 1)

    def _bg_slope_report(self):
        if self.combo_exp_bg.currentText() != "Auto":
            return ["  Final 5% slope match: not used (Auto BG only)"]
        d = getattr(self, "_exp_bg_slope_info", None)
        if d is None: return []
        return [
            f"  Final 5% slope constraint: {'ON (soft)' if d.slope_constrained else 'OFF'}",
            f"  Tail points: {d.tail_points}    Pre-edge fit points: {d.preedge_points}",
            f"  Measured tail slope: {d.tail_slope:.6g} PFY/eV",
            f"  Fitted BG end slope: {d.fitted_end_slope:.6g} PFY/eV",
            f"  End-slope mismatch: {d.fitted_end_slope - d.tail_slope:+.6g} PFY/eV",
        ]

    def _experimental_bg(self):
        mode = self.combo_exp_bg.currentText()
        if mode == "None": return np.zeros_like(self.y)
        if mode == "Manual": return self._manual_background()
        bg, self._exp_bg_slope_info = fit_experimental_background(
            self.x, self.y, self.spin_exp_pre.value()/100.0, self.spin_exp_deg.value(),
            match_tail_slope=(self.chk_match_tail.isChecked() and self.spin_exp_deg.value() > 1))
        return bg

    def _on_pick(self, event):
        if self.combo_exp_bg.currentText() != "Manual": return
        idx = getattr(event.artist, "_sa_anchor_index", None)
        if idx is not None: self._drag_manual = int(idx)

    def _on_motion(self, event):
        if self._drag_manual is None or event.inaxes is not self.ax_exp or event.xdata is None or event.ydata is None: return
        i = self._drag_manual
        if 0 <= i < len(self._manual_points):
            self._manual_points[i] = [float(event.xdata), float(event.ydata)]
            self.recalculate()

    def _on_release(self, event): self._drag_manual = None

    def _plot_manual_anchors(self):
        if self.combo_exp_bg.currentText() != "Manual": return
        for i, (x, y) in enumerate(self._manual_points):
            line, = self.ax_exp.plot([x], [y], "o", ms=7, picker=7, label="Manual anchors" if i == 0 else "_nolegend_")
            line._sa_anchor_index = i

    def _gaussian_model(self, formula, geom, ref):
        profile = gaussian_emission_profile(self.spin_ef.value(), self.spin_fwhm.value())
        mu_f_values = np.asarray(compound_mu_total(profile.energy_eV, formula, self.db), dtype=float)
        q = forward_fraction_distribution(ref.mu_target_tab, ref.mu_bg, mu_f_values, profile.weights, geom.factor)
        weighted_mu = float(np.sum(profile.weights * mu_f_values))
        sigma = profile.fwhm_eV / (2.0 * math.sqrt(2.0 * math.log(2.0)))
        central = np.abs(profile.energy_eV - profile.center_eV) <= 2.0 * sigma
        if not np.any(central): central = np.ones_like(mu_f_values, dtype=bool)
        lo = float(np.min(mu_f_values[central])); hi = float(np.max(mu_f_values[central]))
        variation = 100.0 * (hi - lo) / weighted_mu if weighted_mu > 0 else float("nan")
        return profile, mu_f_values, q, weighted_mu, lo, hi, variation

    def recalculate(self, *args):
        try:
            self._update_emission_controls()
            exp_bg = self._experimental_bg()
            signal = self.y - exp_bg
            geom = flexpes_geometry(self.spin_alpha.value(), self.spin_gamma.value())
            self.lbl_beta.setText(f"{geom.beta_deg:.3f}°"); self.lbl_g.setText(f"{geom.factor:.5g}")
            formula = self.edit_formula.text().strip()
            ref = build_reference_model(self.x, formula, self.spin_ef.value(), self.db, preedge_fraction=self.spin_ref_pre.value()/100.0)

            model = self.combo_emission_model.currentText()
            profile = None; mu_f_values = None; variation = None
            if model == "Gaussian":
                profile, mu_f_values, q, weighted_mu, mu_lo, mu_hi, variation = self._gaussian_model(formula, geom, ref)
                self.lbl_muf.setText(f"{weighted_mu:.6g} cm²/g")
                self.lbl_gmuf.setText(f"{geom.factor*weighted_mu:.6g} cm²/g")
                self.lbl_murange.setText(f"{mu_lo:.5g} – {mu_hi:.5g} cm²/g")
                self.lbl_musens.setText(f"{variation:.3g} %")
            else:
                d = denominator_term(ref.mu_bg, ref.mu_f, geom.factor)
                q = np.divide(ref.mu_target_tab, ref.mu_target_tab + d, out=np.zeros_like(d), where=(ref.mu_target_tab+d)>0)
                self.lbl_muf.setText(f"{ref.mu_f:.6g} cm²/g")
                self.lbl_gmuf.setText(f"{geom.factor*ref.mu_f:.6g} cm²/g")

            interval_mask = (self.x >= self.spin_cal_lo.value()) & (self.x <= self.spin_cal_hi.value())
            finite_signal = np.isfinite(signal)
            finite_reference = np.isfinite(q)
            cal_mask = interval_mask & finite_signal & (signal > 0) & finite_reference & (q > 0)
            if np.count_nonzero(cal_mask) < 2:
                self._show_calibration_failure(exp_bg, signal, ref, q, interval_mask, cal_mask)
                return
            cal = calibrate(signal, q, mask=cal_mask)

            if model == "Gaussian":
                corrected = invert_thick_distribution(signal, cal.scale_c, ref.mu_bg, mu_f_values, profile.weights, geom.factor)
                cond = relative_condition_amplification_distribution(corrected, ref.mu_bg, mu_f_values, profile.weights, geom.factor)
            else:
                corrected = invert_thick(signal, cal.scale_c, ref.mu_bg, ref.mu_f, geom.factor)
                cond = np.divide(1.0, 1.0-cal.y, out=np.full_like(cal.y, np.nan), where=np.isfinite(cal.y)&(cal.y<1))

            # Calibration diagnostics: all quantities use the same fitted C as the inversion.
            predicted = cal.scale_c * np.asarray(q, dtype=float)
            usable = cal_mask & np.isfinite(predicted) & (predicted > 0)
            measured_cal = signal[usable]
            predicted_cal = predicted[usable]
            ratio = measured_cal / predicted_cal
            residual = measured_cal - predicted_cal
            rms_relative = 100.0 * float(np.sqrt(np.mean((ratio - 1.0)**2)))
            rms_signal = 100.0 * float(np.sqrt(np.mean(residual**2)) / np.mean(predicted_cal))
            ratio_min, ratio_max = float(np.min(ratio)), float(np.max(ratio))
            slope = float(np.polyfit(self.x[usable], ratio, 1)[0]) if np.count_nonzero(usable) >= 3 else float('nan')
            slope_percent_10ev = 100.0 * slope * 10.0

            finite_cond = cond[np.isfinite(cond)]
            cond_max = float(np.nanmax(finite_cond)) if finite_cond.size else float("inf")
            self.lbl_p.setText(f"{ref.power_law.exponent:.5g}")
            self.lbl_fit.setText(f"{100*ref.power_law.rms_relative:.3g} %")
            self.lbl_c.setText(f"{cal.scale_c:.6g}")
            self.lbl_ymax.setText(f"{cal.y_max:.5g}")
            self.lbl_strength.setText(correction_strength_label(cal.y_max))
            self.lbl_condmax.setText("∞" if not np.isfinite(cond_max) else f"{cond_max:.4g}")

            warns = []
            if cal.y_max >= 1:
                warns.append("Calibrated y reaches/exceeds 1: inversion is singular/non-physical for this model and calibration.")
            elif cal.y_max >= 0.8:
                warns.append("Very strong correction: small intensity/calibration errors will be strongly amplified.")
            if ref.power_law.rms_relative > 0.02:
                warns.append("Reference pre-edge power-law fit residual exceeds 2%.")
            if rms_relative > 5.0:
                warns.append(f"Calibration mismatch: relative RMS is {rms_relative:.2f}% (measured vs C × q_tab).")
            if abs(slope_percent_10ev) > 5.0:
                warns.append(f"Calibration ratio has a systematic slope of {slope_percent_10ev:+.2f}% per 10 eV.")
            if np.count_nonzero(cal_mask) < 3:
                warns.append("Calibration interval contains very few usable points.")
            if np.nanmin(signal) < 0:
                warns.append("Experimental BG subtraction produces negative intensities in part of the scan.")
            if model == "Gaussian":
                warns.append(f"Gaussian model: center {profile.center_eV:.2f} eV, physical FWHM {profile.fwhm_eV:.2f} eV. The SDD resolution must not be used as this width.")
                if np.isfinite(variation) and variation >= 50:
                    warns.append("HIGH fluorescence-energy sensitivity: attenuation changes by at least 50% across ±2σ of the emission distribution.")
                elif np.isfinite(variation) and variation >= 20:
                    warns.append("Fluorescence-energy sensitivity is substantial: attenuation changes by at least 20% across ±2σ.")
                warns.append("Gaussian Level 1.5 assumes a fixed emission distribution independent of incident photon energy.")
            else:
                warns.append("Single-energy model assumes the selected PFY ROI is dominated by one physical fluorescence energy E_f.")
            if self.combo_edge.currentText().startswith(("L", "M")):
                warns.append("L/M-edge warning: multiple decay channels and incident-energy-dependent resonant emission can limit either fluorescence model.")
            warns.append("Atomic/tabulated target-edge structure is used only for post-edge calibration, not as the recovered NEXAFS fine structure.")
            valid_cal = int(np.count_nonzero(cal_mask))
            cal_q = np.asarray(q)[cal_mask]
            diagnostics = [
                "MODEL / GEOMETRY",
                f"  Composition: {formula}    Absorber: {self.edit_element.text().strip()} {self.combo_edge.currentText()}",
                f"  Fluorescence: {model}    Center / E_f: {self.spin_ef.value():.2f} eV",
                f"  Gaussian physical FWHM: {self.spin_fwhm.value():.2f} eV" if model == "Gaussian" else "  Single physical fluorescence energy",
                f"  Incidence α: {self.spin_alpha.value():.2f}°    Tilt γ: {self.spin_gamma.value():.2f}°",
                f"  Exit β: {geom.beta_deg:.4f}°    G: {geom.factor:.6g}",
                "",
                "REFERENCE / FLUORESCENCE ATTENUATION",
                "  Database: Chantler / XrayDB (bundled)",
                f"  Reference pre-edge fraction: {self.spin_ref_pre.value():.2f}%",
                f"  μ_bg = A E^(-p): p = {ref.power_law.exponent:.6g}",
                f"  Relative pre-edge fit RMS: {100*ref.power_law.rms_relative:.5g}%",
                f"  Mean μ_f: {float(self.lbl_muf.text().split()[0]):.6g} cm²/g",
                f"  G × mean μ_f: {float(self.lbl_gmuf.text().split()[0]):.6g} cm²/g",
            ]
            if model == "Gaussian":
                diagnostics.extend([
                    f"  μ_f within ±2σ: {mu_lo:.6g} – {mu_hi:.6g} cm²/g",
                    f"  Attenuation variation: {variation:.4g}%",
                ])
            diagnostics.extend([
                "",
                "EXPERIMENTAL BG / POST-EDGE CALIBRATION",
                f"  BG mode: {self.combo_exp_bg.currentText()}    Pre-edge fraction: {self.spin_exp_pre.value():.2f}%    Degree: {self.spin_exp_deg.value()}",
                f"  Calibration interval: {self.spin_cal_lo.value():.2f} – {self.spin_cal_hi.value():.2f} eV",
                f"  Usable calibration points: {valid_cal}",
                f"  Tabulated forward fraction q in interval: {float(np.nanmin(cal_q)):.6g} – {float(np.nanmax(cal_q)):.6g}" if valid_cal else "  Tabulated forward fraction q: unavailable",
                f"  Scale C: {cal.scale_c:.7g}",
                f"  Calibration fit RMS (ratio to model): {rms_relative:.5g}%",
                f"  Calibration fit RMS (signal / mean model): {rms_signal:.5g}%",
                f"  Measured / predicted ratio range: {ratio_min:.6g} – {ratio_max:.6g}",
                f"  Ratio slope: {slope_percent_10ev:+.5g}% per 10 eV",
                f"  Maximum y = I/C: {cal.y_max:.6g}",
                f"  Correction strength: {correction_strength_label(cal.y_max)}",
                f"  Maximum relative inversion amplification: {cond_max:.6g}",
                "",
                "WARNINGS / MODEL LIMITATIONS",
            ])
            diagnostics.extend("  • " + w for w in warns)
            diagnostics.extend(["", "EXPERIMENTAL BG END-SLOPE DIAGNOSTICS", *self._bg_slope_report()])
            self.lbl_status.setPlainText("\n".join(diagnostics))
            self._draw(exp_bg, signal, ref, geom, cal, corrected, cal_mask, cond, model, profile, mu_f_values)
        except Exception as exc:
            self.lbl_status.setPlainText(f"CALCULATION STOPPED\n{exc}")
            for lab in (self.lbl_c, self.lbl_ymax, self.lbl_strength, self.lbl_condmax): lab.setText("—")
            self._draw_error(str(exc))

    def _draw(self, exp_bg, signal, ref, geom, cal, corrected, cal_mask, cond, model, profile, mu_f_values):
        for ax in (self.ax_exp, self.ax_ref, self.ax_out, self.ax_diag, self.ax_cal, self.ax_ratio): ax.clear()
        self.ax_exp.plot(self.x, self.y, label="PFY / I₀ input")
        self.ax_exp.plot(self.x, exp_bg, "--", label="Experimental BG")
        self.ax_exp.plot(self.x, signal, label="BG-subtracted PFY")
        self._plot_manual_anchors(); self.ax_exp.set_title("Experimental signal"); self.ax_exp.set_xlabel("Photon energy (eV)"); self.ax_exp.legend(fontsize=8)

        self.ax_ref.plot(self.x, ref.mu_total, label="Chantler compound μ total")
        self.ax_ref.plot(self.x, ref.mu_bg, "--", label="Fitted μ_bg")
        self.ax_ref.plot(self.x, ref.mu_target_tab, label="Tabulated target-edge contribution")
        if model == "Gaussian":
            weighted_mu = float(np.sum(profile.weights * mu_f_values))
            self.ax_ref.axhline(geom.factor*weighted_mu, linestyle=":", label="G ⟨μ_f⟩ (diagnostic)")
        else:
            self.ax_ref.axhline(geom.factor*ref.mu_f, linestyle=":", label="G μ_f")
        self.ax_ref.set_title("Reference attenuation model"); self.ax_ref.set_xlabel("Photon energy (eV)"); self.ax_ref.set_ylabel("cm²/g"); self.ax_ref.legend(fontsize=8)

        norm_mask = cal_mask & np.isfinite(corrected)
        scale_corr = float(np.nanmean(corrected[norm_mask])) if np.any(norm_mask) else 1.0
        scale_sig = float(np.nanmean(signal[cal_mask])) if np.any(cal_mask) else 1.0
        if not np.isfinite(scale_corr) or abs(scale_corr)<1e-30: scale_corr=1.0
        if not np.isfinite(scale_sig) or abs(scale_sig)<1e-30: scale_sig=1.0
        self.ax_out.plot(self.x, signal/scale_sig, label="Input PFY (post-edge norm.)")
        self.ax_out.plot(self.x, corrected/scale_corr, label="Corrected μ_X (post-edge norm.)")
        self.ax_out.axvspan(self.spin_cal_lo.value(), self.spin_cal_hi.value(), alpha=0.12, label="Calibration")
        self.ax_out.set_title("Shape comparison (diagnostic only)"); self.ax_out.set_xlabel("Photon energy (eV)"); self.ax_out.legend(fontsize=8)

        self.ax_diag.plot(self.x, cal.y, label="y = I/C")
        self.ax_diag.plot(self.x, cond, label="relative inversion amplification")
        self.ax_diag.axhline(1.0, linestyle=":", linewidth=1)
        self.ax_diag.set_title("Conditioning diagnostics"); self.ax_diag.set_xlabel("Photon energy (eV)"); self.ax_diag.legend(fontsize=8)

        # Show only the calibration interval with a small horizontal margin.
        predicted = cal.scale_c * np.asarray(ref.mu_target_tab / (ref.mu_target_tab + denominator_term(ref.mu_bg, ref.mu_f, geom.factor)), dtype=float) if model == "Single energy" else None
        # For both models, q(E) is recovered from the same calibration relation in recalculate().
        if model == "Gaussian":
            predicted = cal.scale_c * forward_fraction_distribution(ref.mu_target_tab, ref.mu_bg, mu_f_values, profile.weights, geom.factor)
        mask = cal_mask & np.isfinite(predicted) & (predicted > 0)
        self.ax_cal.plot(self.x[mask], signal[mask], label="Measured BG-subtracted PFY")
        self.ax_cal.plot(self.x[mask], predicted[mask], "--", label="C × q_tab (reference model)")
        self.ax_cal.set_title("Post-edge calibration: measured vs predicted")
        self.ax_cal.set_xlabel("Photon energy (eV)"); self.ax_cal.legend(fontsize=8)
        self.ax_ratio.plot(self.x[mask], signal[mask] / predicted[mask], label="Measured / predicted")
        self.ax_ratio.axhline(1.0, linestyle=":", linewidth=1, label="Ideal = 1")
        self.ax_ratio.set_title("Calibration ratio (post-edge)")
        self.ax_ratio.set_xlabel("Photon energy (eV)"); self.ax_ratio.legend(fontsize=8)
        for ax in (self.ax_cal, self.ax_ratio):
            ax.margins(x=0.08)
        self.canvas.draw_idle()

    def _show_calibration_failure(self, exp_bg, signal, ref, q, interval_mask, cal_mask):
        """Explain invalid calibration points without hiding the fitted experimental BG."""
        n_interval = int(np.count_nonzero(interval_mask))
        invalid_signal = interval_mask & ~np.isfinite(signal)
        nonpositive_signal = interval_mask & np.isfinite(signal) & (signal <= 0)
        invalid_reference = interval_mask & ~np.isfinite(q)
        nonpositive_reference = interval_mask & np.isfinite(q) & (q <= 0)
        n_valid = int(np.count_nonzero(cal_mask))
        lines = [
            "CALIBRATION CANNOT BE COMPUTED",
            f"  Interval: {self.spin_cal_lo.value():.2f} – {self.spin_cal_hi.value():.2f} eV",
            f"  Points within interval: {n_interval}",
            f"  Usable points (positive, finite signal and reference): {n_valid} (minimum: 2)",
            f"  Nonpositive BG-subtracted PFY: {int(np.count_nonzero(nonpositive_signal))}",
            f"  Non-finite BG-subtracted PFY: {int(np.count_nonzero(invalid_signal))}",
            f"  Nonpositive tabulated forward fraction q: {int(np.count_nonzero(nonpositive_reference))}",
            f"  Non-finite tabulated forward fraction q: {int(np.count_nonzero(invalid_reference))}",
            "  Counts may overlap when both signal and reference are invalid.",
        ]
        if np.any(interval_mask & np.isfinite(signal)):
            values = signal[interval_mask & np.isfinite(signal)]
            lines.append(f"  BG-subtracted PFY range in interval: {np.min(values):.6g} – {np.max(values):.6g}")
        if np.count_nonzero(nonpositive_signal):
            lines.append("  Experimental BG is at or above the measured PFY for some calibration points.")
            lines.append("  Inspect the orange BG extrapolation in the experimental plot; try degree 0/1 or Manual BG.")
        if n_interval < 2:
            lines.append("  Choose a wider calibration interval containing at least two scan points.")
        if np.count_nonzero(invalid_reference | nonpositive_reference):
            lines.append("  Check the tabulated edge contribution and selected reference interval.")
        lines.extend(["", "EXPERIMENTAL BG END-SLOPE DIAGNOSTICS", *self._bg_slope_report()])
        self.lbl_status.setPlainText("\n".join(lines))
        for lab in (self.lbl_c, self.lbl_ymax, self.lbl_strength, self.lbl_condmax):
            lab.setText("—")
        for ax in (self.ax_exp, self.ax_ref, self.ax_out, self.ax_diag, self.ax_cal, self.ax_ratio):
            ax.clear()
        self.ax_exp.plot(self.x, self.y, label="PFY / I₀ input")
        self.ax_exp.plot(self.x, exp_bg, "--", label="Experimental BG")
        self.ax_exp.plot(self.x, signal, label="BG-subtracted PFY")
        self._plot_manual_anchors()
        self.ax_exp.axvspan(self.spin_cal_lo.value(), self.spin_cal_hi.value(), alpha=0.12, label="Calibration")
        self.ax_exp.set_title("Experimental signal / BG diagnostics")
        self.ax_exp.set_xlabel("Photon energy (eV)")
        self.ax_exp.legend(fontsize=8)
        self.ax_ref.plot(self.x, ref.mu_total, label="Chantler compound μ total")
        self.ax_ref.plot(self.x, ref.mu_bg, "--", label="Fitted μ_bg")
        self.ax_ref.plot(self.x, ref.mu_target_tab, label="Tabulated target-edge contribution")
        self.ax_ref.set_title("Reference attenuation model")
        self.ax_ref.set_xlabel("Photon energy (eV)")
        self.ax_ref.legend(fontsize=8)
        self.ax_cal.plot(self.x[interval_mask], signal[interval_mask], label="BG-subtracted PFY")
        self.ax_cal.axhline(0.0, linestyle=":", label="Zero signal")
        self.ax_cal.set_title("Calibration signal (invalid points visible)")
        self.ax_cal.set_xlabel("Photon energy (eV)")
        self.ax_cal.legend(fontsize=8)
        self.ax_out.text(0.5, 0.5, "Correction not computed: calibration invalid", ha="center", va="center", transform=self.ax_out.transAxes, wrap=True)
        self.ax_ratio.text(0.5, 0.5, "Measured/predicted ratio unavailable", ha="center", va="center", transform=self.ax_ratio.transAxes)
        self.canvas.draw_idle()

    def _draw_error(self, message):
        for ax in (self.ax_exp, self.ax_ref, self.ax_out, self.ax_diag, self.ax_cal, self.ax_ratio): ax.clear()
        self.ax_exp.plot(self.x, self.y); self.ax_exp.set_title("Experimental signal")
        self.ax_ref.text(0.5,0.5,message,ha="center",va="center",transform=self.ax_ref.transAxes,wrap=True); self.ax_ref.set_axis_off()
        self.canvas.draw_idle()
