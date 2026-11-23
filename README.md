# MAX IV EXACT

**EXACT — Exploration of X-ray Absorption: Characterization and Treatment**

EXACT is a Python software package with an interactive graphical interface for browsing, processing, visualizing, and decomposing X-ray absorption spectra stored in HDF5 files. It was originally developed for data collected at the **FlexPES beamline** at **MAX IV Laboratory**.

Starting with the **2.5 series**, the same software continues under the **EXACT** name and the Python distribution **`maxiv-exact`**.

## Main capabilities

- **Inspect XAS and NEXAFS data.** Browse HDF5 scans, detector signals, and acquisition metadata. Use configurable channel profiles to identify photon energy, incident intensity (I₀), and detector signals such as TEY, PEY, TFY, and PFY.
- **Process and compare spectra.** Normalize by I₀, subtract backgrounds, apply consistent processing across a series, and combine repeat scans. Correct photon energies for individual spectra or subtract a scaled reference from one spectrum or a series.
- **Analyze fluorescence detector maps.** Inspect emission spectra, select emission regions to extract excitation spectra, or fit emission peaks across a scan. Review fitted, residual, and component maps, then send the extracted spectra to Processed Data.
- **Fit NEXAFS series and follow trends.** Fit Gaussian resonances and ionization steps across consistently processed spectra. Compare fitted parameters and peak area ratios, inspect residuals, and save or export the analysis.
- **Explore spectral mixtures.** Use PCA to examine variation across a series, and NMF or MCR-ALS to estimate component spectra and their contributions.
- **Visualize and export results.** Compare processed spectra as overlays or waterfall plots. Export individual spectra on their own energy grids or combine them in one CSV by aligning them within their shared energy range.

**Reference tools.** Save and reuse measured spectra in a personal library, open external HDF5 literature spectra with their stored metadata, and consult bundled atomic X-ray data or calculate compound mass attenuation coefficients. The external literature reference database is a work in progress and is not included.

**Experimental tool.** Self-absorption correction is available for evaluation and has yet to be validated for routine quantitative use.

## Supported data format

EXACT currently focuses on **HDF5** files used for X-ray absorption spectroscopy workflows. The package includes an example HDF5 file structure and is designed around the FlexPES data organization, while the **channel profile** system makes it adaptable to related HDF5 layouts.

## Installation

A dedicated **conda environment** is recommended. EXACT 2.7.1 targets **Python 3.14** and **PyQt6**.

Create the environment once. The command below installs the important Qt/scientific dependencies explicitly, including **h5py** (required for HDF5 files):

```bash
conda create -n exact --override-channels -c https://conda.anaconda.org/conda-forge python=3.14 pyqt6 pyqt6-webengine numpy scipy matplotlib h5py pandas scikit-learn markdown pip
```

**Important:** Install `pyqt6-webengine` with Conda as shown above, not through pip. Installing the wheel without `--no-deps` may pull in pip-managed Qt libraries and leave Qt unable to find its Windows platform plugin. The explicit conda-forge URL and `--override-channels` prevent a misconfigured `defaults` channel from taking priority.

Activate the environment:

```bash
conda activate exact
```

Then choose **one** installation method.

### From a GitHub release wheel (recommended for most users)

1. Open the EXACT repository on GitHub.
2. Open **Releases** and choose the **Latest** release.
3. Scroll to the **bottom of the release page** and expand **Assets** if necessary.
4. Download the file ending in **`.whl`** (for example `maxiv_exact-2.7.1-py3-none-any.whl`).
5. Open a terminal in the folder containing the downloaded wheel and install it:

```bash
pip install --no-deps maxiv_exact-2.7.1-py3-none-any.whl
```

### From the source folder

Open a terminal in the `maxiv-exact` folder and run:

```bash
pip install . --no-deps
```

### Development installation

If you are modifying the source code, install it in editable mode instead:

```bash
pip install -e . --no-deps
```

> Use the conda-forge packages **`pyqt6`** and **`pyqt6-webengine`**, not `pyqt` (PyQt5). **Always use `--no-deps`** when installing EXACT into this Conda environment, including from a wheel or local source. If Qt fails to find its Windows platform plugin, check package sources with `conda list | findstr /i "pyqt qt6 webengine"`; do not modify your launcher or plugin paths before checking for mixed pip/Conda Qt files.

## Starting EXACT

After installation, start the application with:

```bash
exact
```

The following compatibility/alternative launcher is also available:

```bash
maxiv-exact
```

The older launcher is retained for compatibility with earlier installations:

```bash
flexpes-nexafs
```

EXACT can also be started as a Python module:

```bash
python -m maxiv_exact
```

## Quick start

1. Start **EXACT**.
2. Use **Open HDF5 files** to load one or more HDF5 data files.
3. In the left file tree, explore the available scans and detector channels.
4. Load a detector group such as **TEY**, **PEY**, **TFY**, or **PFY**, or use the group-loading controls to load all curves in a selected channel.
5. For fluorescence detector maps, use **Processed Data → FY Analysis → FL Map Analysis** and consult **Help → How to? → FL Map Analysis**.
6. Use the right-hand curve trees/lists (or **Check all / Uncheck all**) to control visibility, then move selected spectra to the processing workflow and inspect how raw and processed representations differ.
7. Choose an appropriate **I₀** signal and apply normalization/background options as needed.
8. Compare the results in the plotting area, optionally using grouping, summation, references, or decomposition tools.

Use the **⚙ Settings** button next to the main file controls to choose **System**, **Light**, or **Dark** theme and to enlarge the Qt interface font by +1 or +2 pt. These appearance settings are remembered between sessions; Matplotlib plot font sizes remain independent. Common control geometry and key tree/list minimum widths scale with the selected UI font size to avoid clipped labels.

The built-in **Help** menu contains the detailed user guidance:

- **What is what?** — explains the interface and controls.
- **How to?** — explains typical workflows.
- **What’s new** — summarizes the main changes between versions.

## Channel profiles and detector roles

EXACT uses a configurable **channel-mapping** system so that the software can associate HDF5 dataset names with canonical detector roles such as:

- **Energy**
- **I₀**
- **TEY**
- **PEY**
- **TFY**
- **PFY**

The active profile can be reviewed and edited using **Setup channels**. This makes it possible to adapt EXACT to different HDF5 naming conventions without changing the code.

## X-ray reference data, reference spectra, and decomposition

The separate **Reference** tab provides bundled Henke/CXRO and Chantler/XrayDB atomic data and can calculate Chantler-based compound mass attenuation coefficients from chemical formulas. This built-in database is separate from the user-maintained **reference spectrum library**, where processed experimental spectra can be saved and loaded again for comparison. For more advanced analysis, selected spectra can be sent to the decomposition tools, where **PCA**, **NMF**, and **MCR-ALS** can be used to explore spectral components and mixtures.

EXACT can also open external HDF5 literature spectra with their stored metadata. The literature reference database is a work in progress and is not included in this release.

## Testing

The repository includes a pytest regression suite under `tests/`. Run it with:

```bash
python -m pytest
```

## Author

**Created by:** Alexei Preobrajenski (MAX IV Laboratory)

## License

**License:** MIT

Copyright (c) 2026 Alexei Preobrajenski, MAX IV Laboratory. See [LICENSE](LICENSE).
