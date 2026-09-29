# MAX IV EXACT

**EXACT — Exploration of X-ray Absorption: Characterization and Treatment**

EXACT is a Python software package with an interactive graphical interface for browsing, processing, visualizing, and decomposing X-ray absorption spectra stored in HDF5 files. It was originally developed for data collected at the **FlexPES beamline** at **MAX IV Laboratory**.

Starting with the **2.5 series**, the same software continues under the **EXACT** name and the Python distribution **`maxiv-exact`**.

## Main capabilities

- Load and inspect X-ray absorption data stored in HDF5 files.
- Work with the common detector channels used in FlexPES XAS/NEXAFS measurements, including **TEY**, **PEY**, **TFY**, **PFY**, and the corresponding **I₀** signal.
- Use built-in or user-edited **channel profiles** to map HDF5 dataset names to the physical detector roles.
- Browse raw curves, load detector groups, and send selected spectra to the processing workflow.
- Apply common XAS/NEXAFS pre-processing steps such as normalization, background handling, averaging/summation, and grouped background alignment.
- Compare spectra visually in overlay or waterfall-style presentations.
- Build and reuse a **reference spectrum library**.
- Perform decomposition analysis with **PCA**, **NMF**, and **MCR-ALS** tools.
- Export processed spectra and decomposition results for further analysis.

## Supported data format

EXACT currently focuses on **HDF5** files used for X-ray absorption spectroscopy workflows. The package includes an example HDF5 file structure and is designed around the FlexPES data organization, while the **channel profile** system makes it adaptable to related HDF5 layouts.

## Installation

A dedicated **conda environment** is recommended. EXACT 2.5 targets **Python 3.14** and **PyQt6**.

Create and activate the environment once:

```bash
conda create -n exact -c conda-forge --strict-channel-priority python=3.14 pyqt6 numpy scipy matplotlib h5py pandas scikit-learn markdown
conda activate exact
```

Then choose **one** installation method.

### From a GitHub release wheel

```bash
pip install --no-deps <path-to-maxiv_exact-*.whl>
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

> Use the conda-forge package **`pyqt6`**, not `pyqt` (which installs PyQt5). Keeping the Qt/scientific dependencies under conda and using `--no-deps` for EXACT avoids mixed pip/conda Qt installations.

## Starting EXACT

After installation, start the application with:

```bash
exact
```

The following launchers are also available:

```bash
maxiv-exact
flexpes-nexafs
```

`flexpes-nexafs` is retained temporarily as a compatibility launcher during the 2.5 transition.

EXACT can also be started as a Python module:

```bash
python -m maxiv_exact
```

## Quick start

1. Start **EXACT**.
2. Use **Open HDF5 files** to load one or more HDF5 data files.
3. In the left file tree, explore the available scans and detector channels.
4. Load a detector group such as **TEY**, **PEY**, **TFY**, or **PFY**, or use the group-loading controls to load all curves in a selected channel.
5. Move selected spectra to the processing workflow and inspect how raw and processed representations differ.
6. Choose an appropriate **I₀** signal and apply normalization/background options as needed.
7. Compare the results in the plotting area, optionally using grouping, summation, references, or decomposition tools.

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

## Reference library and decomposition

Processed spectra can be saved to the internal **reference library** and loaded again for comparison. For more advanced analysis, selected spectra can be sent to the decomposition tools, where **PCA**, **NMF**, and **MCR-ALS** can be used to explore spectral components and mixtures.

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
