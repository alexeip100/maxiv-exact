---

# MAX IV EXACT changelog

---

## [2.5.2] – 2026-10-01

### Added
- Added a separate **Reference** tab with bundled offline **Henke/CXRO** and **Chantler/XrayDB** X-ray reference data, including atomic scattering factors, Chantler mass attenuation coefficients, source comparison, full-range viewing, and a draggable photon-energy cursor with live values.
- Added chemical-composition handling in the Reference tab: one or several formulas can be entered to calculate and compare **Chantler-based compound mass attenuation coefficients**, and **μ compare** overlays `μ photo`, `μ incoh`, and `μ total` for one element or compound.

### Fixed
- Help search matches are now highlighted clearly so they remain easy to locate across application themes.

### Changed
- Expanded the built-in Help and README for the new reference-data workflow, including source conventions, compound attenuation, rendered scientific equations, and clearer installation instructions.

## [2.5.1] – 2026-09-30

### Added
- HDF5 files can now be loaded by drag-and-drop onto any of the three main plotting areas (**Raw Data**, **Processed Data**, or **Plotted Data**) as well as onto the **HDF5 Structure** tree.
- Added a **Settings** cog with persistent **System / Light / Dark** themes and UI font-size choices (**Default / +1 pt / +2 pt**). Plot/figure font sizes remain independent.
- Added **Check all** and **Uncheck all** buttons below the curve list/tree in all three data tabs.

### Changed
- **Clear all** and **Close all** now return the interface to **Raw Data**, matching the normal load → process → plot workflow.
- Raw, Processed, and Plotted Data now use a consistent initial canvas/sidebar proportion. The divider remains adjustable, with a font-aware minimum width for the curve sidebar.
- UI font-size changes now scale the relevant control geometry, spacing, tab margins, and key tree/list minimum widths together with the text.

## [2.5.0.post1] – 2026-09-29

### Fixed
- Corrected the published source/tag content and release-facing documentation for 2.5.0. The intended application functionality is unchanged.

## [2.5.0] – 2026-09-29

### Added
- Introduced the **EXACT** application identity — *Exploration of X-ray Absorption: Characterization and Treatment* — with the `exact` launcher and `maxiv-exact` Python distribution.
- Added a fuller first-time-user Help/README covering loading, channel setup, processing order, I₀ selection, references, troubleshooting, and decomposition workflows.

### Changed
- Migrated the GUI from PyQt5 to **PyQt6** and moved the supported runtime to **Python 3.14** with a current scientific Python stack.
- Refreshed the application icon, About dialog, and Help presentation while preserving the established HDF5/XAS workflow.

### Fixed
- Fixed compatibility issues uncovered by the PyQt6 migration, including checkbox-state handling, dialog results, missing Qt imports, and application startup behavior.

## [2.4.4] – 2026-09-07

### Added
- Updated the FlexPES XAS application icon and added the same logo to the **About** dialog.
- Added platform-specific icon assets for Windows, macOS, and Linux; on Windows 11 the running app now uses the dedicated FlexPES icon reliably in the taskbar.

### Fixed
- CSV export now remembers the last folder chosen during the current session; after restarting the app, the default returns to the loaded data folder.
- **Plotted Data** waterfall curves and legend entries now follow the same top-to-bottom order.
- **Processed Data → Pass** now remains enabled whenever exactly one processed curve is selected.
- Fixed a macOS/PyQt5 crash when opening **Processed Data** with spectra whose Matplotlib colors are represented as RGB/RGBA tuples.

## [2.4.3] – 2026-08-27

### Added
- Added a visible activity indicator below the **HDF5 Structure** tree while HDF5 files or grouped channel data are being loaded/updated.
- New HDF5 files, including recursive channel discovery for **All in channel**, are scanned in a separate background process so slow local or network HDF5 access does not block the main GUI.
- Added the FlexPES XAS application icon to the main window/application.

### Fixed
- **Plotted Data → Reset original view** now returns to the full range of the currently plotted spectra instead of sometimes restoring an older energy range.

### Changed
- **Clear Plotted** now asks for confirmation before removing all plotted curves.
- GUI font sizing is now consistent with the FlexPES PES application.
- **Help → What is what?** and **How to?** have improved presentation and a clearer, more coherent organization while retaining the existing documentation content and workflow.

## [2.4.2] – 2026-07-01

### Added
- MCR-ALS: optional component fraction bounds can now be set per component in %, with Closure required.
- MCR-ALS: bound diagnostics report when constraints are active and warn about possible over-constraint.
- MCR-ALS: random initialization now has a reproducible Seed control.
- MCR-ALS: optional local stability band estimates run-to-run σ(C) from perturbed initial guesses.

### Fixed
- The default grid now appears immediately in **Plotted Data** after the first **Group BG → Pass** operation in a newly opened app.
- MCR-ALS: full-range component bounds (0–100%) now leave the fit unchanged.
- MCR-ALS: the stability band can now be shown or hidden after a run without recalculation.

### Changed
- MCR-ALS controls were reorganized into a clearer layout with a right-side constraints/diagnostics panel and shorter tooltips.
- MCR-ALS: the component-bounds table is now more compact and the Run button shows a busy indicator while calculations are active.
- Improved the visual formatting of **Help → What’s new** section headings.

## [2.4.1] – 2026-06-30

### Added
- HDF5 files can now be loaded by drag-and-drop onto the left **HDF5 Structure** tree. Multiple `.h5`/`.hdf5` files are supported.
- Re-opening or dropping an already loaded file name can now refresh the file from disk, keeping existing work where possible and adding newly appended curves.

### Fixed
- Fixed repeated normalization errors that could appear after refreshing a loaded file.
- Fixed a Group BG issue that could affect passing corrected curves to the **Plotted Data** tab.
- Improved reliability when reading HDF5 files that are still being updated during acquisition.

## [2.4.0] – 2026-03-24

### Changed
- Updated the startup DPI handling so that the GUI keeps the same appearance as on 1920×1080 screens also on higher-resolution displays, avoiding automatic enlargement of fonts and widgets.
- In CSV export from the Plotted Data panel, column headers in the “Entry number” naming mode are now written as entry#### instead of plain numeric values, to avoid them being misinterpreted as data by other software.


## [2.3.9] – 2026-03-23

### Added
- Processed Data: summed groups (created via **Sum up?**) now support a right-click context menu in the Processed tree:
  - **Group info** shows which curves constitute the group,
  - **Rename** updates the group name (and updates the label in Plotted Data if the curve is present there),
  - **Delete** removes the summed group after an OK/Cancel warning (does not delete it from Plotted Data).


## [2.3.8] – 2026-02-02

### Changed
- Major internal refactor: the former large `plotting.py` was reorganized into a `plotting/` package of smaller mixin modules for maintainability.

### Added
- Help: split **Usage** into three menu entries — **What is what?** (Controls), **How to?** (Workflows), and **What's new?" (log of latest changes) — all opening the same viewer window but loading different markdown content.
- Usage viewer: search with **Next/Prev** navigation and **Ctrl+F** support; TOC generated from **H3** headings for quick jumping.
- Help content: key topics are expanded and clarified.


## [2.3.7] – 2026-01-29

### Fixed
- Group loading / plotting robustness: malformed or empty (“0-length” / scalar) 1D datasets no longer prevent plotting of valid spectra; group-loading (e.g. *All in TEY*) now skips invalid datasets instead of aborting with `len() of unsized object`.

### Changed
- Energy regions for interrupted scans: region grouping can infer the intended scan window from an entry’s `title` string and collapses aborted/partial scans into a single region labeled `(E_start – unfinished)` when appropriate (fallback to measured start/end if the title cannot be parsed).
- Curve summation UX: replaced simple “sum all visible” behavior with an interactive summation workflow that materializes summed curves as first-class processed curves while optionally unchecking their constituents.
- Legend tooltip in the Plotted Data tab is made context-aware (dependent on the legend mode).

### Added
- Curve summation dialog (Processed Data):
  - Drag-and-drop grouping of available curves into editable groups (`Group1`, `Group2`, …).
  - Prevents duplicate group names (warning on OK).
  - Supports single-curve groups (creates an identity summed curve that keeps the group name).
  - Summed curves inherit the same Region as their constituents.
- Help → Usage updated to describe energy regions (including “unfinished” grouping) and the new curve summation workflow.


## [2.3.6] – 2026-01-28

### Fixed
- Decomposition (PCA/NMF/MCR): prevented crashes on datasets containing NaNs by trimming to the common energy overlap, auto-repairing isolated interior NaNs, and prompting the user before interpolating larger NaN gaps; aligned behavior with CSV export.
- Raw-tree “energy regions”: corrected unexpected region splitting during group loading by grouping datasets only by start/end energies with a tolerance (≤ 0.01 eV), independent of NaNs in the signal.
- Processed Data: when *Group BG* is enabled and *Subtract BG* is unchecked, individual background curves are now visualized correctly.
- Plotted Data: *Clear all* no longer removes the grid (now preserves grid settings like *Clear Plotted*).

### Changed
- Help → Usage updated to document the new right-click edit actions for annotation and legend.
- Package maintenance: removed an unused internal module (`state.py`).

### Added
- Plotted Data: a full-featured *Edit annotation* dialog (right-click annotation) with font size, font style (bold/italic/underline), font color, optional background color, padding control, and a quick symbol inserter , as well as a context tooltip (“Right click to edit”) when hovering the annotation.
- Plotted Data: *Legend style* editor (right-click legend) with transparency, margins (padding), font size, and font style, plus the same hover tooltip (“Right click to edit”).


## [2.3.5] – 2026-01-12

### Fixed
- UI state desynchronization between “Show all …” toggles / “All in channel” and the file-tree checkmarks is removed:
  - no stale checkmarks,
  - overlapping selections stay synchronized,
  - changing/untoggling one selector no longer removes curves selected by another.
- Keyboard navigation in the HDF5 tree now updates scalar/text display; selecting a group expands it instead of producing an error.
- Channel setup: prevent saving a profile without an Energy channel; prevent duplicate channel assignments across roles.

### Changed
- Plot UX: curve colors no longer reshuffle when (de)selecting curves (colors remain stable).
- Plotted Data default curve thickness set to an integer value (default = 2).
- Processed-tab export tooltip wording updated to match single-curve export behavior.

### Added
- Confirmation dialog when enabling “Sum up” across multiple energy regions.


## [2.3.4] – 2026-01-12 

### Fixed
 - Ensure `QApplication` is created before importing/constructing the main UI (lazy-import `MainWindow` inside `main()`).
 - Prevent mixed Qt bindings by preferring **PyQt5 consistently** across the package (avoids PyQt6 `QApplication` + PyQt5 widgets mismatch).


## [2.3.3] – 2026-01-12

### Fixed
- Fixed a startup crash in fresh environments (`QWidget: Must construct a QApplication before a QWidget`) by ensuring the Qt `QApplication` is created before importing and constructing the main UI (moved the `MainWindow` import inside `main()` in `app.py`)


## [2.3.2] – 2026-01-09

### Fixed
- Manual background subtraction: anchor points now match the selected polynomial degree (number and placement), instead of always showing the degree-3 anchor pattern
- Plotted Data legend: switching legend mode no longer shrinks/rescales the plot; the legend is kept inside the axes by adjusting its anchor position
- Decomposition app anchors: fixed multiple issues preventing anchors/components from being plotted or used reliably (including missing imports and component/anchor plotting failures)
- Anchor workflow integration: MCR-ALS components are now automatically available in the anchor calibration workflow when switching tabs

### Added
- Decomposition app workflow improvements for anchors: more robust loading of raw anchor CSV spectra, and improved calibration/application of anchors against decomposition components
- Decomposition app usability: added **Clear all** and a general **Help** on the Data tab to support standalone work on external CSV datasets (not only PCA-passed data)

### Changed
- Decomposition app layout: splitters (draggable dividers) added on Data and Anchor tabs for flexible resizing of plots vs control panels
- PCA button behavior: if no curves are selected, the decomposition app can still be launched (with an explicit OK/Cancel warning) and Open CSV is enabled
- Decomposition app defaults: Auto-k is OFF by default and k defaults to 2


## [2.3.1] – 2026-01-07

### Fixed
- Restored compatibility with newer NumPy versions (NumPy ≥ 2.4), where `numpy.trapz` is no longer available, by switching to trapezoidal integration via `numpy.trapezoid` with a fallback for older NumPy versions
- Added a small internal helper module (`compat.py`) to keep the same integration API across NumPy 1.x and 2.x

### Changed
- Improved responsiveness when launching the decomposition tool: the first press of **PCA** now opens the decomposition app in under ~1 second by preloading heavy dependencies after launch (in `app.py`).


## [2.3.0] – 2026-01-05

### Fixed
- Fixed an uncertainty when selecting <select curve name> entries in the Plotted Data legend, which could previously result in renaming the wrong curve.

### Added
- Added a major new tool for spectral decomposition analysis, accessible via the “PCA” button in the Plotted Data panel.
- The decomposition tool allows direct transfer of selected plotted spectra to an advanced analysis workspace without intermediate file export.
- Supported decomposition methods include PCA and chemically motivated variants (NMF, MCR-ALS, anchor-based analysis), provided in a dedicated decomposition application.
- Strict validation is applied before decomposition, ensuring that spectra are background-subtracted, area-normalized, share a common energy axis, and are free of display offsets.
- Added descriptive tooltip hints to buttons, checkboxes, and combo boxes throughout the main application to improve usability.
-   Extended Help → Usage documentation with a general explanation of PCA and related methods, and with a description of the PCA workflow.


## [2.2.0] – 2025-12-30

### Fixed
- Fixed a crash when selecting "Manual" background subtraction.

### Changed
- "Group BG" workflow is now more intuitive: the "Group BG" checkbox becomes available as soon as more than one curve is selected in the "Processed Data" tab.
- Enabling "Group BG" automatically switches to "Auto" BG, enables "Subtract BG", and selects "Area" normalization; these settings remain fixed while "Group BG" is enabled (except "Subtract BG", which can be toggled to preview unsubtracted curves with individual backgrounds).
- Simplified "Waterfall" in the "Plotted Data" tab: removed *Adaptive step* and kept only *Uniform step*; replaced the Waterfall mode combobox with a checkbox.
- Minor UI text shortening and layout tweaks; "Help → Usage" updated accordingly.

### Added
- Added a bundled 'channel_mappings.json' with editable “beamline profiles” mapping canonical roles (TEY/PEY/TFY/PFY, I₀, Energy) to HDF5 dataset names; enables use with different beamlines.
- Added a "Setup channels" button and an "Active beamline" indicator (default profile: "FlexPES-A"), including a dialog to create/select/edit/save profiles.
- Added "Delete reference" in the “Load reference” dialog to permanently remove individual spectra from `library.h5` after confirmation.


## [2.1.0] – 2025-12-24

### Added
- Now it is possible to fit background automatically to a group of selected XAS spectra consistently, keeping both area and the absorption jump the same for all spectra (new check box "Group BG"), and also making sure the pre-edge intensity is at zero (new check box "Match pre-edge slope").
- The "Pass" button can work now also on a group of spectra, provided the "Group BG" check box is checked.
- Selected pre-edge region on the "Processed Data" tab is marked now with a vertical line, which is mouse-draggable.
- Legend on the "Plotted Data" panel can now be set automatically with the entry numbers.

### Changed
- Help -> Usage text is updated.
- Help -> Usage dialog window appearance is improved: Content menu added, font size widget added, maximixation option added.


## [2.0.0] – 2025-12-04

### Added
- an example h5 file with typical structure used at FlexPES is added to the package in the \example_data folder along with a README.md file describing its structure.
- upon pressing "Open HDF5 files" button, the opening dialog is pointing now by default to this example file.


## [1.9.9] – 2025-12-02

### Fixed
- A bug with the manual background being invisible upon unchecking "Subtract background" box is fixed.
- A bug in the appearance of the Help->Usage window is fixed: the text is now rescaled upon window resize.

### Added 
- It is possible now to close not only all h5 files at once, but also individual files, by selecting a file and either pressing "Delete" or right-click and pressing "Close". 
- Manual background can now be changed by the drag-and-drop of the anchor points not only in Y but also in X direction.


## [1.9.8] – 2025-11-22

### Fixed
- A few bugs related to the appearance of curves and legends in the "Plotted Data" plot are fixed.

### Added
- Annotation option is added for the plot in the "Plotted Data" panel.
- Reference spectra library file (library.h5) is added; spectra in the list on the "Plotted Data" panel can be added to the library using the new "bookmark" button in each row.
- "Load reference" button allows to load a reference spectrum saved in the file library.h5 (for these spectra the "bookmark" buttons are disabled).

### Changed
- Help -> Usage text is updated.


## [1.9.7] – 2025-11-15

### Fixed
- A bug crashing the application is fixed.


## [1.9.6] – 2025-11-15

### Added
- It is possible now to remove curves from the list in the "Plotted Data" panel by clicking a "Cross" button in front of any specific curve, with corresponding adjustment of the plot.

### Changed
- "Grid" check box is replaced with the "Grid:" combo box, which allows to apply grids with different line density.
- "Help"->"Usage" is updated. 


## [1.9.5] – 2025-11-12

### Added
- The curve list in the “Plotted Data” panel is now interactive: dragging curves up or down with the mouse instantly updates the plot and reorders the legend accordingly upon release (most noticeable in the Waterfall representation).


## [1.9.4] – 2025-11-11

### Added
- Group loading of any channel (not only TEY, PEY, TFY and PFY) is now enabled by using a combo box "All in channel:"

### Changed
- Package structure has been completely refactored: the code is now split into several modules (ui.py, data.py, plotting.py, etc) to simplify development.
- Help updated
- Help is refactored from plotting.py into a dedicated markdown file (help.md in DOCS) for easier updating. 

## [1.9.2] – 2025-10-11

### Added
- New features of Waterfall representation in the Plotted Data panel

### Fixed

- Fixed bugs in the post-normalization of the summed curves (to Max, Jump and Area).
- Fixed bug of passing a summed curve and all curves constituting the sum: toggling Waterfall does not remove the very first curve any more.


## [1.9.1] – 2025-10-09

### Changed

- H5 files are no longer open for the lifetime of the app -> other software can open them simultaneously for writing (e.g. Sardana) 
- Better "Open file" dialog

### Fixed

- Improved stability of background subtraction toggle (`Subtract background?`) for manual BG in case of summed curves.


