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
        "## Reference library and decomposition",
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
