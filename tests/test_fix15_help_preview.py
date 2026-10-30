from pathlib import Path

from maxiv_exact.utils.help_text import build_whats_new_markdown


ROOT = Path(__file__).resolve().parents[1]


def test_processed_help_names_fy_analysis_and_points_to_workflow():
    text = (ROOT / 'src/maxiv_exact/docs/usage_controls.md').read_text(encoding='utf-8')
    section = text.split('## Processed Data tab', 1)[1].split('## Plotted Data tab', 1)[0]
    assert '#### **FY Analysis**' in section
    assert 'FL Map Analysis…' in section
    assert 'How to? → Analyze fluorescence-detector maps (FL Map Analysis)' in section


def test_260_whats_new_is_release_focused():
    text, latest = build_whats_new_markdown(current_version='2.6.1', max_versions=5)
    latest_section = text.split('### 2.6.0 — 2026-10-30', 1)[1].split('---', 1)[0]
    assert latest == '2.6.1'
    assert '#### Added' in latest_section
    assert 'FL Map Analysis' in latest_section
    assert 'ROI' in latest_section
    assert '#### Changed' not in latest_section
    assert '#### Fixed' not in latest_section
    assert 'development preview' not in text
    assert '### 2.5.2' in text
