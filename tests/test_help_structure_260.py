"""Navigation-level checks for the two active user Help documents."""
from pathlib import Path
import re

DOCS = Path(__file__).resolve().parents[1] / 'src' / 'maxiv_exact' / 'docs'


def _headings(filename):
    lines = (DOCS / filename).read_text(encoding='utf-8').splitlines()
    return [(len(m.group(1)), m.group(2).strip()) for line in lines if (m := re.match(r'^(#{1,6})\s+(.+)$', line))]


def _parent_of(headings, title):
    index = next(i for i, (_, name) in enumerate(headings) if name == title)
    level = headings[index][0]
    return next((name for heading_level, name in reversed(headings[:index]) if heading_level < level), None)


def test_workflows_have_unambiguous_topic_parents():
    headings = _headings('usage_workflows.md')
    assert _parent_of(headings, 'Inspect other 1D HDF5 datasets (metadata and diagnostics)') == 'Load and inspect data'
    assert _parent_of(headings, 'First map: measured ROI spectra (no fitting needed)') == 'Analyze fluorescence-detector maps (FL Map Analysis)'
    assert _parent_of(headings, 'Fit fluorescence peaks across the map') == 'Analyze fluorescence-detector maps (FL Map Analysis)'
    assert _parent_of(headings, 'SA Correction (experimental)') is None
    top = [title for level, title in headings if level == 1]
    assert top[-1] == 'Troubleshooting and a safe first workflow'
    assert len(top) == len(set(top))


def test_control_headings_and_transfer_boundaries():
    headings = _headings('usage_controls.md')
    names = [name.replace('**', '') for _, name in headings]
    a,b,d = map(names.index, ['Match pre-edge', 'FY Analysis', 'Pass'])
    assert a < b < d
    assert headings[b][0] == headings[a][0] == headings[d][0] == 4
    text = (DOCS / 'usage_controls.md').read_text(encoding='utf-8')
    assert 'not** sent to XAS-specific Processed Data' in text
    assert 'How to? → Analyze fluorescence-detector maps (FL Map Analysis)' in text
