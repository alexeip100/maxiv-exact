"""Release-facing metadata and first-time-user Help placement."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_about_date_agrees_with_release_changelog():
    from maxiv_exact import __date__, __version__
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(r'^## (?:\[' + re.escape(__version__) + r'\] [–-] (\d{4}-\d{2}-\d{2})|' + re.escape(__version__) + r' — development build \d+ \((\d{4}-\d{2}-\d{2})\))$', changelog, re.M)
    assert match is not None
    assert __date__ == (match.group(1) or match.group(2))


def test_fy_analysis_help_in_processed_controls_order():
    content = (ROOT / 'src/maxiv_exact/docs/usage_controls.md').read_text(encoding='utf-8')
    section = content.split('## Processed Data tab\n', 1)[1].split('\n## ', 1)[0]
    assert section.count('#### **FY Analysis**') == 1
    assert section.index('#### **Match pre-edge**') < section.index('#### **FY Analysis**') < section.index('#### **Pass**')
    assert '**FL Map Analysis…**' in section
    assert 'How to? → Analyze fluorescence-detector maps (FL Map Analysis)' in section
