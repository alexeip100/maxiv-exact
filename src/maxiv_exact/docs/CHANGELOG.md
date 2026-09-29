---

# MAX IV EXACT changelog


---

## [2.5.0] – 2026-09-29

### What changed since 2.4.4
- Rebranded the application as **EXACT** — *Exploration of X-ray Absorption: Characterization and Treatment* — with the Python distribution renamed to `maxiv-exact` and the primary launcher changed to `exact`.
- Modernized the runtime from PyQt5 to **PyQt6** and moved the supported environment to **Python 3.14** with current NumPy, SciPy, Matplotlib, h5py, pandas, scikit-learn, and Markdown versions.
- Reworked the user-facing Help for clearer first-time orientation, more balanced workflow guidance, improved light/dark-theme presentation, and clearer coverage of channel setup, processing order, I₀ selection, references, troubleshooting, and decomposition workflows.
- Added a full user-facing README with installation, startup, quick-start, channel-profile, reference-library, and decomposition guidance.
- Refreshed the application identity and presentation, including the EXACT icon and About dialog.
- Added migration and regression fixes required by PyQt6 while preserving the established HDF5 loading, XAS/NEXAFS processing, plotting, reference-library, and PCA/NMF/MCR-ALS workflows.

### Compatibility
- Existing HDF5/reference workflows remain compatible; no intentional scientific-processing algorithm changes were introduced in the 2.5 modernization.
- The legacy `flexpes-nexafs` launcher is retained temporarily, and existing legacy channel-mapping settings are migrated to the new EXACT configuration location when needed.


## [2.5.0a10] – 2026-09-28

### Changed
- Integrated the finalized EXACT icon geometry selected during the icon-only design iteration.
- Removed the white canvas outside the rounded icon frame by preserving alpha transparency outside the frame while keeping the white spectrum background inside the frame opaque.
- Regenerated PNG, Windows ICO, and macOS ICNS application assets from the finalized transparent master.

### Testing
- Verified that the packaged PNG master has transparent corner pixels and an opaque white interior above the spectrum.

## [2.5.0a9] – 2026-09-28

### Changed
- Integrated the finalized EXACT icon into the packaged application assets (`png`, `ico`, and `icns`) after the dedicated icon-design iteration.
- Replaced the placeholder top-level README with a proper user-facing overview aligned in spirit with PANDA, covering capabilities, supported data, installation, launch commands, quick start, channel profiles, and advanced analysis tools.

### Testing
- Added regression coverage for the README structure and preserved the existing icon-asset checks.

## [2.5.0a8] – 2026-09-28

### Changed
- Aligned the About EXACT dialog rubric order with PANDA so the dialog now presents the title/expansion first, followed by version, date, author, license, and then the descriptive paragraph.
- Refined the About text wording to match the concise PANDA style more closely while remaining EXACT-specific.
- Redesigned the EXACT application icon to use the same visual principle as PANDA: a black spectrum silhouette with a white area above it inside a rounded framed icon, while preserving the XAS curve character.

### Testing
- Added regression coverage for the About-dialog field order and kept manual inspection of the refreshed icon and About dialog as part of the pre-RC polish pass.

## [2.5.0a7] – 2026-09-28

### Changed
- Aligned the user-facing Help presentation more closely with PANDA: theme-aware colors, clearer heading hierarchy, and palette-based navigation that works consistently in light and dark application themes.
- Rebalanced **What is what?** and **How to?** for first-time users while preserving the established EXACT documentation and terminology. The Help now explains the normal three-stage workflow, distinguishes processing from display-only controls, and makes the processing order easier to follow.
- Expanded practical guidance for loading/orienting in HDF5 files, choosing I₀, using the reference library, troubleshooting common processing problems, and following a safe complete first workflow.
- Corrected remaining legacy documentation wording after the EXACT rebranding.

### Testing
- Added regression coverage for Help structure, first-time-user topics, theme-aware rendering, and removal of stale product branding from active Help.

## [2.5.0a6] – 2026-09-28

### Changed
- Rebranded the application as **EXACT** — *Exploration of X-ray Absorption: Characterization and Treatment*.
- Renamed the Python distribution to `maxiv-exact` and the import package to `maxiv_exact`.
- Added `exact` as the primary launcher and `maxiv-exact` as an alternate launcher.
- Retained `flexpes-nexafs` as a temporary compatibility launcher for the 2.5 transition.
- Renamed application resources/build files to the EXACT identity and changed the Windows application ID to `MAXIV.EXACT`.
- Updated application/About/help titles and package metadata to the EXACT identity while retaining FlexPES references where they describe the beamline or data format.

### Compatibility
- Existing legacy `~/.flexpes_nexafs/channel_mappings.json` settings are copied to the new EXACT user configuration location on first use when needed.
- The project history and existing HDF5/reference data remain compatible; this is a rebrand of the existing software, not a new codebase.

### Testing
- Updated regression tests for the new distribution/import/launcher names and application resources.

## [2.5.0a5] – 2026-09-28

### Changed
- Completed the modernization cleanup pass without changing application workflows or scientific algorithms.
- Modernized project metadata for the Python 3.14/PyQt6 baseline, including SPDX-style MIT license metadata and Python 3.14 classifiers.
- Removed obsolete NumPy 1.x integration fallback code now that NumPy 2.5.3 or newer is required.
- Removed stale imports and Qt5-era comments left by earlier refactors while preserving runtime behavior.
- Extended the development README with explicit clean-environment verification commands.

### Testing
- Added regression checks for the cleaned packaging metadata and removal of the obsolete NumPy 1.x fallback.
- Full automated regression suite remains required before the release-candidate build.

## [2.5.0a4] – 2026-09-28

### Changed
- Raised the supported Python runtime to Python 3.14 for the modernization baseline.
- Updated the declared runtime dependency floors to the current stable scientific/GUI stack targeted for 2.5.0: PyQt6 6.11, NumPy 2.5.3, SciPy 1.18.1, Matplotlib 3.11.2, h5py 3.16.0, pandas 3.0.6, scikit-learn 1.9.1, and Markdown 3.10.3.
- Added a conda-forge environment definition for a clean Python 3.14/PyQt6 development installation.
- Documented that the editable package should be installed with `pip install -e . --no-deps` after conda creates the dependency stack, avoiding mixed pip/conda Qt runtimes.

### Testing
- Added metadata regression checks for the Python 3.14 floor, modern dependency floors, and the conda environment definition.
- No intentional GUI, workflow, or scientific-processing algorithm changes are included in this build.

## [2.5.0a3.post3] – 2026-09-28

### Fixed
- Audited all dialog result handling for PyQt6.
- Replaced remaining Qt5-style `dlg.Accepted` result checks with `QDialog.DialogCode.Accepted` across library, processing, and main-window workflows.

### Testing
- Added regression coverage for legacy Qt5 dialog/enum constants so the same migration class is caught automatically.

## [2.5.0a3.post2] – 2026-09-28

### Fixed
- Added missing PyQt6 widget imports for `QAbstractItemView` in the reference-library browser and `QApplication` in plotting core, fixing runtime `NameError` failures introduced during the Qt6 migration.

### Testing
- Added a static Qt-symbol import audit so referenced Qt classes beginning with `Q` must be imported or locally defined.

## [2.5.0a3.post1] – 2026-09-28

### Fixed
- Fixed PyQt6 checkbox state handling for signals that emit integer check states, restoring group loading such as **All PEY data** and related checkbox-driven controls.

## [2.5.0a3] – 2026-09-28

### Fixed
- Fixed a PyQt6 startup regression in `app.py`: the application event loop is now returned from `main()` and `sys.exit(main())` is only executed when the module is run as a script. This prevents the console entry point from hitting a module-level `sys.exit(app.exec())` call with no `sys` import.

### Testing
- Added a regression check that forbids a top-level `sys.exit(...)` call in `app.py` and verifies that `main()` owns the Qt event-loop return.

## [2.5.0a2] – 2026-09-28

### Changed
- Migrated the application from PyQt5 to native PyQt6 while preserving the existing user workflow and processing behavior.
- Updated Qt5-style enums, dialog execution calls, drag/drop flags, file-dialog options, and other Qt APIs to their PyQt6 equivalents.
- Switched Matplotlib Qt canvas/toolbar imports from `backend_qt5agg` to the binding-neutral `backend_qtagg`.
- Updated packaging/PyInstaller Qt collection from PyQt5 to PyQt6 and changed the runtime Qt dependency to `PyQt6>=6.8`.
- Kept the Python version floor and all non-Qt scientific dependency requirements unchanged for this build.

### Testing
- Updated modernization regression checks so the source tree cannot silently reintroduce PyQt5 imports, the Qt5 Matplotlib backend, or `exec_()` calls.

## [2.5.0a1] – 2026-09-28

### Changed
- Began the 2.5 modernization series with a deliberately behavior-preserving baseline build.
- Strengthened automated baseline coverage for package metadata, entry-point wiring, bundled channel mappings, example HDF5 data, and the current Qt5/Matplotlib backend assumptions ahead of the PyQt6 migration.
- No intentional application workflow, GUI, data-processing, or dependency changes are included in this build.

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


