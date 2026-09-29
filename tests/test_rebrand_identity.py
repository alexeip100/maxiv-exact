from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "maxiv_exact"


def test_exact_distribution_namespace_and_launchers():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "maxiv-exact"' in pyproject
    assert 'exact = "maxiv_exact.app:main"' in pyproject
    assert 'maxiv-exact = "maxiv_exact.app:main"' in pyproject
    assert 'flexpes-nexafs = "maxiv_exact.app:main"' in pyproject
    assert (ROOT / "src" / "maxiv_exact").is_dir()
    assert not (ROOT / "src" / "flexpes_nexafs").exists()


def test_exact_application_identity_is_visible_in_ui_and_about():
    ui = (PKG / "ui.py").read_text(encoding="utf-8")
    core = (PKG / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    app = (PKG / "app.py").read_text(encoding="utf-8")
    assert 'self.setWindowTitle("EXACT")' in ui
    assert 'Exploration of X-ray Absorption: Characterization and Treatment' in core
    assert '"MAXIV.EXACT"' in app
    assert 'app.setApplicationName("EXACT")' in app


def test_exact_icon_resources_and_build_entry_are_rebranded():
    assets = PKG / "assets"
    for name in [
        "exact_icon.ico", "exact_icon.icns",
        "exact_icon_64.png", "exact_icon_128.png",
        "exact_icon_256.png", "exact_icon_512.png",
    ]:
        assert (assets / name).is_file(), name
    spec = (ROOT / "MAXIV-EXACT.spec").read_text(encoding="utf-8")
    assert "run_exact.py" in spec
    assert "run_flexpes.py" not in spec


def test_legacy_namespace_only_remains_for_settings_migration():
    occurrences = []
    for source in PKG.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        if "flexpes_nexafs" in text:
            occurrences.append(source.relative_to(ROOT).as_posix())
    assert occurrences == ["src/maxiv_exact/channel_setup.py"]
