from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_modern_dependency_floors_are_declared():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected = [
        'requires-python = ">=3.14"',
        '"PyQt6>=6.11"',
        '"numpy>=2.5.3"',
        '"scipy>=1.18.1"',
        '"matplotlib>=3.11.2"',
        '"h5py>=3.16.0"',
        '"pandas>=3.0.6"',
        '"scikit-learn>=1.9.1"',
        '"markdown>=3.10.3"',
    ]
    for item in expected:
        assert item in pyproject


def test_conda_environment_is_python314_qt6_only():
    env = (ROOT / "environment.yml").read_text(encoding="utf-8").lower()
    assert env.startswith("name: exact\n")
    assert "python=3.14" in env
    assert "pyqt6>=6.11" in env
    assert "\n  - pyqt\n" not in env
    assert "qt-main" not in env
    assert "pyqt5" not in env


def test_conda_environment_covers_project_runtime_dependencies():
    env = (ROOT / "environment.yml").read_text(encoding="utf-8").lower()
    for name in ["pyqt6", "numpy", "scipy", "matplotlib", "h5py", "pandas", "scikit-learn", "markdown"]:
        assert name in env


def test_readme_documents_conda_qt6_install_without_pip_dependencies():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "python 3.14" in readme
    assert "pyqt6" in readme
    assert "pip install -e . --no-deps" in readme
    assert "not `pyqt`" in readme


def test_packaging_metadata_is_modernized_for_a7():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "2.5.1"' in pyproject
    assert 'license = "MIT"' in pyproject
    assert 'license = { text = "MIT" }' not in pyproject
    assert '"Programming Language :: Python :: 3.14"' in pyproject


def test_numpy_compatibility_helper_no_longer_targets_numpy1():
    compat = (ROOT / "src" / "maxiv_exact" / "compat.py").read_text(encoding="utf-8")
    assert "np.trapezoid" in compat
    assert "np.trapz" not in compat
    assert 'getattr(np, "trapezoid"' not in compat
