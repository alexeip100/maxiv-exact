from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "src" / "maxiv_exact" / "docs"


def test_active_help_keeps_existing_exact_topics_and_adds_first_time_orientation():
    controls = (DOCS / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (DOCS / "usage_workflows.md").read_text(encoding="utf-8")

    # Established EXACT topics remain present.
    for topic in ["Group BG", "Match pre-edge", "Sum up?", "Load reference", "MCR-ALS"]:
        assert topic in controls or topic in workflows

    # First-time-user orientation is explicit rather than implied.
    for topic in [
        "First-time orientation",
        "Processing controls versus display controls",
        "Understand the processing order",
        "Choose I₀ normalization sensibly",
        "A safe complete workflow for a first-time user",
    ]:
        assert topic in controls or topic in workflows


def test_active_help_uses_exact_branding():
    controls = (DOCS / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (DOCS / "usage_workflows.md").read_text(encoding="utf-8")
    joined = controls + "\n" + workflows
    assert "MAX IV EXACT" in joined
    assert "opened EXACT" in joined
    assert "FlexPES‑NEXAFS" not in joined
    assert "FlexPES-NEXAFS" not in joined


def test_help_renderer_is_palette_aware_like_panda_baseline():
    helper = (ROOT / "src" / "maxiv_exact" / "utils" / "help_text.py").read_text(encoding="utf-8")
    mixin = (ROOT / "src" / "maxiv_exact" / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    assert "def _help_palette_colors" in helper
    assert "def _blend_hex" in helper
    assert "palette(alternate-base)" in mixin
    assert "palette(link)" in mixin
    assert "QBrush(QColor(" not in mixin
