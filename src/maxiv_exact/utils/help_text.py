"""Utilities for loading and rendering packaged help text.

Help files are shipped under docs/ (for example usage_controls.md).
"""

from __future__ import annotations

from pathlib import Path
import re


def _pkg_root_path() -> Path | None:
    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        return None


def _read_help_markdown(md_filename: str = "usage_controls.md") -> str | None:
    root = _pkg_root_path()
    if not root:
        return None
    md_path = root / "docs" / md_filename
    try:
        return md_path.read_text(encoding="utf-8")
    except Exception:
        return None


def _format_changelog_subheading_html(title: str) -> str:
    """Return compact HTML for small changelog labels such as Added/Fixed/Changed."""
    import html

    safe = html.escape(str(title or "").strip())
    if not safe:
        return ""
    return (
        '<div class="changelog-subheading" '
        'style="margin:10px 0 4px 0; padding:3px 8px; '
        'border-left:4px solid #8a8a8a; background-color:#f2f2f2; '
        'font-weight:bold;">'
        f'{safe}</div>'
    )


def _style_whats_new_html(html_text: str) -> str:
    """Normalize What's New subsection headings across markdown/fallback renderers."""
    import re

    def repl(match):
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        return _format_changelog_subheading_html(title)

    styled = re.sub(r"<h4[^>]*>(.*?)</h4>", repl, html_text or "", flags=re.I | re.S)
    styled = re.sub(r"<h5[^>]*>(.*?)</h5>", repl, styled, flags=re.I | re.S)
    styled = re.sub(r"<h6[^>]*>(.*?)</h6>", repl, styled, flags=re.I | re.S)
    return styled


def _basic_md_to_html(md: str) -> str:
    """Small Markdown-to-HTML fallback used if the markdown package is absent.

    It supports headings, unordered/ordered lists, simple paragraphs, bold,
    italic, and inline code. It also adds ids to H1/H2 headings for the TOC.
    """
    import html
    import re

    text = html.escape(md)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"\[([^]]+)\]\((#[^)]+)\)", r'<a href="\2">\1</a>', text)

    def _slugify(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"[\s_]+", "-", s)
        s = re.sub(r"[^a-z0-9\-]+", "", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "section"

    used_ids: dict[str, int] = {}
    out: list[str] = []
    para: list[str] = []
    in_ul = False
    in_ol = False

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append(f"<p>{' '.join(para).strip()}</p>")
            para = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush_para()
            continue

        if line.startswith("# ") or line.startswith("## ") or line.startswith("### ") or line.startswith("#### "):
            flush_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if in_ol:
                out.append("</ol>"); in_ol = False
            if line.startswith("# "):
                level, title = 1, line[2:].strip()
            elif line.startswith("## "):
                level, title = 2, line[3:].strip()
            elif line.startswith("### "):
                level, title = 3, line[4:].strip()
            else:
                level, title = 4, line[5:].strip()
            anchor = _slugify(title)
            used_ids[anchor] = used_ids.get(anchor, 0) + 1
            if used_ids[anchor] > 1:
                anchor = f"{anchor}-{used_ids[anchor]}"
            out.append(f'<h{level} id="{anchor}">{title}</h{level}>')
            continue

        if line in {"---", "***", "___"}:
            flush_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if in_ol:
                out.append("</ol>"); in_ol = False
            out.append("<hr>")
            continue

        if line.startswith("&gt; "):
            flush_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if in_ol:
                out.append("</ol>"); in_ol = False
            out.append(f"<blockquote>{line[5:].strip()}</blockquote>")
            continue

        if line.startswith("- ") or line.startswith("* "):
            flush_para()
            if in_ol:
                out.append("</ol>"); in_ol = False
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{line[2:].strip()}</li>")
            continue

        if any(line.startswith(f"{n}. ") for n in range(1, 10)):
            flush_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if not in_ol:
                out.append("<ol>"); in_ol = True
            dot = line.find('.')
            out.append(f"<li>{line[dot+1:].strip()}</li>")
            continue

        para.append(line)

    flush_para()
    if in_ul:
        out.append("</ul>")
    if in_ol:
        out.append("</ol>")
    return "\n".join(out)


def _help_palette_colors() -> dict[str, str]:
    """Return Qt-palette colours for Help rich text.

    QTextBrowser does not reliably resolve every palette(...) token in inline
    HTML styles, so resolve the active application palette to concrete colours
    before building the document.
    """
    defaults = {
        "text": "#202020",
        "base": "#ffffff",
        "alternate": "#f2f2f2",
        "mid": "#9a9a9a",
        "highlight": "#2f83c5",
        "link": "#2f83c5",
    }
    try:
        from PyQt6 import QtGui, QtWidgets
        app = QtWidgets.QApplication.instance()
        if app is None:
            return defaults
        pal = app.palette()
        role = QtGui.QPalette.ColorRole
        return {
            "text": pal.color(role.Text).name(),
            "base": pal.color(role.Base).name(),
            "alternate": pal.color(role.AlternateBase).name(),
            "mid": pal.color(role.Mid).name(),
            "highlight": pal.color(role.Highlight).name(),
            "link": pal.color(role.Link).name(),
        }
    except Exception:
        return defaults


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "#000000").lstrip("#")
    if len(value) != 6:
        value = "000000"
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def _blend_hex(a: str, b: str, fraction_b: float) -> str:
    """Blend two #RRGGBB colours for theme-aware Help accents."""
    fraction_b = max(0.0, min(1.0, float(fraction_b)))
    ar, ag, ab = _hex_rgb(a)
    br, bg, bb = _hex_rgb(b)
    vals = [
        round(x * (1.0 - fraction_b) + y * fraction_b)
        for x, y in ((ar, br), (ag, bg), (ab, bb))
    ]
    return "#" + "".join(f"{v:02x}" for v in vals)


def _relative_luma(color: str) -> float:
    r, g, b = _hex_rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _help_css(base_px: int = 17) -> str:
    """Return shared semantic styling for both Help documents."""
    base_px = max(8, min(28, int(base_px)))
    h1_px = min(29, max(base_px + 6, 20))
    h2_px = min(25, max(base_px + 2, 16))
    h3_px = min(24, max(base_px + 1, 15))
    h4_px = min(23, max(base_px, 14))
    c = _help_palette_colors()
    dark_theme = _relative_luma(c["base"]) < 0.5
    accent_seed = c["link"] or c["highlight"]
    # Pull the palette accent toward the current text colour. This makes it
    # slightly deeper in Light mode and noticeably lighter in Dark mode.
    accent = _blend_hex(accent_seed, c["text"], 0.30 if dark_theme else 0.18)
    accent_soft = _blend_hex(c["base"], accent, 0.16 if dark_theme else 0.10)
    accent_faint = _blend_hex(c["base"], accent, 0.08 if dark_theme else 0.055)
    css = f"""
<style>
body {{
  color: {c['text']};
  line-height: 1.42;
  margin: 0.45em 0.65em 1.2em 0.65em;
}}
h1 {{
  font-size: {h1_px}px;
  font-weight: 700;
  color: {c['text']};
  background-color: {accent_soft};
  margin: 3.20em 0 0.55em 0;
  padding: 0.22em 0.38em 0.26em 0.38em;
  border-bottom: 2px solid {accent};
}}
h2 {{
  font-size: {h2_px}px;
  font-weight: 700;
  color: {accent};
  margin: 1.20em 0 0.42em 0;
  padding: 0.12em 0 0.18em 0.42em;
  border-left: 0.22em solid {accent};
  border-bottom: 1px solid {c['mid']};
}}
h3 {{ font-size: {h3_px}px; font-weight: 600; color: {c['text']}; margin: 0.95em 0 0.28em 0; padding: 0.05em 0 0.05em 0.42em; border-left: 0.12em solid {accent}; }}
h4 {{ font-size: {h4_px}px; font-weight: 600; color: {c['text']}; margin: 0.72em 0 0.22em 0; }}
p {{ margin: 0.38em 0 0.62em 0; }}
ul, ol {{ margin-top: 0.25em; margin-bottom: 0.68em; }}
li {{ margin: 0.16em 0; }}
hr {{ border: 0; border-top: 1px solid {c['mid']}; margin: 1.25em 0; }}
a {{ color: {accent}; text-decoration: none; font-weight: 600; }}
blockquote {{
  margin: 0.72em 0 0.82em 0;
  padding: 0.48em 0.72em;
  background-color: {accent_faint};
  border-left: 0.28em solid {accent};
  color: {c['text']};
}}
code {{
  font-size: 0.94em;
  color: {c['text']};
  background-color: {c['alternate']};
  padding: 0.08em 0.22em;
}}
table {{ border-collapse: collapse; margin: 0.55em 0 0.85em 0; font-size: 0.92em; }}
th {{ font-weight: 700; color: {c['text']}; background-color: {c['alternate']}; }}
th, td {{ border: 1px solid {c['mid']}; padding: 0.30em 0.48em; vertical-align: top; }}
</style>
"""
    return css


def get_usage_html(md_filename: str = "usage_controls.md", base_px: int = 17) -> str:
    """Return styled help content as HTML from a Markdown file under docs/."""
    md = _read_help_markdown(md_filename)
    if not md:
        return "<p><b>Help file not found.</b></p>"
    try:
        import markdown  # type: ignore
        content = markdown.markdown(
            md, extensions=["tables", "fenced_code", "sane_lists", "toc"]
        )
    except Exception:
        content = _basic_md_to_html(md)
    # Qt's rich-text parser does not consistently honour font sizes from a
    # document-level <style> block for h1-h4. Add the essential typography
    # inline so the displayed hierarchy matches the selected base font.
    import re

    base_px = max(8, min(28, int(base_px)))
    help_colors = _help_palette_colors()
    dark_theme = _relative_luma(help_colors["base"]) < 0.5
    accent_seed = help_colors["link"] or help_colors["highlight"]
    accent = _blend_hex(accent_seed, help_colors["text"], 0.30 if dark_theme else 0.18)
    accent_soft = _blend_hex(help_colors["base"], accent, 0.16 if dark_theme else 0.10)
    heading_styles = {
        1: (min(29, max(base_px + 6, 20)), "3.20em", "700", help_colors["text"]),
        2: (min(27, max(base_px + 3, 18)), "1.45em", "700", accent),
        3: (min(26, max(base_px + 2, 17)), "1.05em", "600", help_colors["text"]),
        4: (min(25, max(base_px + 1, 16)), "0.80em", "600", help_colors["text"]),
    }

    def _inline_heading(match):
        level = int(match.group(1))
        attrs = match.group(2) or ""
        body = match.group(3)
        size, margin_top, weight, color = heading_styles[level]
        id_match = re.search(r'\sid=["\']([^"\']+)["\']', attrs, flags=re.I)
        anchor = id_match.group(1) if id_match else ""
        anchor_html = f'<a name="{anchor}"></a>' if anchor else ""
        # QTextBrowser imposes a large built-in scale on h1-h4 even when an
        # inline font size is supplied. Render semantic headings as ordinary
        # paragraphs, which honour explicit sizes reliably, and keep their
        # level/anchor as data used by the contents tree.
        extra_style = ""
        if level == 1:
            extra_style = (
                f"background-color:{accent_soft}; "
                "padding:0.24em 0.42em 0.28em 0.42em; "
                f"border-bottom:2px solid {accent};"
            )
        elif level == 2:
            extra_style = (
                "padding:0.10em 0 0.14em 0.42em; "
                f"border-left:0.22em solid {accent}; "
                f"border-bottom:1px solid {help_colors['mid']};"
            )
        elif level == 3:
            extra_style = (
                "padding-left:0.42em; "
                f"border-left:0.12em solid {accent};"
            )
        style = (
            f"font-size:{size}px; font-weight:{weight}; color:{color}; "
            f"margin-top:{margin_top}; margin-bottom:0.45em; {extra_style}"
        )
        return (
            f'<p data-help-level="{level}" data-help-anchor="{anchor}" '
            f'style="{style}">{anchor_html}{body}</p>'
        )

    content = re.sub(
        r"<h([1-4])([^>]*)>(.*?)</h\1>",
        _inline_heading,
        content,
        flags=re.I | re.S,
    )
    return _help_css(base_px) + content


# ---------------------------------------------------------------------------
# What's new / changelog rendering
# ---------------------------------------------------------------------------

def _parse_changelog_sections(md: str):
    """Parse Keep-a-Changelog style sections.

    Expected headings:
      ## [Unreleased]
      ## [2.3.8] – YYYY-MM-DD

    Returns:
      (unreleased_block, version_blocks) where version_blocks is a list of
      (version_str, date_str, block_md) in the order they appear in the file.
    """
    import re

    # Split into blocks starting at "## ["
    m = re.search(r"^## \[", md, flags=re.M)
    if not m:
        return None, []

    rest = md[m.start():]

    starts = []
    for match in re.finditer(r"^## \[(?P<tag>[^\]]+)\]\s*[-–—]\s*(?P<date>\d{4}-\d{2}-\d{2}).*$", rest, flags=re.M):
        starts.append((match.group("tag").strip(), match.group("date").strip(), match.start()))

    # Also catch "[Unreleased]" without date
    for match in re.finditer(r"^## \[(?P<tag>Unreleased)\].*$", rest, flags=re.M | re.I):
        # ensure it's not already in starts
        tag = match.group("tag").strip()
        if not any(t.lower() == tag.lower() and s == match.start() for t, _, s in starts):
            starts.append((tag, "", match.start()))

    # sort by position
    starts.sort(key=lambda x: x[2])

    blocks = []
    for i, (tag, d, start) in enumerate(starts):
        end = starts[i+1][2] if i+1 < len(starts) else len(rest)
        blocks.append((tag, d, rest[start:end].strip()))

    unreleased = None
    versions = []
    for tag, d, block in blocks:
        if tag.lower() == "unreleased":
            unreleased = block
        else:
            versions.append((tag, d, block))

    return unreleased, versions


def _semver_key(v: str):
    """Return a sortable key for versions like '2.3.8'."""
    import re
    s = (v or "").strip()
    if s.lower().startswith("v"):
        s = s[1:]
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", s)
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


def build_whats_new_markdown(current_version: str, max_versions: int = 5) -> tuple[str, str]:
    """Build a markdown document for 'What's new' from docs/CHANGELOG.md.

    Returns:
      (md, latest_version_str)
    """
    md = _read_help_markdown("CHANGELOG.md")
    if not md:
        return ("# What's new\n\n**Changelog could not be loaded.**\n", "")

    _unrel, versions = _parse_changelog_sections(md)
    if not versions:
        return ("# What's new\n\n**No released versions found in changelog.**\n", "")

    # Sort by semver desc when possible, otherwise keep file order
    versions_sorted = []
    versions_unparsable = []
    for tag, d, block in versions:
        key = _semver_key(tag)
        if key is None:
            versions_unparsable.append((tag, d, block))
        else:
            versions_sorted.append((key, tag, d, block))

    versions_sorted.sort(key=lambda x: x[0], reverse=True)
    merged = [(tag, d, block) for _, tag, d, block in versions_sorted] + versions_unparsable

    # User-facing What's new should describe public releases, not the internal
    # alpha/RC sequence used to prepare them.  When the installed version is a
    # stable release, hide pre-release changelog entries (a/b/rc tags) while
    # retaining them in the full packaged changelog.
    current_is_stable = re.fullmatch(r"v?\d+\.\d+\.\d+", str(current_version).strip()) is not None
    if current_is_stable:
        prerelease_tag = re.compile(r"^v?\d+\.\d+\.\d+(?:a|b|rc)\d+", re.I)
        merged = [item for item in merged if not prerelease_tag.match(item[0])]

    top = merged[:max_versions]

    latest_version = top[0][0] if top else ""

    out = []
    out.append("# What's new")
    out.append("These are the latest changes recorded in the packaged changelog.")
    out.append("")

    # Create version headings as H3 so TOC shows versions (H3 is used by the Usage TOC style).
    for idx, (tag, d, block) in enumerate(top):
        title = f"{tag} — {d}" if d else tag
        out.append(f"### {title}")
        out.append("")
        # Remove the leading '## [x] ...' line inside block and demote '###' to '####'
        lines = block.splitlines()
        if lines and lines[0].startswith("## "):
            lines = lines[1:]
        content = "\n".join(lines).strip()
        # Demote headings inside each version block to avoid flooding the TOC.
        # Do it consistently for all same-level headings (e.g. "### Fixed" and "### Changed")
        # so equal-level headings render with equal font size.
        content = re.sub(r"^###\s+", "#### ", content, flags=re.M)
        content = re.sub(r"^##\s+", "#### ", content, flags=re.M)
        out.append(content)
        out.append("")
        if idx != len(top) - 1:
            out.append("---")
            out.append("")
    return ("\n".join(out).strip() + "\n", latest_version)


def get_whats_new_payload(current_version: str, max_versions: int = 5) -> tuple[str, str]:
    """Return (html, latest_version) for the What's new window."""
    md, latest = build_whats_new_markdown(current_version=current_version, max_versions=max_versions)
    try:
        import markdown
        html = markdown.markdown(md, extensions=["tables","fenced_code","sane_lists","toc"])  # type: ignore
    except Exception:
        html = _basic_md_to_html(md)
    html = _style_whats_new_html(html)
    return html, latest
