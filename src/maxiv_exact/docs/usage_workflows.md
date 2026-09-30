# Load and inspect data

## Quickstart
You’ve just opened EXACT and want to get from “a file on disk” to “a curve I can trust”.

Start simple:

1) Click **Open HDF5** and select your file(s). The file(s) appear in the **HDF5 Structure** tree.  
2) Go to **Raw Data** and make your first broad choice: *which kind of signal do I want to look at?*  
   - If you’re after an electron-yield view, try **All TEY data** or **All PEY data**.  
   - If you’re working with fluorescence, try **All TFY data** or **All PFY data**.  
   - If you already know the exact channel name you need across many entries, enable **All in channel** and pick it in the dropdown.  
3) Switch to **Processed Data** and decide what “clean” means for your case:
   - Do you need normalization by the incident-beam monitor (**Normalize by I₀?** + **Choose I₀**)?
   - Do you need a baseline/background correction (**Choose BG**, **Pre-edge (%)**, **Poly degree**)?
   - Do you want to *see* the BG‑subtracted result (**Subtract BG?**)?
   - Do you want a defined scaling for comparisons (**Normalize**, often **Area**)?
4) When the processed curve looks right, either:
   - click **Export** (best when you are exporting one curve), or
   - click **Pass** to move curves into **Plotted Data**, where you can style, reorder, annotate, and export multiple curves together.

**Controls used (What is what?):** *Raw Data tab*, *Processed Data tab*, *Export*, *Pass*

### Abbreviations used below (quick reference)
- **TEY**: Total Electron Yield
- **PEY**: Partial Electron Yield
- **TFY**: Total Fluorescence Yield
- **PFY**: Partial Fluorescence Yield
- **I₀ (I0)**: incident-beam monitor; in practice you select the **I₀ signal/curve** to normalize your spectra
- **BG**: background (baseline) model/subtraction
- **PCA**: Principal Component Analysis
- **NMF**: Non-negative Matrix Factorization
- **MCR-ALS**: Multivariate Curve Resolution – Alternating Least Squares

## Load an HDF5 file and orient yourself
1. Click **Open HDF5** or drag an `.h5` / `.hdf5` file onto the **HDF5 Structure** tree or any main plotting area.
2. Expand the file only as far as you need. The tree is lazy-loaded, so opening a large file does not require expanding every group.
3. Start in **Raw Data**. For a standard measurement, try one detector-family selector (TEY/PEY/TFY/PFY) before manually checking individual datasets.
4. If you want to inspect a scalar or text metadata item, click it in the HDF5 tree; its value is shown below the Raw plot when supported.
5. If a detector-family selector picks the wrong channel, do not compensate manually for every scan—fix the **Setup channels** profile first.

You can open several files together and compare curves across them. Use the file-level right-click **Close** action when you want to remove only one file without clearing the whole session.

**Controls used (What is what?):** *Open HDF5*, *HDF5 Structure*, *Raw Data*, *Setup channels*

## Adjust the interface for your screen
Use the **⚙ Settings** button when you want a different application theme or larger interface text. Theme and UI font size are remembered between sessions. Enlarging the UI font also enlarges the relevant control geometry; Matplotlib plot fonts are unchanged.

If you want to restart the workflow, **Clear all** keeps the opened HDF5 files but resets the working state, while **Close all** also closes the files. Both return you to **Raw Data**.

**Controls used (What is what?):** *Settings (⚙)*, *Clear all*, *Close all*

---

## Fix wrong TEY/PEY selection (Setup channels)
If **All TEY data** (or another detector-family selector) selects nothing or clearly selects the wrong signal, the file’s channel naming may not match the current channel profile.


**How to fix it:**
1) Click **Setup channels**. Think of this dialog as the app’s “dictionary” for your file naming conventions.  
2) Pick the profile that is closest to your data (for example, a FlexPES profile).  
3) If needed, adjust the substrings/candidates so that the app can correctly recognize TEY/PEY/TFY/PFY and suitable I₀ candidates.  
4) Save/apply, confirm the label **Active beamline:** shows what you expect, then go back and try **All TEY data** again.

If the selector now lights up the right curves, you’re done.

**Controls used (What is what?):** *Setup channels (beamline profiles)*, *Channel family selectors*

---

## Inspect many curves quickly (Raw Data selection)
For datasets with many entries—such as repeated scans, a temperature series, or a map—the Raw Data tab lets you select related curves without checking each dataset individually in the HDF5 tree.

### Option A: “show me all curves of a detector family”
If you want the “standard” signals:
- Click **All TEY data** (or PEY/TFY/PFY).

You’ll immediately see the family of curves, which makes it easy to spot outliers, drift, bad scans, or obvious trends before you process anything.

### Option B: “follow one channel across many entries”
If you know you always want the same channel name:
- Enable **All in channel**, then choose the channel in the dropdown.

This is great for non-standard channels, monitor signals, or anything that isn’t reliably captured by the TEY/PEY/TFY/PFY grouping.

For a quick global visibility change, use **Check all / Uncheck all** below the right-hand curve tree. The same pair is available in Processed Data and Plotted Data.

**If nothing sensible shows up:** go back to **Setup channels** and fix the mapping first.

**Controls used (What is what?):** *Raw Data tab*, *Channel family selectors*, *All in channel*

---

# Process spectra

## Understand the processing order
The controls in **Processed Data** are easier to use if you think of them in their numerical order:

1. Start from the selected raw detector signal.
2. Optionally divide by **I₀**.
3. Optionally create a summed curve from repeated scans.
4. Estimate a background (**None / Auto / Manual**).
5. Optionally subtract that background.
6. Optionally apply post-normalization (**Max / Jump / Area**).
7. Export one result directly or **Pass** comparable curves to **Plotted Data**.

There is no requirement to enable every step. For example, a quick quality check may need no background treatment at all, whereas a multi-spectrum comparison may benefit from background subtraction and a common normalization.

## Choose I₀ normalization sensibly
I₀ normalization is useful when the monitor really represents variations in incident photon flux for the spectrum being analyzed.

1. Enable **Normalize by I₀?**.
2. Inspect the candidates in **Choose I₀** and select the monitor appropriate for your beamline/profile.
3. Compare the result with normalization off. The expected effect is usually removal of incident-flux variation, not creation of new spectral structure.
4. If the normalized spectrum becomes unexpectedly noisy, strongly distorted, or discontinuous, check the chosen I₀ channel and the channel profile before changing background parameters.

I₀ normalization and post-normalization are different operations: **I₀** corrects the spectrum using a measured incident-beam signal, while **Max / Jump / Area** rescales the already processed spectrum for comparison.

**Controls used (What is what?):** *Normalize by I₀?*, *Choose I₀*, *Setup channels*, *Normalize*

---

## Make a single clean processed curve
This workflow is for the common situation: you’re not trying to compare 50 curves yet—you just want *one* spectrum that is corrected, readable, and exportable.

1) In **Processed Data**, decide whether you need incident-beam normalization.  
   If yes: enable **Normalize by I₀?** and pick the correct **I₀ signal/curve** in **Choose I₀**.  
2) Choose how to deal with baseline/background:
   - **Auto** is the normal starting point.
   - Adjust **Pre-edge (%)** and **Poly degree** if the baseline fit is clearly wrong.
   - Use **Manual** only if you really need anchor-style correction.  
3) Decide what you want to look at:
   - Enable **Subtract BG?** if you want the BG-subtracted spectrum.
   - Disable it if you want to keep the baseline in the displayed curve.  
4) If your next step is comparison (or PCA later), choose a stable scaling via post **Normalize** (often **Area**).  
5) When the curve looks right:
   - **Export** if you’re exporting one curve, or
   - **Pass** if you want to assemble a figure or export multiple curves from Plotted Data.

**A practical note:** Processed‑tab **Export** is intentionally strict—if multiple curves are visible, export from **Plotted Data** instead, or create a summed curve first.

**Controls used (What is what?):** *Processed Data tab*, *Choose BG*, *Subtract BG?*, *Normalize*, *Export*, *Pass*

---

## Sum curves (“Sum up?” dialog)
Summation is what you reach for when you have repeats: several scans that are “the same measurement”, just noisy or slightly shifted, and you want one cleaner curve.

When you click **Sum up?**, you’re essentially telling the app: *“Treat these curves as one group and give me a single representative curve.”*

**How it works in practice:**
1) In **Processed Data**, make sure the curves you want are visible.  
2) Click **Sum up?** and build one or more groups (each group becomes one summed curve).  
3) Name each group—those names become the new curve names.  
4) Confirm.

Behind the scenes, the app uses the overlapping energy range, interpolates onto a common grid, and then sums. If **Normalize by I₀?** is enabled, that normalization happens before the summation.

If you don’t get a summed curve, it usually means the curves don’t overlap in energy enough to build a shared grid.

**Controls used (What is what?):** *Sum up?*, *Normalize by I₀?*, *Export*

After summation, you can manage the new group directly in the **Processed Data** tree: right-click the group name for **Group info**, **Rename**, or **Delete**.

---

## Compare multiple curves consistently (Group BG)
Once you move from “one nice curve” to “a set of curves I want to compare”, the risk changes: tiny differences in baseline handling can dominate your interpretation.

That’s what **Group BG** is for: it puts the app into a consistent group mode so the set behaves like a set.

**A good mental model:** “I want these curves to be processed the same way, so I can focus on real spectral differences.”

1) In **Processed Data**, make two or more curves visible—the ones you want to compare.  
2) Enable **Group BG**. The app locks into a consistent mode:
   - **Choose BG = Auto**
   - **Subtract BG? = ON**
   - **Normalize = Area**  
3) If the pre-edge region still looks uneven and distracts from the comparison, enable **Match pre-edge** to align pre-edge baseline/slope more consistently.  
4) Click **Pass** to move the group into **Plotted Data** for styling, ordering, annotation, and export.

**Controls used (What is what?):** *Group BG mode*, *Match pre-edge*, *Pass*

---

# Compose, compare, and export

## Prepare a publication-style plot (Plotted Data)
Processed Data is where you *compute*; Plotted Data is where you *compose*.

In Plotted Data you can treat curves like figure elements:
- choose naming via **Legend**,
- reorder curves for a sensible narrative,
- add annotation,
- choose grid and waterfall display,
- export the final dataset as CSV.

A typical “figure-making” rhythm:
1) Send curves in using **Pass** (from Processed Data).  
2) Pick a **Legend** mode:
   - **User-defined** if you want meaningful labels (“Sample A”, “Annealed 450°C”…),
   - **Entry number** if you want raw bookkeeping labels.  
3) Use the plotted curve list (tree on the right) to show/hide and reorder curves—this also controls legend order.  
4) Add **Annotation** when you want the figure to explain itself.  
5) Add a **Grid** if it helps reading values; use **Waterfall** when curves overlap too much.  
6) Export:
   - **Export/Import → Export CSV** for data,
   - Matplotlib toolbar Save for an image/PDF if you want a figure file.

**Controls used (What is what?):** *Plotted Data tab*, *Legend*, *Annotation*, *Grid*, *Waterfall*, *Export/Import*

---

## Export plotted curves to CSV (Export/Import → Export CSV)
Exporting from Plotted Data is for when you have *a set* of curves and you want them in one tidy CSV.

Before you export, decide how you want the columns to be named:
- **User-defined** legend → your custom names become headers.
- **Entry number** legend → entry numbers become headers.
- **None** → export is blocked (there is no naming scheme).

Then:
1) Click **Export/Import → Export CSV**.
2) Choose where to save.

**Controls used (What is what?):** *Export/Import*, *Legend*

---

## Import CSV into Plotted Data
Import is the mirror of export: it lets you bring curves back in, or overlay external curves for comparison.

1) Click **Export/Import → Import CSV**.
2) Select one or more CSV files.

The curves appear in the plotted list and on the plot, ready for styling and export.

**Controls used (What is what?):** *Export/Import*

---

## Use reference spectra (Load reference)
References are for the moments when you want a known spectrum on top of your data—an internal standard, a literature/reference spectrum that you have imported, or a saved “good sample” spectrum.

### Save one of your curves as a reference
1. First send the processed curve to **Plotted Data**.
2. In the plotted-curve list, use the **bookmark / add-to-library** control for that curve.
3. Fill in useful metadata such as element, edge, compound, resolution, and comments. Good metadata matters later when the library grows.
4. Confirm to store the spectrum in the local reference library.

### Load references for comparison
1. Click **Load reference** in Plotted Data.  
2. Pick one or more references and confirm.  
3. They are added to the plotted set so you can style, reorder, or export them together with measured curves.
4. If you are cleaning up the library, **Delete reference** is available inside the same dialog. Deletion is permanent, so keep a backup of a carefully curated `library.h5`.

A reference overlay is an aid to comparison, not an automatic chemical-state assignment. Differences in energy calibration, resolution, normalization, geometry, and sample conditions can all matter.

**Controls used (What is what?):** *Plotted curve list*, *bookmark / add-to-library*, *Load reference*

---

# Multivariate analysis

## Send curves to PCA / decomposition window
This workflow is for *series thinking*: you have many spectra and you suspect the set is a mixture of a few underlying components.

The decomposition window helps you answer questions like:
- “How many independent spectral shapes are present?”
- “Do these spectra move together (one dominant trend) or in several independent ways?”
- “Can I explain the series as mixtures of a few endmembers?”

**How to get there smoothly:**
1) In **Processed Data**, make curves comparable (often you’ll end up with post **Normalize = Area**).  
2) Click **Pass** to move them into **Plotted Data**.  
3) Make sure **Waterfall** is OFF (waterfall is for visualization, not analysis).  
4) Make sure **Legend** is not **None** so the spectra have names.  
5) Click **PCA**.

If requirements are met, curves are sent into the decomposition window where you can run PCA/NMF/MCR‑ALS. Use **Help inside the decomposition window** for method-specific guidance, parameters, diagnostics, and interpretation.

**Controls used (What is what?):** *PCA (decomposition window)*, *Pass*, *Plotted Data tab*


---

# Troubleshooting and a safe first workflow

## If the result looks wrong
Work backwards through the workflow rather than changing several parameters at once.

- **Wrong or missing TEY/PEY/TFY/PFY curves:** check **Setup channels** and the active beamline profile.
- **Wrong x-axis or no sensible energy axis:** check the Energy mapping in the channel profile and inspect the HDF5 tree.
- **I₀-normalized curve becomes noisy or distorted:** verify **Choose I₀** and compare with I₀ normalization disabled.
- **Background looks unphysical:** start with **Auto**, inspect the pre-edge interval, and change **Pre-edge (%)** or **Poly degree** cautiously. Use **Manual** only when the automatic estimate needs deliberate guidance.
- **Several spectra become difficult to compare after separate processing:** try **Group BG** and inspect the result with **Match pre-edge** both off and on.
- **Summation gives no result:** the selected scans may not have enough overlapping energy range for a common grid.
- **CSV export is blocked in Plotted Data:** choose a usable **Legend** mode and make sure every exported curve has a valid name.
- **PCA/decomposition transfer is blocked:** turn **Waterfall** off, use **Area** post-normalization for all transferred curves, and choose a non-None legend.

If a processing choice creates a feature you did not see in the raw data, compare before/after carefully before interpreting it physically.

## A safe complete workflow for a first-time user
1. Open one representative HDF5 file.
2. In **Raw Data**, choose the detector family you actually measured and inspect all scans for outliers.
3. Confirm that the active channel profile identifies the expected Energy and I₀ signals.
4. Move to **Processed Data** and enable only the corrections you understand and need. Start with I₀ normalization if appropriate, then background handling, then post-normalization.
5. For repeated scans of the same sample, inspect them first and then use **Sum up?** if combining them is scientifically justified.
6. For a series that should be compared consistently, consider **Group BG** rather than tuning every spectrum independently.
7. Use **Pass** to collect final processed curves in **Plotted Data**. Choose meaningful names before exporting.
8. Add reference spectra only when they help answer a specific comparison question.
9. Use the decomposition window only for a genuinely comparable spectral series; read the method-specific Help there before interpreting PCA/NMF/MCR-ALS results.
10. Export the processed numerical data as well as any figure you make, so the analysis remains reproducible outside EXACT.

This is a starting workflow, not a compulsory recipe. XAS processing choices depend on the experiment and the scientific question; EXACT deliberately keeps the raw and processed views accessible so you can judge those choices rather than hide them.
