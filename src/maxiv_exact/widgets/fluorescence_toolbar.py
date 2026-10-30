"""Compact Matplotlib toolbar coordinate readout for fluorescence plots."""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT


_COORDS = re.compile(r'^\s*\(x,\s*y\)\s*=\s*\(([^,]+),\s*([^\)]+)\)\s*$')


def single_line_coordinates(message: str) -> str:
    """Present Matplotlib map x/y and image intensity on one unwrapped line."""
    parts = [part.strip() for part in message.splitlines() if part.strip()]
    if not parts:
        return ''
    match = _COORDS.fullmatch(parts[0])
    if match:
        result = f'X: {match.group(1)}   Y: {match.group(2)}'
        if len(parts) > 1:
            intensity = parts[1].strip('[] ')
            result += f'   Z: {intensity}'
        return result
    return '   '.join(parts)


class FluorescenceToolbar(NavigationToolbar2QT):
    """Retain standard Matplotlib actions, with a compact coordinate label."""

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        if self.coordinates:
            self.locLabel.setWordWrap(False)
            self.locLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.locLabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_message(self, message):
        super().set_message(single_line_coordinates(message))
