## Overview
This app helps you **inspect, process, and export NEXAFS spectra** stored in HDF5 files (FlexPES / MAX IV style data).

**Typical workflow (most users):**
1. **Open HDF5** file(s).
2. In **Raw Data**, quickly select curves (e.g. *all TEY* for an edge).
3. In **Processed Data**, apply **I₀ normalization** and **background subtraction** (and optionally **sum** curves).
4. **Pass to Plotted** for figure-like viewing, styling, reference spectra, and export.

## File Controls (Top Left Panel)
Use these buttons when you want to **load data, reset the session, or adjust how channels are interpreted**.

- **Open HDF5:** Load one or more HDF5 files containing NEXAFS data.
- **Close all:** Remove all currently opened files (tree + plots).
- **Clear all:** Reset the interface (Raw/Processed/Plotted). Useful if you want a clean start but keep the app open.
- **Help:** Open the **Usage** and **About** dialogs.
- **Setup channels / Active beamline:** Use this if curves do not show up under the expected detector family (TEY/PEY/TFY/PFY),
  if the **energy axis** is not detected correctly, or if the default **I₀** channel is not what you expect.

## File Tree Panel
Shows the hierarchical structure of loaded HDF5 files.

**Use this panel when you want fine-grained control**: pick specific entries, channels, or scans.
- Expand groups to find 1‑D datasets (curves), then tick their checkboxes to show/hide them.
- Tip: if you mainly work by detector family (TEY/PEY/TFY/PFY), the **Raw Data tab** has faster “select many” tools.

## Setup channels (beamline profiles)
The app uses a **beamline profile** to translate the canonical roles (TEY, PEY, TFY, PFY, I₀, Energy) into the dataset names
that exist in your HDF5 files.

**When to open this dialog**
- The **All TEY/PEY/TFY/PFY** checkboxes select the wrong curves (or nothing).
- The **energy axis** looks wrong (or the x‑axis falls back to an index).
- You want to change which dataset is considered the default **I₀** monitor.

**What “Active beamline” affects**
- The Raw Data tab’s **All TEY/PEY/TFY/PFY** convenience selection (it uses the configured channel substrings), and
- the default **I₀** choice for normalization and the **Energy** dataset lookup.

**Profiles and saving**
- Profiles live in `channel_mappings.json`. You can keep multiple profiles, switch between them, and edit them in the app.
- In the Setup dialog:
  - **Use selected** activates a profile and closes the dialog (no saving needed).
  - **Save changes** writes the table values into the currently shown profile name (with an overwrite warning).
- **I₀** and **Energy** fields accept a comma-separated list of candidate dataset names/paths; the **first** candidate is the preferred default.

## Tabs (Right Panel):
The right panel contains three main tabs: **Raw Data**, **Processed Data**, and **Plotted Data**. Most workflows go left → right.

## Raw Data Tab
**Purpose:** choose which datasets (curves) are visible.

**Common tasks:**
- Show *all TEY/PEY/TFY/PFY* curves for one edge across many entries.
- Load the *same channel* across all entries ("All in channel") to compare scans consistently.
- Quickly toggle whole edge regions on/off using the region checkboxes in the Raw tree.


- **Data Plot:** Shows raw spectra. Multiple curves can be shown at once.

- **Channel Families:**  
  Quick toggles by detector type:
  - **All TEY data**
  - **All PEY data**
  - **All TFY data**
  - **All PFY data**

  Each checkbox shows or hides *all* 1-D datasets whose HDF5 path contains
  the corresponding channel substring (e.g. `_ch1`, `_ch3`, etc.), across
  all opened files. You can combine these with the tree item checkboxes
  and with **All in channel** (see below).

- **All in channel:** *(checkbox + combobox of channel names)*  
  The combobox lists unique channel names found across all opened files
  (based on the **last path component** of each 1-D dataset).  
  - **Checked:**  
    Load the selected channel across **all entries**. If another channel
    was previously active, it is cleared first. Changing the selection
    while checked switches to the new channel and removes the previous one.
  - **Unchecked:**  
    Clear that channel group from the plot (and from the Raw Data tree’s
    visibility map). Changing the combobox while unchecked does not load
    anything.

- **Raw Data Tree (right of plot):**  
  A dedicated tree for raw data inspection. Datasets are grouped into
  energy-dependent “regions” (e.g. absorption edges). Regions are grouped by energy range (edge). Interrupted/unfinished scans are collapsed to avoid clutter. Checkboxes on group
  nodes allow quick selection or deselection of an entire edge, while
  individual items allow fine-grained control of which curves are visible.

- **Scalar Display (Raw):**  
  A small text area beneath the raw plot canvas that shows scalar or
  textual metadata for the currently selected item(s) (for example,
  experimental parameters or scan comments).

---

## Processed Data Tab
**Purpose:** apply non-destructive processing to the visible raw curves.

**Common tasks:**
- Normalize spectra by **I₀** before comparing scans.
- Subtract a background and apply a consistent post-normalization for comparison.
- Sum repeated scans into one curve ("Sum up").
- Use **Group BG** when processing multiple spectra that must be treated consistently.


### Top Controls (normalization, summing, export)

- **Normalize by I₀?** *(checkbox + “Choose I₀” combobox)*  
  When checked, each raw spectrum is divided by the chosen I₀ / monitor
  channel from the same entry. This corrects for intensity fluctuations
  between scans before any background subtraction or post-normalization.

- **Choose I₀:**  
  Choose which dataset within the entry should be used as I₀. Only used
  when **Normalize by I₀?** is checked.

- **Sum up?** *(button)*  
  Opens the **Curve summation** dialog, where you can combine spectra into one or more *summed curves*.

  **Workflow:** drag curves into groups, rename groups if desired, then press **OK**.

**Result:**
  - Each group produces a new curve with the group name (e.g. “sample1”). Single-curve groups keep the group name.
  - The summed curves appear in the **same Region** as their constituents.
  - Constituents are unchecked by default; the new summed curves are checked.
  - Summed curves behave like normal curves for BG subtraction, normalization, passing to Plotted, and export.

  **Energy alignment:** If curves have slightly different energy grids, the app aligns them automatically using common overlap and interpolation.


- **Group BG:** *(checkbox)*
  Becomes **checkable** as soon as **two or more** spectra are selected (it is **not** enabled by default — the user must
  actively check it).

  When **Group BG** is checked, the app switches to *group background* mode to process multiple spectra consistently (background + post-normalization settings are enforced for comparability). You can still toggle **Subtract BG** to visually inspect the suggested background:
      - **Subtract BG ON:** show background-subtracted (Area-normalized) spectra.
      - **Subtract BG OFF:** show the **unsubtracted** spectra with their **individual fitted backgrounds**.

  If you uncheck **Group BG**, your previous single-spectrum BG / normalization settings are restored. If the current
  selection drops below two spectra, **Group BG** is automatically turned off and disabled.

  **Passing to Plotted Data:** When Group BG is active, the **Pass** operation carries over the enforced **Area**
  normalization and group-consistent background adjustment, so the curves in **Plotted Data** match what you see in the
  **Processed Data** panel.

  **Background model used in Group BG (Auto BG):**

  - Each spectrum starts from its *own* **Auto BG** (a low-degree polynomial fitted to the pre-edge, with the same
    end-slope constraint as in single-spectrum mode).
  - The background is then adjusted per spectrum by adding a small **affine term** *(constant + global linear term)* so that
    (i) the **pre-edge baseline after subtraction is 0**, and (ii) the **absorption jump after Area normalization** is
    consistent across the selected spectra.

- **Match pre-edge:** *(checkbox)*
  Available only when **Group BG** is active. When enabled, the group mode additionally adjusts the
  backgrounds so that the **pre-edge slope after BG subtraction** is consistent across the selected spectra
  (median target).

  **Important:** With **Match pre-edge** enabled, the final background is **no longer a single pure polynomial**.
  Internally, the polynomial background is supplemented by a *localized pre-edge correction term* that is active in the
  pre-edge region and smoothly tapers to zero before the edge (so it does not distort the post-edge window). This extra
  degree of freedom makes it possible to align pre-edge slopes across a group while keeping the Area-normalized jump
  consistent.

- **Pass:**  
  Send the current processed main curve (possibly normalized, summed and
  background-subtracted) to the **Plotted Data** tab.  
  The curve is added to the Plotted list without clearing existing curves.

- **Export:**  
  Export the current **Processed Data** main curve to a CSV file.
  (This button is separate from the **Export/Import** menu in the *Plotted Data* tab.)

### Bottom Controls (BG + post-normalization)

- **Choose BG:** *(controls: None / Auto / Manual)*  
  - **None:** no background is fitted or subtracted.
  - **Auto:** polynomial background fit with an additional constraint
    so that the derivative at the end of the background matches the slope
    of the data (intended to mimic a smooth pre-edge baseline).
  - **Manual:** manual background mode. The application starts from an
    automatic estimate, and you can adjust anchor points with the mouse
    if the automatic fit fails or needs refinement.

- **Poly degree:**  
  Polynomial degree for the background fit (typically 0–3).


- **Pre-edge (%):**  
  Fraction of the spectrum (in %) treated as “pre-edge” region for
  background estimation.

- **Subtract BG?**  
  When checked, the plotted curve on the Processed Data tab is shown as
  **(signal − background)**. This also enables *post-normalization*.

- **Normalize (post-processing):** *(None / Max / Jump / Area)*  
  This is a **post-normalization** applied after background subtraction
  (if enabled). Modes:
  - **None:** no further scaling.
  - **Max:** scale to the maximum value of the (subtracted) curve.
  - **Jump:** scale to the absorption jump at the last point of the curve.
  - **Area:** scale to the integrated area under the curve.

> **Note:** Background subtraction and post-normalization are only
> available when there is a single effective main curve (one dataset visible, or multiple datasets combined via **Sum them up?**).
> 
> If several raw curves are visible and summing is disabled, BG/post-normalization are normally disabled — **except** when
> BG mode is **Auto** and **Group BG** is enabled.
> 
> In that group mode, when **Subtract BG?** is **OFF**, BG curves are shown for all selected curves.
> When **Subtract BG?** is **ON**, the view switches to the BG-subtracted curves, and the **Pass** button can pass
> **all selected curves** to the Plotted Data tab at once.

---

## Plotted Data Tab
**Purpose:** control plot appearance, curve styles, reference spectra, and export.

**Common tasks:**
- Make a clean, readable figure (styles, legend, annotation).
- Compare many curves using **Waterfall** and drag‑reordering.
- Save curves to the **reference library** and export plots/data.


### Plot and axes

- **Interactive Plot Canvas:**  
  Embedded Matplotlib canvas with zoom, pan, and save tools (via the
  toolbar). Energy (x-axis) is auto-detected from typical energy arrays (with a fallback to an index axis if none are found). Curve labels initially include
  information like *entry + channel* (or “Summed Curve”).

### Waterfall controls

- **Waterfall:** *(checkbox)*  
  - **Unchecked:** all curves are plotted on top of each other (no vertical shift).  
  - **Checked:** applies a **Uniform step** vertical offset to the visible curves in the plotted list order.
- **Step (slider + spinbox):** controls the size of the vertical offset. The value is a fraction of the global y-range of the
  currently visible curves; larger values increase separation.

### Curve List (right side)

Side panel that lists all curves currently in the **Plotted Data** tab.

For each curve you can:

- **Show/hide:** toggle visibility without removing the curve.
- **Change color:** open a color picker to change the line color.
- **Change style:** choose between **Solid**, **Dashed**, and **Scatter**
  (marker mode).
- **Change thickness / marker size:** controlled by the style row’s size
  field.
- **Remove curve:** click the small **×** (cross) to remove the curve
  from the Plotted list and the Plotted axes.
- **Add to reference library:** click the **bookmark** button to add the
  curve to the reference spectra library (`library.h5`) together with
  metadata (element, edge, compound, resolution, comments, etc.).

The curve list is fully interactive:

- **Drag-and-drop reordering:**  
  Drag curves up or down with the mouse. When you release, the plot and
  legend are updated to follow the new order (particularly visible in
  the Waterfall representation).

### Legend

Legend behavior is controlled via the **Legend:** drop-down on the Plotted Data panel:

- **User-defined (default):** shows the legend and lets you set custom curve names.
  - In the legend, entries initially appear as `<select curve name>`.
  - **Left-click** a legend label to rename that curve (only in User-defined mode).
- **Entry number:** shows the legend and automatically labels curves by their entry ID.
  - For example, `entry6567` becomes `6567` in the legend.
- **None:** removes the legend from the plot.

**Drag:** You can reposition the legend by dragging it inside the axes.

**Right-click to edit style:** Right-click the legend (text or frame) to edit its appearance:
- transparency
- margins/padding
- font size
- font style (bold/italic/underline)

> Tip: when the mouse is inside the legend box, a small tooltip reminds you: “Right click to edit”.


### Annotation

- **Annotation checkbox:** show/hide a single annotation text on the Plotted Data plot.
- When visible:
  - **Drag with left mouse button** to reposition it.
  - **Right-click** to edit the annotation text and style.

The annotation editor supports:
- font size
- font style (bold/italic/underline)
- font color
- background color or no background
- border on/off (and border thickness/color)
- padding (margin between text and frame)
- inserting common symbols (e.g. °, ±, µ, Å, α, β, Δ, ≤, ≥)

> Tip: when the mouse is inside the annotation box, a tooltip reminds you: “Right click to edit”.


### Grid

- **Grid:** *(controls: None / Coarse / Fine / Finest)*  
  Applies major and minor grid lines to the Plotted Data axes:
  - **None:** no grid.
  - **Coarse:** major grid only (similar to the original single checkbox).
  - **Fine / Finest:** enable minor grid with successively denser spacing.
    Minor grid lines are drawn less prominently than major ones.

## X-ray Reference tab

The built-in **Reference** tab is documented in the current in-application Help:

- **Help → What is what? → X-ray Reference** describes the controls, Henke/CXRO and Chantler/XrayDB quantities, attenuation decomposition, chemical formulas, compound mass attenuation, and source conventions.
- **Help → How to? → Inspect built-in X-ray reference data** gives the practical plotting workflow, including multi-compound comparison.

This legacy document is retained for older documentation references; the two Help pages above are the maintained source of truth for the current interface.

### Reference Spectra Library

The app ships with a small reference library file `library.h5`. You can add your own reference spectra and load them
together with measured curves in the **Plotted Data** tab.

- **Add to reference library:** click the **bookmark** button in the Plotted curve list to save a curve into `library.h5`
  together with metadata (element, edge, compound, resolution, comments, etc.).
- **Load reference:** opens a dialog listing spectra stored in `library.h5`.
  - Select one or more references and click **OK** to load them into the Plotted Data plot.
  - **Delete reference:** deletes the selected reference from `library.h5` after a confirmation prompt (**permanent**).

> Tip: If you want a fully custom curated library, keep a backup copy of `library.h5` and/or version it with Git.

### Export / Import
 
Opens a menu:

- **Export CSV:** export the curves currently shown in the Plotted Data tab as CSV.
    - Column headers are derived from the **Legend** mode in Plotted Data:
      - **Entry number** → headers are the entry numbers.
      - **User-defined** → headers are the user-assigned curve names.
    - The placeholder `<select curve name>` is **never** allowed in exported CSV headers.
    - If required names are missing (e.g. user-defined names not set, or no entry numbers available), the export is blocked and a warning is shown.
- **Import CSV:** load one or several previously exported CSV files into the Plotted Data plot.

### PCA (Principal Component Analysis) 
  
PCA and related multivariate decomposition methods are used to identify the dominant sources of variation in a set of spectra, without assuming a specific physical model.
In XAS, these methods are useful for analyzing systematic spectral changes arising from variations in measurement geometry, temperature, pressure, or chemical state, such as metal oxidation-state (valence) evolution.
While PCA components are not necessarily physical spectra by themselves, they provide a powerful starting point for understanding spectral trends and for guiding more chemically constrained methods such as NMF or MCR-ALS.
 
The PCA button opens the **spectral decomposition** window (PCA / NMF / MCR-ALS / Anchors) and transfer the currently shown Plotted curves to this window.
The transfer uses the same curve selection and naming rules as **Export CSV** (visible/checked curves, legend-based names).

For a scientifically meaningful decomposition, the button is blocked unless:

- **Waterfall** is **unchecked** (no offsets applied), and
- all selected curves have **post-normalization = Area** (i.e. background-subtracted, Area-normalized curves).

A short explanation of methods PCA, NMF, MCR-ALS, as well as the usage of anchor spectra is available under the specific **Help** buttons on the decomposition app panels.

### Clear Plotted
  
Remove all curves from the Plotted Data tab (but keep raw and processed data untouched).
