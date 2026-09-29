"""Help browser widget used by the Help menu."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import QMenu, QTextBrowser, QTextEdit


class HelpBrowser(QTextBrowser):
    """QTextBrowser with responsive wrapping and heading navigation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._help_anchors: list[tuple[int, str, str]] = []
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_help_context_menu)

    def setHtml(self, html: str) -> None:  # type: ignore[override]
        super().setHtml(html)
        try:
            import html as _html
            import re

            def _strip_tags(s: str) -> str:
                s = re.sub(r"<[^>]+>", "", s)
                return _html.unescape(s).strip()

            anchors: list[tuple[int, str, str]] = []
            # Current renderer uses ordinary paragraphs rather than native
            # h1-h3 tags because QTextBrowser otherwise applies an oversized
            # built-in heading scale. Keep support for legacy h tags too.
            for mh in re.finditer(
                r'<p[^>]*data-help-level="([123])"[^>]*data-help-anchor="([^"]*)"[^>]*>(.*?)</p>',
                html,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                level = int(mh.group(1))
                title = _strip_tags(mh.group(3))
                anchor = mh.group(2)
                if title and anchor:
                    anchors.append((level, title, anchor))
            if not anchors:
                for mh in re.finditer(
                    r"<h([123])[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</h\1>",
                    html,
                    flags=re.IGNORECASE | re.DOTALL,
                ):
                    level = int(mh.group(1))
                    title = _strip_tags(mh.group(3))
                    anchor = mh.group(2)
                    if title and anchor:
                        anchors.append((level, title, anchor))
            self._help_anchors = anchors
        except Exception:
            self._help_anchors = []

    def _show_help_context_menu(self, pos):
        try:
            from functools import partial
            menu = self.createStandardContextMenu()
            if self._help_anchors:
                nav = QMenu("Go to", menu)
                for level, title, anchor in self._help_anchors:
                    disp = ("    " + title) if level == 2 else title
                    nav.addAction(disp, partial(self.scrollToAnchor, anchor))
                if menu.actions():
                    first = menu.actions()[0]
                    menu.insertMenu(first, nav)
                    menu.insertSeparator(first)
                else:
                    menu.addMenu(nav)
            menu.exec(self.mapToGlobal(pos))
        except Exception:
            try:
                self.createStandardContextMenu().exec(self.mapToGlobal(pos))
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.setLineWrapColumnOrWidth(self.viewport().width())
        except Exception:
            pass
