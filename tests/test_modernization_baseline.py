"""Baseline contracts for the 2.5 modernization series.

These tests protect the modernization contracts as the 2.5 series advances.
The 2.5.0rc1 build continues the cleaned Python 3.14/current-dependency modernization baseline and must not regress to Qt5.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "maxiv_exact"


def test_project_entry_point_and_python_floor_are_explicit():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.14"' in pyproject
    assert 'exact = "maxiv_exact.app:main"' in pyproject
    assert 'maxiv-exact = "maxiv_exact.app:main"' in pyproject
    assert 'flexpes-nexafs = "maxiv_exact.app:main"' in pyproject


def test_a7_is_the_intentional_native_pyqt6_baseline():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    app = (PKG / "app.py").read_text(encoding="utf-8")

    assert '"PyQt6>=6.11"' in pyproject
    assert "PyQt5" not in pyproject
    assert "backend_qtagg" in ui
    assert "backend_qt5agg" not in ui
    assert "from PyQt6" in app

    for source in PKG.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "from PyQt5" not in text, source
        assert "import PyQt5" not in text, source
        assert ".exec_(" not in text, source


def test_root_and_packaged_changelogs_stay_identical():
    root_log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    packaged_log = (PKG / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert packaged_log == root_log
    assert "## [2.5.0rc1] – 2026-09-29" in root_log


def test_bundled_channel_mapping_schema_is_valid():
    mapping_path = PKG / "docs" / "channel_mappings.json"
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))

    profiles = payload["profiles"]
    assert payload["active_profile"] in profiles
    assert {"FlexPES-A", "FlexPES-B"}.issubset(profiles)

    for name, profile in profiles.items():
        assert "Energy" in profile, name
        assert isinstance(profile["Energy"], list) and profile["Energy"], name
        assert "I0" in profile, name
        assert isinstance(profile["I0"], list) and profile["I0"], name


def test_bundled_example_hdf5_is_readable_and_has_measurement_entries():
    example = PKG / "example_data" / "example_Cu_oxide_mixtures.h5"
    assert example.is_file()

    with h5py.File(example, "r") as handle:
        entries = sorted(name for name in handle if name.startswith("entry"))
        assert len(entries) >= 20
        first = handle[entries[0]]
        assert "measurement" in first
        assert len(first["measurement"].keys()) > 0


def test_core_modules_compile_without_importing_the_gui():
    """Catch syntax-level regressions while remaining safe for headless CI."""
    modules = [
        PKG / "compat.py",
        PKG / "hdf5_loading.py",
        PKG / "decomposition" / "mcr_als_core.py",
        PKG / "utils" / "nan_policy.py",
        PKG / "utils" / "sorting.py",
    ]
    for module in modules:
        compile(module.read_text(encoding="utf-8"), str(module), "exec")


def test_qt_class_references_are_imported_or_defined():
    """Catch missing Qt class imports without importing GUI modules."""
    import ast

    for source in PKG.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported = set()
        defined = set()
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
                defined.update(arg.arg for arg in node.args.args)
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    defined.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    used.add(node.id)

        missing = sorted(
            name for name in used
            if name.startswith("Q") and name not in imported and name not in defined
        )
        assert not missing, f"{source}: Qt-like names used without import/definition: {missing}"
