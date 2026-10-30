from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_bundled_mathjax_and_license():
    base = ROOT / "src/maxiv_exact/resources/mathjax"
    assert (base / "tex-svg-full.js").stat().st_size > 1_000_000
    assert (base / "LICENSE-MathJax.txt").is_file()

def test_webengine_dependency_and_source():
    config = (ROOT / "pyproject.toml").read_text()
    src = (ROOT / "src/maxiv_exact/widgets/self_absorption_dialog.py").read_text()
    assert "PyQt6-WebEngine" in config
    assert "QWebEngineView" in src and "_render_mathjax_help" in src
    assert "tex-svg-full.js" in src
    assert "cdn.jsdelivr" not in src
