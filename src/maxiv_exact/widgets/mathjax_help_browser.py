"""Offline MathJax document viewer for the main EXACT Help.

The table of contents and controls remain native Qt widgets in mixin_core.
This widget replaces only the content surface of the main usage/how-to Help.
"""
from __future__ import annotations

import html
import json
import re
from importlib.resources import files
from pathlib import Path

import markdown
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage

from ..utils.help_text import _read_help_markdown


class MathJaxHelpBrowser(QWebEngineView):
    def __init__(self, md_filename: str, parent=None, base_px: int = 17, markdown_source: str | None = None):
        super().__init__(parent)
        self.md_filename = md_filename
        self._markdown_source = markdown_source
        self._base_px = int(base_px)
        self._help_anchors: list[tuple[int, str, str]] = []
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._load_document()

    def _load_document(self) -> None:
        source = self._markdown_source if self._markdown_source is not None else _read_help_markdown(self.md_filename)
        if source is None:
            source = '# Help unavailable\nThe packaged Markdown file could not be opened.'
        tokens: list[tuple[str, str]] = []

        def store(expr: str, display: bool):
            token = f'EXACTHELPFORMULA{len(tokens):06d}TOKEN'
            tokens.append((token, (r'\[' + expr.strip() + r'\]') if display else (r'\(' + expr.strip() + r'\)')))
            return token

        source = re.sub(r'```(?:tex|latex)\s*\n(.*?)\n```', lambda m:'\n\n'+store(m.group(1), True)+'\n\n', source, flags=re.S|re.I)
        source = re.sub(r'\$\$(.*?)\$\$', lambda m:'\n\n'+store(m.group(1), True)+'\n\n', source, flags=re.S)
        source = re.sub(r'\\\[(.*?)\\\]', lambda m:'\n\n'+store(m.group(1), True)+'\n\n', source, flags=re.S)
        source = re.sub(r'\\\((.*?)\\\)', lambda m:store(m.group(1), False), source, flags=re.S)
        # A single-dollar math span must not eat a double-dollar display block.
        source = re.sub(r'(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)',lambda m:store(m.group(1),False),source)
        rendered = markdown.markdown(source,extensions=['tables','fenced_code','sane_lists','toc'])
        # Legacy main-Help prose uses code spans for mathematical variable names.
        # Convert *only* well-recognized symbol names to inline TeX; preserve
        # genuine code, paths and UI labels as code.
        def _math_code(match):
            value = html.unescape(match.group(1)).strip()
            # Legacy docs use backticks for variable names, including the
            # user-visible 'μ photo' spelling, as well as true program code.
            # Render only recognized mathematical terms; leave everything
            # else (commands, identifiers, paths) in monospace code spans.
            if re.fullmatch(r'f_[12](?:/f_[12])?|f[₁₂](?:/f[₁₂])?', value):
                expr = value.translate(str.maketrans({'₁':'1','₂':'2'}))
                expr = re.sub(r'f_?([12])', r'f_{\1}', expr)
            elif re.fullmatch(r'(?:[μ\u03bc]|mu)[_ ](?:photo|coh|incoh|total|tot|bg)(?:\s*[+−-]\s*(?:[μ\u03bc]|mu)[_ ](?:photo|coh|incoh|total|tot|bg))*',value):
                expr = re.sub(r'(?:μ|mu)[_ ]([A-Za-z]+)', lambda m:r'\mu_{\mathrm{'+m.group(1)+r'}}', value)
                expr = expr.replace('−', '-')
            else:
                return match.group(0)
            return html.escape(r'\('+expr+r'\)', quote=False)
        rendered = re.sub(r'<code>([^<>]+)</code>', _math_code, rendered)
        for token, expr in tokens:
            rendered=rendered.replace(token,html.escape(expr,quote=False))
        self._help_anchors=[]
        for match in re.finditer(r'<h([123])\b([^>]*)>(.*?)</h\1>',rendered,flags=re.I|re.S):
            anchor=re.search(r'\bid=["\']([^"\']+)',match.group(2))
            title=html.unescape(re.sub(r'<[^>]*>','',match.group(3))).strip()
            if anchor and title:
                self._help_anchors.append((int(match.group(1)),title,anchor.group(1)))
        font=self._base_px
        document='''<!doctype html><html><head><meta charset="utf-8">
        <style>html{scroll-behavior:auto}body{font-family:Arial,sans-serif;font-size:FONTpx;line-height:1.45;margin:15px 21px;color:#202020}
        h1{font-size:1.4em;border-bottom:2px solid #577c9e;padding:.23em .3em;background:#edf3f8;margin-top:2em}
        h2{font-size:1.2em;color:#204e7c;border-left:4px solid #577c9e;padding-left:.4em;margin-top:1.5em}
        h3{font-size:1.12em;color:#204e7c;border-left:4px solid #577c9e;padding-left:.4em;margin-top:1.4em}h4{font-size:1em;font-weight:700;background:#f1f4f7;border-left:3px solid #9aa9b7;padding:3px 8px}p,li{line-height:1.45}code,pre{font-family:Consolas,monospace}
        code{background:#f2f2f2;padding:0 .15em}pre{overflow-x:auto;background:#f5f5f5;padding:9px}
        table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:5px 9px}
        mjx-container[display="true"]{margin:1.05em 0!important;overflow-x:auto;overflow-y:hidden}
        a{color:#185c9c}::selection{background:#ffeb3b;color:#111111}h1,h2,h3{scroll-margin-top:12px}</style>
        <script>window.MathJax={tex:{inlineMath:[['\\\\(','\\\\)']],displayMath:[['\\\\[','\\\\]']],processEscapes:true},svg:{fontCache:'local'},options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};</script>
        <script src="tex-svg-full.js"></script></head><body>BODY</body></html>'''.replace('FONT',str(font)).replace('BODY',rendered)
        base=Path(str(files('maxiv_exact').joinpath('resources/mathjax')))
        self.setHtml(document,QUrl.fromLocalFile(str(base)+'/'))

    def scrollToAnchor(self, anchor: str) -> None:
        arg=json.dumps(str(anchor))
        self.page().runJavaScript(f'(function(){{let e=document.getElementById({arg});if(e)e.scrollIntoView({{block:"start"}});}})()')

    def set_base_font(self, size: int) -> None:
        # Change CSS in situ: preserves scroll position and MathJax processing.
        self._base_px=int(size)
        self.page().runJavaScript(f'document.body.style.fontSize={json.dumps(str(self._base_px)+"px")};')

    def find_help(self, query: str, backward: bool, on_result=None) -> None:
        flags=QWebEnginePage.FindFlag.FindBackward if backward else QWebEnginePage.FindFlag(0)
        self.findText(query,flags, (lambda result: on_result(bool(result.numberOfMatches())) if on_result else None))

    def _context_menu(self,pos):
        menu=QMenu(self)
        nav=menu.addMenu('Go to')
        for level,title,anchor in self._help_anchors:
            action=nav.addAction(('    ' if level>1 else '')+title)
            action.triggered.connect(lambda _checked=False,a=anchor:self.scrollToAnchor(a))
        menu.addSeparator()
        menu.addAction('Copy',lambda:self.page().triggerAction(QWebEnginePage.WebAction.Copy))
        menu.addAction('Select All',lambda:self.page().triggerAction(QWebEnginePage.WebAction.SelectAll))
        menu.exec(self.mapToGlobal(pos))
