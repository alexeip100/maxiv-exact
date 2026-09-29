from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QWidget


class BusySpinner(QWidget):
    """Small indeterminate circular activity indicator."""

    def __init__(self, parent=None, diameter=26, line_width=3):
        super().__init__(parent)
        self._angle = 0
        self._diameter = int(diameter)
        self._line_width = int(line_width)
        self.setFixedSize(self._diameter, self._diameter)
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._advance)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
        self.show()
        self.update()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _advance(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        side = min(self.width(), self.height())
        margin = self._line_width + 2
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        base = self.palette().mid().color()
        active = self.palette().highlight().color()

        base_pen = QPen(base, self._line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        active_pen = QPen(active, self._line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(active_pen)
        painter.drawArc(rect, int(-self._angle * 16), int(105 * 16))
