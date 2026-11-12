from pathlib import Path

from maxiv_exact import __version__
from maxiv_exact.utils.help_text import build_whats_new_markdown

ROOT = Path(__file__).resolve().parents[1]

def test_fluorescence_map_default_and_reset_are_terrain():
    source = (ROOT / "src/maxiv_exact/widgets/fluorescence_map_dialog.py").read_text(encoding="utf-8")
    assert source.count("self._colormap='terrain'") == 2
    assert "self._colormap='viridis'" not in source

def test_release_metadata_and_whats_new():
    markdown, latest = build_whats_new_markdown(current_version=__version__)
    assert latest == __version__
    historical = markdown.split("### 2.6.1 — 2026-10-30", 1)[1].split("---", 1)[0]
    assert "#### Changed" in historical and "#### Fixed" in historical
    assert "terrain" in historical and "Processed Data" in historical and "Pass" in historical
