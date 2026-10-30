# PFY self-absorption correction — experimental workflow

## Purpose

This dialog is an **isolated development workflow** for testing self-absorption/saturation corrections of fluorescence-yield (PFY) NEXAFS spectra. Corrected curves remain inside this dialog and are **not** sent to Processed Data or Plotted Data.

The current implementation assumes a homogeneous, effectively semi-infinite sample and offers two fluorescence models:

1. **Single energy** — one physical fluorescence photon energy.
2. **Gaussian** — a fixed physical fluorescence-energy distribution with selectable center and FWHM.

The Gaussian model is a deliberate intermediate step between the single-energy approximation and a future treatment of the full incident-energy-dependent fluorescence spectrum.

**How to use:** Choose a PFY signal normalized by \(I_0\) in Processed Data, open the correction window, enter sample/edge and the physical fluorescence model, check the experimental BG, reference pre-edge and post-edge calibration, and assess the calibration ratio and inverse-amplification plots. The correction is exploratory and does not modify data in the main window. You can leave both windows open; closing the main EXACT window also closes this tool window.

---

## Essential quantities

- \(\mu_X(E)\) — absorption coefficient of the element/shell whose XAS is sought.
- \(\mu_{\mathrm{tot}}(E)\) — total attenuation of the incident beam by the complete material.
- \(\mu_{\mathrm{bg}}(E)\) — all incident-beam attenuation except the target-shell contribution.
- \(\mu_f=\mu_{\mathrm{tot}}(E_f)\) — total attenuation at one fluorescence energy in the single-energy model.
- \(S(E_f)\) — normalized physical fluorescence-energy distribution in the Gaussian model.
- \(C\) — experimental scale factor containing detector efficiency, solid angle, ROI scaling and other approximately energy-independent factors.

The attenuation decomposition is

$$
\mu_{\mathrm{tot}}(E)=\mu_X(E)+\mu_{\mathrm{bg}}(E).
$$

The **experimental PFY background** is a different object from \(\mu_{\mathrm{bg}}(E)\). Experimental BG removes detector/scattering/ROI baseline from the measured PFY signal. \(\mu_{\mathrm{bg}}(E)\) is a physical attenuation term constructed independently from reference data.

---

## Geometry

Angles are measured relative to the sample surface. \(\alpha=90^\circ\) is normal incidence.

For the current FlexPES geometry, the detector is 90° from the incident beam and the beam–detector plane is tilted around the incident-beam axis by \(\gamma\):

$$
\sin\beta=\cos\alpha\cos\gamma
$$

and

$$
G=\frac{\sin\alpha}{\sin\beta}=\frac{\tan\alpha}{\cos\gamma}.
$$

Larger \(\alpha\) makes the fluorescence exit more grazing. This lowers detected intensity but makes the effective sampling depth shallower, which can reduce saturation distortion.

---

# Model 1 — Single physical fluorescence energy

## Forward model

For one physical fluorescence energy \(E_f\), define

$$
\mu_f=\mu_{\mathrm{tot}}(E_f).
$$

The thick-sample forward model is

$$
I_{\mathrm{PFY}}(E)
= C\,\frac{\mu_X(E)}
{\mu_X(E)+\mu_{\mathrm{bg}}(E)+G\mu_f}.
$$

Define

$$
D(E)=\mu_{\mathrm{bg}}(E)+G\mu_f,
\qquad
y(E)=\frac{I_{\mathrm{PFY}}(E)}{C}.
$$

The inversion is analytic:

$$
\mu_X(E)=D(E)\,\frac{y(E)}{1-y(E)}.
$$

For positive attenuation coefficients, the forward model requires \(0\le y(E)<1\). The inversion is invalid when

$$
y(E)\ge 1.
$$

The relative inversion amplification is

$$
A_{\mathrm{rel}}(E)=\frac{1}{1-y(E)}.
$$

### Important input rule

\(E_f\) is the **physical fluorescence photon energy in eV**, not the Xspress3 MCA channel number and not the center of an uncalibrated detector pulse-height peak.

---

# Model 2 — Gaussian fluorescence-energy distribution

## Why use a distribution?

If \(\mu_{\mathrm{tot}}(E_f)\) changes strongly over the physical emission band, a single-energy approximation can be extremely unstable. This is particularly important when an emission band lies close to an absorption edge, as can occur for transition-metal \(L\) emission.

The Gaussian model assumes that the **normalized physical emission profile is independent of incident energy**, which can fail at resonant transition-metal edges, throughout the NEXAFS scan:

$$
S(E_f)=\frac{1}{\sigma\sqrt{2\pi}}
\exp\left[-\frac{(E_f-E_c)^2}{2\sigma^2}\right],
\qquad
\int S(E_f)\,dE_f=1.
$$

The dialog specifies the distribution by its center \(E_c\) and FWHM:

$$
\mathrm{FWHM}=2\sqrt{2\ln2}\,\sigma.
$$

### Critical distinction from detector resolution

The Gaussian FWHM is the **physical emission width before the photon leaves the sample**. It is **not** the SDD pulse-height resolution. For example, an approximately 120 eV SDD resolution must not be entered as the fluorescence FWHM.

## Forward model

The thick-sample model becomes

$$
I_{\mathrm{PFY}}(E)
= C\,\mu_X(E)
\int
\frac{S(E_f)}
{\mu_X(E)+\mu_{\mathrm{bg}}(E)+G\mu_{\mathrm{tot}}(E_f)}
\,dE_f.
$$

For calibration, the same integral is evaluated using the tabulated target-shell contribution \(\mu_{X,\mathrm{tab}}(E)\).

## Numerical inversion

There is no longer a simple analytic expression for \(\mu_X(E)\). At every incident energy EXACT solves the monotonic scalar equation

$$
\frac{I_{\mathrm{PFY}}(E)}{C}
=
\mu_X(E)
\int
\frac{S(E_f)}
{\mu_X(E)+\mu_{\mathrm{bg}}(E)+G\mu_{\mathrm{tot}}(E_f)}
\,dE_f
$$

numerically for \(\mu_X(E)\).

This model reduces continuously toward the single-energy case as the physical fluorescence width tends toward zero.

## Conditioning diagnostic

For the distribution model define

$$
q(\mu_X)=
\mu_X
\int
\frac{S(E_f)}
{\mu_X+\mu_{\mathrm{bg}}+G\mu_{\mathrm{tot}}(E_f)}
\,dE_f.
$$

The relative inverse amplification displayed by EXACT (local sensitivity of the inferred attenuation to a relative PFY change when the calibration is held fixed) is

$$
A_{\mathrm{rel}}
=
\frac{q}{\mu_X\,dq/d\mu_X}.
$$

For a single fluorescence energy this reduces exactly to

$$
A_{\mathrm{rel}}=\frac{1}{1-y}.
$$

---

## Experimental PFY background

The dialog offers an empirical background for the measured PFY normalized by \(I_0\):

- **Auto** — polynomial fit to a selected pre-edge fraction. For polynomial degree 2 or 3, an optional checkbox **Match final 5% slope (soft constraint)** adds the main EXACT end-slope condition. It is unchecked by default, and unavailable for degrees 0 and 1;
- **Manual** — polynomial through draggable blue anchor points;
- **None** — no additive experimental baseline subtraction.

For the constrained Auto BG, the slope \(m_{\mathrm{tail}}\) of a linear fit to
the last 5% of the measured \(I_0\)-normalized PFY is used as an
additional weighted least-squares condition on the derivative of the BG at the
final photon energy. In terms of normalized energy \(u\) and a polynomial \(B(u)\),
the fit minimizes

$$
\sum_{i\in\mathrm{pre}}\left[B(u_i)-F_i\right]^2
+ w^2\left[B'(u_{\max}) - m_{\mathrm{tail}}\frac{dE}{du}\right]^2.
$$

Here \(w\) is the median Euclidean norm of the pre-edge design-matrix rows,
matching the main EXACT processing method. The slope condition is **soft**:
the final fitted BG derivative need not equal the measured tail slope exactly.
The option is available only for degrees 2 and 3. The Diagnostics pane reports
both slopes and their difference. For Manual and None BG, this condition is not
used.

**Important:** matching the end slope is an empirical stabilizer, not a
physical requirement. A rising tail may contain real absorption structure,
so examine the fitted BG across the entire scan and the post-edge calibration
ratio. The checkbox defaults to **off**, so degree-0/1 and unconstrained fits retain the previous behavior.

This background is intentionally empirical and is not interpreted as an attenuation coefficient.

---

## Reference attenuation background

EXACT calculates the compound Chantler mass attenuation coefficient from the frozen local reference database.

The tabulated pre-edge is fitted with

$$
\mu_{\mathrm{bg}}(E)=A E^{-p}
$$

and extrapolated through the target-edge region. The fitted exponent \(p\) is a diagnostic and is not forced to 3 or 4.

The tabulated target-edge contribution used for calibration is approximated by

$$
\mu_{X,\mathrm{tab}}(E)
=\max\left[\mu_{\mathrm{tot,tab}}(E)-\mu_{\mathrm{bg}}(E),\,0\right].
$$

This atomic/tabulated edge curve is **only a post-edge calibration aid**. It must not replace the measured solid-state NEXAFS fine structure near the edge.

---

## Post-edge calibration

The scale factor \(C\) is determined over the selected post-edge interval by least squares, using the positive, finite background-subtracted points and valid tabulated forward fractions.

For the single-energy model:

$$
q(E)=
\frac{\mu_{X,\mathrm{tab}}(E)}
{\mu_{X,\mathrm{tab}}(E)+\mu_{\mathrm{bg}}(E)+G\mu_f}.
$$

For the Gaussian model:

$$
q(E)=
\mu_{X,\mathrm{tab}}(E)
\int
\frac{S(E_f)}
{\mu_{X,\mathrm{tab}}(E)+\mu_{\mathrm{bg}}(E)+G\mu_{\mathrm{tot}}(E_f)}
\,dE_f.
$$

In both cases EXACT fits

$$
I^*_{\mathrm{PFY}}(E)=C\,q(E)
$$

across the complete selected calibration interval, where \(I^*_{\mathrm{PFY}}\) is the PFY signal normalized by \(I_0\) after the chosen experimental-background subtraction.

---

## Fluorescence-energy sensitivity

For the Gaussian model EXACT evaluates \(\mu_{\mathrm{tot}}(E_f)\) across the physical emission distribution and reports the attenuation range within approximately \(\pm 2\sigma\).

Large variation means that the correction is intrinsically sensitive to the emission-energy model. This is particularly important near absorption edges.

The weighted mean attenuation shown in the dialog is only a **diagnostic**:

$$
\langle\mu_f\rangle
=\int S(E_f)\,\mu_{\mathrm{tot}}(E_f)\,dE_f.
$$

The Gaussian correction itself uses the full integral and does **not** replace the distribution by \(\langle\mu_f\rangle\).

---

## SDD resolution and ROI

The SDD resolution acts **after** the photon has escaped from the sample. It therefore does not define the self-absorption energy distribution.

A broad SDD ROI can be necessary for counting statistics. The correction assumes that the selected ROI is dominated by the fluorescence channel or emission band described by the chosen model.

Unresolved fluorescence/scattering channels that change with incident energy can make either model unreliable.

---

## L/M-edge warning

At transition-metal L and M edges, several complications can occur:

- several radiative decay channels;
- Coster–Kronig processes;
- emission distributions that change with incident photon energy;
- strong variation of \(\mu_{\mathrm{tot}}(E_f)\) across the emission band.

The Gaussian model improves the treatment of a finite physical emission width but still assumes

$$
S(E_f,E_{\mathrm{in}})\approx A(E_{\mathrm{in}})S(E_f).
$$

A future treatment may need the full incident-energy-dependent fluorescence map.

---

## Diagnostics to watch

- \(\max y\) approaching 1;
- large relative inversion amplification;
- strong variation of attenuation across a Gaussian emission band;
- large or unstable changes when experimental BG is adjusted;
- poor power-law fit of the tabulated pre-edge;
- strong dependence on the post-edge calibration interval;
- negative BG-subtracted PFY intensities;
- corrected resonances that diverge or acquire artificial structure.

These are warnings about model validity. They should not be hidden by smoothing or by tuning fluorescence parameters merely to make the corrected spectrum resemble another detection channel.

---

## Selected references and data sources

1. **ParSeq-XAS self-absorption documentation** — practical implementation based on the Iida/Noma formalism, including tabulated background extrapolation and calibration.  
   https://github.com/kklmn/ParSeq-XAS/blob/a47a7999572ba1e45e5fa059fff54232a0a6faa1/parseq_XAS/doc/self-absorption.rst

2. **Iida, A. & Noma, T.** Correction of the self-absorption effect in fluorescence X-ray absorption fine structure. *Jpn. J. Appl. Phys.* **32** (1993).

3. **Eisebitt, S. et al.** Determination of absorption coefficients for concentrated samples by fluorescence detection. *Phys. Rev. B* **47**, 14103 (1993).

4. **Booth, C. H. & Bridges, F.** Improved self-absorption correction for fluorescence measurements of extended X-ray absorption fine structure. *Phys. Scr.* **T115**, 202 (2005).

5. **Trevorah, R. M. et al.** Solving self-absorption in fluorescence. *IUCrJ* **6**, 586–602 (2019).

6. **Chantler / NIST FFAST** — primary tabulated attenuation reference used by the correction backend. EXACT ships a frozen local copy for reproducibility.


## Calibration-quality diagnostics

The calibration plots show the background-subtracted experimental PFY
\(F_{\mathrm{exp}}(E)\) and the reference prediction

$$
F_{\mathrm{ref}}(E)=Cq_{\mathrm{tab}}(E),
$$

using the **same least-squares scale** $C$ employed in the correction.
A second plot displays

$$
R(E)=\frac{F_{\mathrm{exp}}(E)}{Cq_{\mathrm{tab}}(E)}.
$$

If calibration is consistent, \(R(E)\) should fluctuate around unity without
systematic slope. The Diagnostics pane displays two RMS measures, the minimum
and maximum of \(R\) in the calibration interval, and the linear slope of \(R\)
reported as percent per 10 eV. These are **fit diagnostics**, not statistical
uncertainty estimates and not a validation of the fluorescence-channel model.

For a controlled test, hold the fluorescence model, geometry and reference
pre-edge fixed while moving the post-edge calibration interval. Examine the
ratio plot before modifying the experimental BG polynomial degree. A quadratic pre-edge fit can extrapolate very strongly over a long energy interval. The optional final-5% slope constraint may stabilize it; compare
on/off fits and use it only if its full-range shape is credible.
