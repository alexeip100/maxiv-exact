# Application overview
MAX IV EXACT is a GUI tool for inspecting, processing, comparing, and decomposing **1D X-ray absorption spectra** stored in HDF5 files. It is developed around FlexPES/MAX IV data, with configurable channel profiles for other compatible HDF5 naming conventions.

You can use it to:
- browse HDF5 content safely (tree items are **lazy-loaded** as you expand them),
- quickly visualize groups of spectra corresponding to a specific detection mode (TEY/PEY/TFY/PFY), or groups of other recorded 1d data,
- apply common processing steps (optional **I₀ normalization**, **background subtraction**, and **post-normalization**),
- create **summed** spectra from multiple scans,
- prepare publication-style plots (with legend, annotation, grid, waterfall representation, curve style selection, etc),
- export/import curves as CSV, load reference spectra, and send curves to decomposition tools (PCA/NMF/MCR).

## Mental model (how parts of the GUI relate)
Think in three layers:

1) **Select** what you want to see (HDF5 Structure + Raw Data tab)  
2) **Process** selected spectra (Processed Data tab)  
3) **Present/export** selected curves (Plotted Data tab)

### First-time orientation
If this is your first session, you do not need to understand every control before starting. A normal path is:

1. **Open HDF5** and choose one file.
2. In **Raw Data**, select one detector family such as TEY, PEY, TFY, or PFY and inspect the spectra.
3. In **Processed Data**, first decide whether to normalize by **I₀**, then choose background subtraction and post-normalization only if they are needed for the comparison you want to make.
4. Use **Pass** when you are ready to collect processed curves in **Plotted Data** for comparison, styling, references, or multi-curve export.
5. Use **PCA** only after the spectra have been made comparable; the decomposition window has its own method-specific Help.

> A useful rule is to change one processing choice at a time and look at its effect. EXACT is designed to let you inspect the raw spectrum and processed result side by side rather than forcing a fixed recipe.

### Processing controls versus display controls
Some controls change the numerical curve sent onward; others only change how it is shown.

- **Changes the processed data:** I₀ normalization, background subtraction, post-normalization, summation, Group BG / Match pre-edge.
- **Mainly changes presentation:** legend style, curve order, line/marker style, annotation, grid, and waterfall offsets.
- **Waterfall is display-only**, which is why it must be OFF before transferring spectra to decomposition.

When in doubt, use **How to?** for a workflow explanation and **What is what?** for the meaning of an individual control.

## Key terms used in the UI
- **Curve**: one 1D dataset shown as a line.
- **Entry number**: IDs like `entry6567`. Used by the “Entry number” legend mode.
- **Region**: a grouping used in the Raw/Processed trees to organize curves on the photon E scale.
- **I₀**: a monitor channel used for normalization when enabled.

## Abbreviations used in the UI
- **TEY**: Total Electron Yield (usually sample drain current)
- **PEY**: Partial Electron Yield (electron current with a low-E cutoff, usually from a channeltron multiplier or a multichannel plate (MCP) detector)
- **TFY**: Total Fluorescence Yield (either a photodiode, or an MCP counting detector, or sum of all channels in an energy-dispersive detector)
- **PFY**: Partial Fluorescence Yield (photon-counting signal with energy filtering, typically a region of interest in an energy-dispersive detector)
- **I₀ (I0)**: the incident-beam monitor; in the app this usually means the **I₀ signal/curve** used for normalization.
- **BG**: background (baseline) model used for subtraction from the raw XAS spectra.
- **PCA**: Principal Component Analysis (variance-based decomposition of the multiple spectra arrays)
- **NMF**: Non-negative Matrix Factorization (non-negative components)
- **MCR-ALS**: Multivariate Curve Resolution – Alternating Least Squares (mixture model with constraints)

---

# Global controls
These buttons control file loading and global reset actions.

## **Open HDF5**
Opens one or more HDF5 files. Loaded files appear in the **HDF5 Structure** tree.

You can also drag and drop one or more `.h5`/`.hdf5` files directly onto the **HDF5 Structure** tree or onto any of the three main plotting areas (**Raw Data**, **Processed Data**, or **Plotted Data**). All drop targets use the same loader. Invalid files are skipped with a warning.

If a file with the same file name is already loaded, the program asks whether to refresh it from disk. Refreshing is non-destructive: existing processed/plotted work is kept where possible, and newly appended curves are added to the tree.

**Tip:** you can open multiple files at once; curves from all files can be selected and plotted together.

## **Close all**
Closes *all* opened files and clears all loaded data, trees, and plots. After the reset, EXACT returns to the **Raw Data** tab so the next session starts at the beginning of the normal workflow.

**Also available:** close a *single* file:
- In **HDF5 Structure**, right-click the top-level file item → **Close** (confirmation shown).

## **Clear all**
Resets the UI state without exiting the application. Typical effects:
- clears plotted curves (Plotted Data),
- clears current raw/processed selections and curves shown in plots,
- resets processing controls.

Opened files remain visible in the HDF5 tree, so you can reselect curves quickly. EXACT returns to the **Raw Data** tab after the reset.

## **Help**
Opens:
- **What is what?** (this document, describes all UI elements)
- **How to?** (describes typical workflows/recipes)
- **About**

## **Setup channels** and **Active beamline**
Opens the channel mapping dialog and shows which profile (beamline or branch line) is currently active.

**See also (How to):** *Fix wrong TEY/PEY selection (Setup channels)*

---

# Data loading and selection

## Setup channels (beamline profiles)
This dialog defines how the application recognizes roles such as **TEY / PEY / TFY / PFY**, **Energy**, and **I₀** based on dataset names/paths in the HDF5 file. It is used normally to define and use profiles specific for non-default beamlines (default is “FlexPES-A”)

### When to use it
- “All TEY data / All PEY data / …” selects the wrong curves (or nothing).
- The x-axis energy is not detected as expected.
- The default I₀ selection is not suitable for your files.

### Where mappings are stored
- A default mapping ships with the package: `docs/channel_mappings.json`
- Edits are saved to a per-user config file:
  `AppDataLocation/channel_mappings.json` (fallback: `~/.maxiv_exact/channel_mappings.json`)

### What it affects in the GUI
- Raw tab bulk selection:
  **All TEY data / All PEY data / All TFY data / All PFY data**
- Candidates shown in **Choose I₀**
- Energy lookup for plotting (x-axis)

### Practical guidance
- Treat the channel mapping as “how the software finds things” rather than “how the HDF5 is structured”.
- If your data uses different naming conventions, add the relevant substrings/candidates here.

---

## Settings (⚙)
The cog button next to **Open HDF5** opens the global appearance settings.

- **Theme:** System, Light, or Dark.
- **UI font size:** Default, +1 pt, or +2 pt. This changes Qt interface text, not Matplotlib plot/figure fonts.

The choices are stored and restored the next time EXACT starts. When the UI font is enlarged, control heights, spacing, tab geometry, and important tree/list minimum widths are adjusted with it so labels remain readable.

---

## HDF5 Structure (tree in left panel)
This tree is for browsing the file contents and selecting specific datasets.

### Lazy loading
Tree nodes are populated only when expanded. This keeps large files responsive.

### Browsing metadata
Clicking on 0d data (like metadata strings or scalars) shows their values in a field under the plot on the Raw Data tab.

### Checking items
Checking a 1d dataset (toggling specific check boxes) affects what is considered “visible” and can contribute curves to Raw/Processed plots.

### Closing a single file
Right-click a top-level file item → **Close** (with confirmation). Alternatively, select the HDF5 file to close and press “Delete”. 

---

# Data tabs and plot area
The right panel contains three main data tabs:
- **Raw Data**
- **Processed Data**
- **Plotted Data**

Each tab answers a different question:
- *Raw:* “What do I want to look at?”
- *Processed:* “How do I transform it (normalization/background/sum)?”
- *Plotted:* “How do I present/export it?”

All three tabs use the same basic plot/sidebar layout. The vertical divider is draggable, but the curve sidebar keeps a minimum width large enough for its controls. Beneath each curve list/tree, **Check all** and **Uncheck all** provide a fast way to show or hide every curve in that tab.

---

## Raw Data tab
Purpose: select and inspect raw curves.

### Channel family selectors
Checkboxes:
- **All TEY data**
- **All PEY data**
- **All TFY data**
- **All PFY data**

These toggle visibility of all datasets matching the role substrings from the **active beamline profile**.

**Tip:** If these select nothing or the wrong curves, use **Setup channels** to adjust mappings.

### “All in channel”
- **All in channel:** checkbox + dropdown

The dropdown lists unique channel names (last component of dataset paths).  
When enabled, changing the dropdown switches the active channel selection across entries.

**When to use:** you want something else (I₀, energy, an encoder value, etc) across many entries.

### Raw curve tree (right side)
The right-hand tree groups loaded raw curves by energy region. Use the individual or region checkboxes for selective visibility, or use **Check all / Uncheck all** below the tree to toggle the complete Raw selection in one action.

### Raw plot
- Matplotlib toolbar is shown above the raw plot (zoom, pan, save, etc).

### Raw info line (below the plot)
A small text line under the plot displays a scalar value or short information for the currently displayed/selected 0d dataset (typically when browsing through HDF5 file metadata).

**See also (How to):** *Inspect many curves quickly (Raw Data selection)*

---

## Processed Data tab
Purpose: process visible curves (I₀ normalization, background handling, post-normalization), optionally create summed curves, then export or pass results to Plotted Data.

### Top row controls

#### **Normalize by I₀?**
When checked, each curve is divided by the corresponding **I₀ signal/curve** from the same entry.

**When to use:** Usually when a suitable I₀ monitor is available: it compensates for variations in incident photon flux, including temporary intensity changes such as storage-ring injection events. Background subtraction is handled separately.  
**Tips:** If you choose an unsuitable I₀ signal (candidate), the result can be noisy or distorted.

#### **Choose I₀**
Dropdown enabled only when **Normalize by I₀?** is checked.

Candidates come from the channel mapping profile.

#### **Sum up?**
Opens the curve summation dialog to create new summed curves from selected curves. Mainly used when you have collected multiple scans from each sample for better statistics, and want to sum them up in groups corresponding to samples before proceeding with further treatment.

**See also (How to):** *Sum curves (“Sum up?” dialog)*


#### Summed groups: right-click menu (Processed Data tree)
When you create a summed curve using **Sum up?**, it appears as a *group curve* in the **Processed Data** tree.
Right-click the group name to access:
- **Group info**: shows which curves were used to build the group.
- **Rename**: changes the group name (and updates the label in **Plotted Data** if that curve is present there).
- **Delete**: removes the summed group after an OK/Cancel warning. (Curves already passed to **Plotted Data** are not removed automatically.)


#### **Group BG**
Enabled when you have two or more curves that you want to process *as a comparable group*.

**What it is for**  
Use **Group BG** when you want to compare a series of spectra (e.g. repeated scans, a time/temperature series, or multiple samples) and you don’t want the background handling and scaling to drift independently for each curve.

**What happens when you enable it**  
Group BG switches the app into a constrained group-processing mode and locks the relevant settings to keep the result comparable across the whole group:

- **Choose BG** is forced to **Auto**  
- **Subtract BG?** is forced **ON**  
- post **Normalize** is forced to **Area**

So the Processed Data plot shows a set of **background-subtracted, area-normalized** spectra processed in a consistent way.

**How the background is determined (conceptually)**  
Instead of fitting each curve completely independently, Group BG adjusts the automatic polynomial backgrounds with the goal that, across the group:

- the **post-subtraction scaling is comparable** (area-normalized output), and  
- the **pre-edge baseline behavior is consistent** enough to make curves directly comparable.

**When to use / when not to use**
- Use it for comparative plots and trend analysis across many similar spectra.
- Avoid it if each curve truly requires a different background model (very different baseline shapes or strong artefacts), because forcing consistency can hide genuine differences or introduce bias.

---

#### **Match pre-edge**
Enabled only when **Group BG** is active.

**What it does**  
Adds an extra group constraint that makes the **pre-edge region line up more consistently** across the selected curves (in practice: the pre-edge slope/offset after subtraction is aligned across the group).

**Why you might want it**  
Sometimes Auto polynomial backgrounds are “good enough” curve-by-curve, but the group comparison still looks messy in the pre-edge (small slope differences dominate the visual comparison). Match pre-edge is meant to reduce that distraction and make the group comparison clearer.

**Important caution**  
Match pre-edge can improve consistency, but it does so by allowing a more flexible adjustment of the background specifically to make the pre-edge align. Sanity-check that you are not introducing artificial structures or distorting real low-energy features. A good practice is to toggle it on/off and confirm that the edge-region features you care about remain stable.

**See also (How to):** *Compare multiple curves consistently (Group BG)*

#### **Pass**
Sends the current processed curve(s) to **Plotted Data** without clearing existing plotted curves.

**When to use:** you want to style/export from Plotted Data and keep multiple curves together.

#### **Export**
Exports processed data to CSV. Works for individual curves, not a group. Group CSV export is possible from the Plotted Data tab.

**See also (How to):** *Make a single clean processed curve* and *Sum curves (“Sum up?” dialog)*

### Processed curve tree (right side)
The right-hand tree controls which processed curves are visible. **Check all / Uncheck all** below the tree toggles the whole processed set. The button row is aligned with the bottom processing controls.

### Background and post-normalization controls (bottom row)

#### **Choose BG** — None / Auto / Manual
- **None**: no background model
- **Auto**: polynomial pre-edge background
- **Manual**: anchor-based adjustment (built on top of an automatic estimate)

#### **Poly degree**
Polynomial degree for Auto/Manual background.

#### **Pre-edge (%)**
Pre-edge region length (percent of energy span) used for baseline fitting.

#### **Subtract BG?**
Shows BG-subtracted curves when enabled.

#### **Normalize** — None / Max / Jump / Area
Post-normalization scaling (enabled/disabled depending on mode).


---

## Plotted Data tab
Purpose: figure-like plotting and exporting.

### Plotted curve list (tree on the right)
Here you can manage which curves are shown and how they look. Each row corresponds to one curve currently loaded into Plotted Data.

#### What you can do there

- Show / hide curves (visibility toggle per curve).
- Reorder curves by drag-and-drop (this affects plot order and legend order).
- Change appearance per curve:
-- color,
-- line style (solid / dashed / markers, depending on the control),
-- line width / marker size (depending on the control).
- Remove a curve from the plotted set (delete/remove control on the row).
- Add a curve to the reference library using the bookmark/add-to-library control (available on each curve row).

#### Selection behavior

Selecting an item in the list makes that curve the “active” curve for certain actions (e.g. operations that act on one curve at a time, like naming in user-defined legend mode).

**Tip:** If you want a consistent export order and legend order, set it here by reordering the curves before exporting.

Use **Check all / Uncheck all** below the list to show or hide the complete plotted set without changing the curve order.

### Top row controls

#### Legend
Dropdown: **Legend**
- **None**
- **User-defined**
- **Entry number**

Behavior:
- **User-defined**: rename labels by clicking legend entries.
- **Entry number**: labels by `entry#### → ####`.

**Tips:** If Legend is **None**, CSV export from Plotted Data is blocked (there is no naming scheme).

#### Annotation
Checkbox: **Annotation**
- shows/hides one annotation box,
- right-click to edit text/style,
- drag to reposition.

### Bottom row controls

#### Waterfall
Checkbox + slider/spinbox (enabled only when Waterfall is enabled).  
Applies a uniform vertical offset to separate many curves visually.

#### Grid
Dropdown: `None / Coarse / Fine / Finest`

#### Load reference
Button: **Load reference**
Opens the reference library dialog where you can load references into the plot.
The same dialog contains **Delete reference** (removes from the library).

#### Export/Import
Button opens a menu:
- **Export CSV**
- **Import CSV**

Export naming depends on Legend mode:
- **Entry number** → headers are entry numbers (requires entry ids)
- **User-defined** → headers are custom names; placeholder `<select curve name>` is not allowed
- **None** → export is blocked

**See also (How to):** *Export plotted curves to CSV (Export/Import → Export CSV)*

#### PCA (decomposition window)
Button: **PCA**

This opens the **decomposition window** and (optionally) sends curves from Plotted Data to it. Although the button is labelled **PCA**, the window contains the broader PCA/NMF/MCR-ALS and anchor-based decomposition workflow.

##### Role in the workflow
Use these tools when you have a series of comparable spectra and want to examine dominant variations, estimate the number of significant components, or model the series using non-negative or constrained components. Detailed guidance on PCA, NMF, MCR-ALS, anchors, constraints, diagnostics, and interpretation is available from **Help inside the decomposition window**.

##### What happens when you click PCA
- If eligible curves are available in Plotted Data, they are transferred to the decomposition window.
- If no visible curves are selected/eligible, the window can still open (useful if you plan to load data from within that window).

##### Requirements enforced by the app (transfer from Plotted Data)
The transfer is blocked unless:
- **Waterfall** is OFF (waterfall changes y-values and is for visualization only),
- post **Normalize** is **Area** for all selected curves (ensures comparability),
- **Legend** is not **None** and curve names are resolvable (needed to label spectra in the decomposition window).

**See also (How to):** *Send curves to PCA / decomposition window*

#### Clear Plotted
Removes all curves from Plotted Data without changing Raw/Processed selections.



# X-ray Reference

The separate **Reference** tab at the far right provides built-in atomic X-ray reference data. It is independent of the user-maintained **Reference Spectra Library** used for measured spectra in Plotted Data.

## Main controls

- **Element:** choose an element from the periodic-table selector.
- **Compound(s):** type one chemical formula, or several formulas separated by commas (for example `CoO, Co2O3, Co3O4`), and press **Enter**. Valid formulas switch the Reference tab to compound mode and are plotted together. Up to eight compounds can be compared at once.
- **Source:** choose **Henke / CXRO**, **Chantler / XrayDB**, or **Henke + Chantler** when both sources contain the selected quantity.
- **Quantity:** choose `f₁`, `f₂`, one of the Chantler mass-attenuation coefficients, or **μ compare**. **μ compare** overlays `μ photo`, `μ incoh` and `μ total` for one Chantler element or one compound. Hover over the current Source or Quantity entry for a short definition.
- **Photon energy:** sets the dashed vertical cursor. The cursor can also be dragged directly on the plot. Circular markers show the intersections with the visible reference curves, and the value table below the plot updates continuously.
- **Full source range:** normally the plot opens in the soft-X-ray region up to 2500 eV. Enable this to expose the full tabulated source range.
- **Legend:** show or hide the legend. In comparison mode the legend is draggable.

## Reference quantities

- **Photon energy, E (eV):** X-ray photon energy on the horizontal axis. The frozen database preserves the full original source ranges; 2500 eV is only the default soft-X-ray display limit.
- **f₁ (electrons):** full real atomic scattering factor. **Henke/CXRO** tabulates full `f₁` directly. **Chantler/XrayDB** stores the anomalous real correction `f′`, so EXACT displays `f₁ = Z + f′` for direct comparison with Henke. The original Chantler `f′` remains unchanged in the frozen database.
- **f₂ (electrons):** imaginary, absorptive part of the complex atomic scattering factor. It is closely related to X-ray absorption and changes strongly at absorption edges. Available from both **Henke/CXRO** and **Chantler/XrayDB**.
- **μ photo (cm²/g):** photoelectric mass attenuation coefficient: attenuation caused by photoabsorption per unit mass density. Available from **Chantler/XrayDB**.
- **μ incoh (cm²/g):** incoherent-scattering contribution to the mass attenuation coefficient. Available from **Chantler/XrayDB**.
- **μ total (cm²/g):** total mass attenuation coefficient tabulated in the Chantler/XrayDB dataset. Available from **Chantler/XrayDB**.
- **μ compare:** overlays `μ photo`, `μ incoh` and `μ total` for the same element or a single compound, using one log-scale axis and one photon-energy cursor. It is intentionally disabled when several compounds are active, to avoid an ambiguous 3 × N curve plot.

## How total attenuation is composed

For the Chantler attenuation data used by EXACT, the total attenuation coefficient is the sum of photoelectric absorption, coherent (Rayleigh) scattering and incoherent (Compton) scattering:

$$\mu_{\mathrm{total}} = \mu_{\mathrm{photo}} + \mu_{\mathrm{coh}} + \mu_{\mathrm{incoh}}$$

The same decomposition applies to the **mass attenuation coefficients** shown in EXACT after division by density:

$$\left(\frac{\mu}{\rho}\right)_{\mathrm{total}} = \left(\frac{\mu}{\rho}\right)_{\mathrm{photo}} + \left(\frac{\mu}{\rho}\right)_{\mathrm{coh}} + \left(\frac{\mu}{\rho}\right)_{\mathrm{incoh}}$$

Here `μ coh` denotes coherent (**Rayleigh**) scattering and `μ incoh` denotes incoherent (**Compton**) scattering. This equation describes the **physical decomposition** of the total attenuation coefficient. The frozen XrayDB/Chantler tables bundled with EXACT, however, provide only three attenuation channels as independent arrays: `μ photo`, `μ incoh` and `μ total`. A separate `μ coh` channel is **not present in the downloaded Chantler table used by EXACT**, so it cannot be selected or plotted directly in the Reference tab. Its contribution is contained implicitly in `μ total` and can only be inferred as `μ total − μ photo − μ incoh`.

In the soft-X-ray range for which EXACT is primarily intended, coherent (Rayleigh) scattering is generally a very small contribution compared with photoelectric absorption, and is often also small compared with the incoherent (Compton) contribution. This is why the available `μ total` curve can lie almost exactly on top of `μ photo + μ incoh`. The **μ compare** mode therefore shows the three quantities that are actually tabulated in the bundled database; it should not be read as a plot of every physical attenuation channel separately.


## Chemical composition and compound mass attenuation

Compound mode currently calculates **only Chantler/XrayDB mass attenuation coefficients**. Henke/CXRO and compound `f₁`/`f₂` are intentionally not used for this calculation.

The formula parser accepts element symbols, positive stoichiometric numbers and nested parentheses. Examples include `Co2O3`, `LiFePO4`, `Al2(SO4)3` and fractional stoichiometry such as `La0.7Sr0.3MnO3`. To compare several materials, enter comma-separated formulas, for example `CoO, Co2O3, Co3O4`; EXACT plots one Chantler mass-attenuation curve for each formula, using the same selected quantity and photon-energy cursor. Up to eight compounds can be shown together. Duplicate formula entries are removed. Weight-percent mixtures, unknown `x` concentrations, ionic charges and hydrate-dot notation are not yet supported. The parsing scope follows the chemical-formula approach used in **XAFSmass / ParSeq-XAS**, but EXACT implements only this narrower stoichiometric subset locally.

From the formula, EXACT calculates each element's **mass fraction** `wᵢ` using the elemental molar masses in the bundled reference database. The compound mass attenuation coefficient is then constructed with the standard mixture rule:

$$\left(\frac{\mu}{\rho}\right)_{\mathrm{compound}} = \sum_i w_i \left(\frac{\mu}{\rho}\right)_i$$

This calculation is available for:

- **μ photo / ρ:** photoelectric mass attenuation coefficient.
- **μ incoh / ρ:** incoherent (**Compton**) scattering contribution to the mass attenuation coefficient.
- **μ total / ρ:** total Chantler/XrayDB mass attenuation coefficient.

All are displayed in **cm²/g**. **Density is not required** for the displayed mass attenuation coefficient. Density would only be needed later to convert mass attenuation to the linear attenuation coefficient or to an attenuation length:

$$\mu = \rho\left(\frac{\mu}{\rho}\right), \qquad \lambda = \frac{1}{\mu}$$

Each compound curve is built from the elemental Chantler tabulations over their common energy range. The existing Photon energy cursor works for all compound curves together, and the live-value table reports one value per compound. For a single compound, the parsed molar mass and elemental mass fractions are shown below the formula field; for several compounds, the active formulas are summarized there and the detailed composition information is available in the tooltip.

## Source conventions

**Henke / CXRO** and **Chantler / XrayDB** remain separate source datasets. **Henke + Chantler** overlays the two independent curves; EXACT does not average or merge them. For `f₁`, the overlay compares Henke's tabulated full `f₁` with `Z + f′` derived from Chantler/XrayDB. The bundled database is local and frozen, so normal use of the Reference tab does not require internet access.
