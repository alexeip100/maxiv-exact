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


def test_251_user_facing_help_covers_new_workflow_controls():
    controls = (DOCS / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (DOCS / "usage_workflows.md").read_text(encoding="utf-8")
    joined = controls + "\n" + workflows
    for topic in [
        "Settings (⚙)",
        "System, Light, or Dark",
        "Check all",
        "Uncheck all",
        "returns to the **Raw Data** tab",
        "drag and drop",
    ]:
        assert topic in joined


def test_reference_help_is_in_active_help_documents_and_toc_level():
    controls = (DOCS / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (DOCS / "usage_workflows.md").read_text(encoding="utf-8")
    assert "# X-ray Reference" in controls
    assert "Chantler / XrayDB" in controls
    assert "f₁ = Z + f′" in controls
    assert "# Inspect built-in X-ray reference data" in workflows


def test_reference_help_renders_through_actual_help_loader():
    from maxiv_exact.utils.help_text import get_usage_html
    controls_html = get_usage_html("usage_controls.md")
    workflows_html = get_usage_html("usage_workflows.md")
    assert "X-ray Reference" in controls_html
    assert "Chantler / XrayDB" in controls_html
    assert "Inspect built-in X-ray reference data" in workflows_html


def test_reference_help_explains_attenuation_decomposition_and_mu_compare():
    controls = (DOCS / "usage_controls.md").read_text(encoding="utf-8")
    workflows = (DOCS / "usage_workflows.md").read_text(encoding="utf-8")
    for token in (
        "How total attenuation is composed",
        r"\mu_{\mathrm{total}}",
        r"\mu_{\mathrm{coh}}",
        r"\mu_{\mathrm{incoh}}",
        "Rayleigh",
        "Compton",
        "μ compare",
    ):
        assert token in controls or token in workflows


def test_help_renderer_converts_tex_style_equations_to_embedded_images():
    from maxiv_exact.utils.help_text import get_usage_html

    html = get_usage_html("usage_controls.md")
    assert "data:image/svg+xml;base64" in html
    assert "EXACTMATH" not in html
    assert "$$" not in html


def test_help_explains_unavailable_coherent_channel():
    text = Path("src/maxiv_exact/docs/usage_controls.md").read_text(encoding="utf-8")
    assert "not present in the downloaded Chantler table used by EXACT" in text
    assert "cannot be selected or plotted directly" in text
    assert "μ total − μ photo − μ incoh" in text



def test_help_search_selection_is_high_contrast_yellow():
    mixin = (ROOT / "src" / "maxiv_exact" / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    assert mixin.count("selection-background-color: #ffeb3b") >= 2
    assert mixin.count("selection-color: #111111") >= 2
