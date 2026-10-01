from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_contains_user_facing_core_sections():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in [
        "# MAX IV EXACT",
        "## Main capabilities",
        "## Supported data format",
        "## Installation",
        "## Starting EXACT",
        "## Quick start",
        "## Channel profiles and detector roles",
        "## X-ray reference data, reference spectra, and decomposition",
        "## Testing",
        "## Author",
        "## License",
    ]:
        assert heading in text


def test_readme_mentions_exact_identity_and_compatibility_launcher():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "EXACT — Exploration of X-ray Absorption: Characterization and Treatment" in text
    assert "maxiv-exact" in text
    assert "flexpes-nexafs" in text
    assert "python -m maxiv_exact" in text


def test_readme_release_installation_is_complete_and_copy_friendly():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "h5py" in text
    assert "Releases" in text
    assert "Latest" in text
    assert "bottom of the release page" in text
    assert "Assets" in text
    assert "maxiv_exact-2.5.2-py3-none-any.whl" in text
    # Commands intended as separate shell inputs must not share one fenced block.
    assert "conda create -n exact" in text
    assert "```\n\nActivate the environment" in text
    assert "conda activate exact" in text


def test_release_changelogs_match_and_include_252():
    root_log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    help_log = (ROOT / "src" / "maxiv_exact" / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert root_log == help_log
    assert "## [2.5.2] – 2026-10-01" in root_log
    for heading in ["### Added", "### Fixed", "### Changed"]:
        assert heading in root_log.split("## [2.5.1]", 1)[0]
