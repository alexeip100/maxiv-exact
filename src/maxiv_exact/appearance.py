from __future__ import annotations

"""Application-level appearance preferences for EXACT.

The settings are deliberately small: color theme and an accessibility-oriented
UI font enlargement. Plot/figure fonts remain controlled by Matplotlib.
"""

from dataclasses import dataclass
from enum import Enum

from PyQt6 import QtCore, QtGui, QtWidgets

from .ui_metrics import UiMetrics, metrics_for_font_offset

SETTINGS_ORGANIZATION = "MAX IV"
SETTINGS_APPLICATION = "EXACT"
SETTINGS_GROUP = "appearance"
BASELINE_FONT_INCREMENT = 2
ALLOWED_FONT_OFFSETS = (0, 1, 2)


class UiTheme(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class AppearanceConfig:
    theme: UiTheme = UiTheme.SYSTEM
    font_offset_pt: int = 0


_BASE_FONT: QtGui.QFont | None = None
_SYSTEM_PALETTE: QtGui.QPalette | None = None



class ExactCheckStyle(QtWidgets.QProxyStyle):
    """Fusion proxy with explicit high-contrast checkbox painting in Dark mode."""

    def __init__(self, base_style: str = "Fusion") -> None:
        super().__init__(base_style)
        self.dark_mode = False

    def drawPrimitive(self, element, option, painter, widget=None):  # noqa: N802
        checkbox_elements = {
            QtWidgets.QStyle.PrimitiveElement.PE_IndicatorCheckBox,
            QtWidgets.QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
        }
        if not self.dark_mode or element not in checkbox_elements:
            return super().drawPrimitive(element, option, painter, widget)

        rect = QtCore.QRectF(option.rect).adjusted(1.0, 1.0, -1.0, -1.0)
        enabled = bool(option.state & QtWidgets.QStyle.StateFlag.State_Enabled)
        checked = bool(option.state & QtWidgets.QStyle.StateFlag.State_On)
        partial = bool(option.state & QtWidgets.QStyle.StateFlag.State_NoChange)
        hover = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QtGui.QColor("#303030" if enabled else "#383838"))
        border = QtGui.QColor("#eeeeee" if hover and enabled else ("#b8b8b8" if enabled else "#858585"))
        painter.setPen(QtGui.QPen(border, 1.0))
        painter.drawRoundedRect(rect, 2.0, 2.0)

        mark = QtGui.QColor("#ffffff" if enabled else "#a7a7a7")
        painter.setPen(QtGui.QPen(mark, 1.8, QtCore.Qt.PenStyle.SolidLine,
                                  QtCore.Qt.PenCapStyle.RoundCap,
                                  QtCore.Qt.PenJoinStyle.RoundJoin))
        if checked:
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            path = QtGui.QPainterPath()
            path.moveTo(x + 0.22 * w, y + 0.53 * h)
            path.lineTo(x + 0.43 * w, y + 0.74 * h)
            path.lineTo(x + 0.80 * w, y + 0.28 * h)
            painter.drawPath(path)
        elif partial:
            inset = rect.adjusted(rect.width() * 0.22, rect.height() * 0.43,
                                  -rect.width() * 0.22, -rect.height() * 0.43)
            painter.drawLine(inset.topLeft(), inset.topRight())
        painter.restore()


_CHECK_STYLE: ExactCheckStyle | None = None


def current_ui_metrics() -> UiMetrics:
    app = QtWidgets.QApplication.instance()
    if app is not None:
        try:
            metrics = app.property("exact_ui_metrics")
            if isinstance(metrics, UiMetrics):
                return metrics
        except Exception:
            pass
    return metrics_for_font_offset(0)


def _remember_minimum(widget: QtWidgets.QWidget, prop: str, getter) -> int:
    original = widget.property(prop)
    if original is None:
        original = int(getter())
        widget.setProperty(prop, original)
    return int(original)


def refresh_ui_metrics(app: QtWidgets.QApplication | None = None) -> None:
    """Reapply generic geometry after live font changes."""
    app = app or QtWidgets.QApplication.instance()
    if app is None:
        return
    metrics = current_ui_metrics()
    try:
        widgets = list(app.allWidgets())
    except Exception:
        widgets = []

    control_types = (
        QtWidgets.QPushButton, QtWidgets.QToolButton, QtWidgets.QComboBox,
        QtWidgets.QLineEdit, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox,
    )
    for widget in widgets:
        try:
            if isinstance(widget, control_types):
                original = _remember_minimum(widget, "exact_original_min_height", widget.minimumHeight)
                widget.setMinimumHeight(max(original, metrics.standard_control_height))

            role = str(widget.property("exact_ui_role") or "")
            if role == "settings_button":
                widget.setFixedSize(metrics.settings_button_size, metrics.settings_button_size)
            elif role == "main_tree":
                widget.setMinimumWidth(metrics.main_tree_min_width)
            elif role == "raw_tree":
                widget.setMinimumWidth(metrics.raw_tree_min_width)
            elif role == "processed_tree":
                widget.setMinimumWidth(metrics.processed_tree_min_width)
            elif role == "plotted_list":
                widget.setMinimumWidth(metrics.plotted_list_min_width)
            elif role == "channel_combo":
                widget.setMinimumWidth(metrics.combo_min_width)
            elif role == "busy_row":
                widget.setFixedHeight(metrics.small_row_height)
            elif role == "setup_channels_button":
                # Never freeze width at an old-font size.  sizeHint() follows
                # the current application font and therefore grows live.
                original = _remember_minimum(widget, "exact_original_min_width", widget.minimumWidth)
                widget.setMinimumWidth(max(original, widget.sizeHint().width()))
                widget.setMaximumWidth(16777215)
            elif role == "curve_sidebar":
                # Align the sidebar action row with the bottom-control row of
                # its companion panel.  The reference widget is assigned by
                # ui.py; copying the current bottom margin keeps this correct
                # across font/theme refreshes without hard-coded offsets.
                layout = widget.layout()
                source = getattr(widget, "_exact_bottom_margin_source", None)
                if layout is not None and source is not None and source.layout() is not None:
                    margins = layout.contentsMargins()
                    source_bottom = source.layout().contentsMargins().bottom()
                    layout.setContentsMargins(
                        margins.left(), margins.top(), margins.right(), source_bottom
                    )

                # Keep the splitter from collapsing a curve sidebar far enough
                # to truncate the full-width Check all / Uncheck all row.  Use
                # the buttons' current-font size hints so +1/+2 pt settings are
                # handled automatically.
                buttons = [
                    child for child in widget.findChildren(QtWidgets.QPushButton)
                    if child.text() in {"Check all", "Uncheck all"}
                ]
                if len(buttons) >= 2:
                    by_text = {child.text(): child for child in buttons}
                    check = by_text.get("Check all")
                    uncheck = by_text.get("Uncheck all")
                    if check is not None and uncheck is not None:
                        layout = widget.layout()
                        spacing = metrics.compact_spacing
                        if layout is not None:
                            try:
                                spacing = max(0, int(layout.spacing()))
                            except Exception:
                                pass
                        # Add a small safety allowance for style/frame metrics.
                        required = check.sizeHint().width() + uncheck.sizeHint().width() + spacing + 4
                        original = _remember_minimum(widget, "exact_original_min_width", widget.minimumWidth)
                        widget.setMinimumWidth(max(original, required))

            layout = widget.layout()
            if layout is not None:
                layout_role = str(widget.property("exact_layout_role") or "")
                if layout_role == "panel":
                    m = metrics.panel_margin
                    layout.setContentsMargins(m, m, m, m)
                    layout.setSpacing(metrics.layout_spacing)
                elif layout_role == "compact":
                    layout.setSpacing(metrics.compact_spacing)
            widget.updateGeometry()
            widget.update()
        except Exception:
            pass
    try:
        app.processEvents()
    except Exception:
        pass

def _settings() -> QtCore.QSettings:
    return QtCore.QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


def load_appearance_config() -> AppearanceConfig:
    settings = _settings()
    settings.beginGroup(SETTINGS_GROUP)
    theme_raw = settings.value("theme", UiTheme.SYSTEM.value)
    font_raw = settings.value("font_offset_pt", 0)
    settings.endGroup()
    try:
        theme = UiTheme(str(theme_raw))
    except (TypeError, ValueError):
        theme = UiTheme.SYSTEM
    try:
        font_offset = int(font_raw)
    except (TypeError, ValueError):
        font_offset = 0
    if font_offset not in ALLOWED_FONT_OFFSETS:
        font_offset = 0
    return AppearanceConfig(theme=theme, font_offset_pt=font_offset)


def save_appearance_config(config: AppearanceConfig) -> None:
    try:
        theme = config.theme if isinstance(config.theme, UiTheme) else UiTheme(str(config.theme))
    except (TypeError, ValueError):
        theme = UiTheme.SYSTEM
    try:
        font_offset = int(config.font_offset_pt)
    except (TypeError, ValueError):
        font_offset = 0
    if font_offset not in ALLOWED_FONT_OFFSETS:
        font_offset = 0
    settings = _settings()
    settings.beginGroup(SETTINGS_GROUP)
    settings.setValue("theme", theme.value)
    settings.setValue("font_offset_pt", font_offset)
    settings.endGroup()
    settings.sync()


def capture_application_baseline(app: QtWidgets.QApplication) -> None:
    """Capture the OS-selected palette/font once, before EXACT applies styling."""
    global _BASE_FONT, _SYSTEM_PALETTE
    if _BASE_FONT is None:
        _BASE_FONT = QtGui.QFont(app.font())
    if _SYSTEM_PALETTE is None:
        _SYSTEM_PALETTE = QtGui.QPalette(app.palette())


def _light_palette(app: QtWidgets.QApplication) -> QtGui.QPalette:
    try:
        style = QtWidgets.QStyleFactory.create("Fusion")
        if style is not None:
            return QtGui.QPalette(style.standardPalette())
    except Exception:
        pass
    return QtGui.QPalette(app.palette())


def _dark_palette() -> QtGui.QPalette:
    p = QtGui.QPalette()
    p.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(45, 45, 45))
    p.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(235, 235, 235))
    p.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(30, 30, 30))
    p.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(42, 42, 42))
    p.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(245, 245, 245))
    p.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(25, 25, 25))
    p.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(235, 235, 235))
    p.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(52, 52, 52))
    p.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(235, 235, 235))
    p.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(48, 105, 170))
    p.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(255, 255, 255))
    p.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(105, 175, 235))
    p.setColor(QtGui.QPalette.ColorRole.Mid, QtGui.QColor(145, 145, 145))
    p.setColor(QtGui.QPalette.ColorRole.Midlight, QtGui.QColor(105, 105, 105))
    p.setColor(QtGui.QPalette.ColorRole.Light, QtGui.QColor(120, 120, 120))
    p.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor(150, 150, 150))
    disabled = QtGui.QColor(184, 184, 184)
    for role in (
        QtGui.QPalette.ColorRole.Text,
        QtGui.QPalette.ColorRole.WindowText,
        QtGui.QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QtGui.QPalette.ColorGroup.Disabled, role, disabled)
    return p


def _stylesheet(theme: UiTheme, font_size_pt: int | None, metrics: UiMetrics | None = None) -> str:
    metrics = metrics or metrics_for_font_offset(0)
    font_rule = "" if not font_size_pt or font_size_pt <= 0 else f"font-size: {font_size_pt}pt;"
    common = f"""
        QWidget {{ {font_rule} }}
        QMenu {{ {font_rule} }}
        QToolTip {{ {font_rule} }}
        QMenu::item {{ padding: {metrics.menu_v_padding}px 10px; }}
        QTabBar::tab {{
            padding-top: {metrics.tab_v_padding}px; padding-bottom: {metrics.tab_v_padding}px;
            padding-left: {metrics.tab_h_padding}px; padding-right: {metrics.tab_h_padding}px;
            margin-right: {metrics.tab_gap}px;
        }}
        QTreeView::item, QTableView::item, QListView::item, QListWidget::item, QTreeWidget::item, QTableWidget::item {{ padding-top: {metrics.item_v_padding}px; padding-bottom: {metrics.item_v_padding}px; }}
    """
    if theme is not UiTheme.DARK:
        return common
    return common + """
        QGroupBox, QLabel { color: #eeeeee; }
        QLabel:disabled { color: #9f9f9f; }
        QCheckBox { color: #eeeeee; spacing: 5px; }
        QCheckBox:disabled { color: #9f9f9f; }
        QRadioButton { color: #eeeeee; spacing: 5px; }
        QRadioButton:disabled { color: #9f9f9f; }
        QSplitter::handle { background: #5d5d5d; }
        QSplitter::handle:hover { background: #787878; }
        QPushButton, QToolButton {
            color: #eeeeee; background: #3b3b3b; border: 1px solid #626262;
        }
        QPushButton:hover, QToolButton:hover { background: #4a4a4a; border-color: #858585; }
        QPushButton:pressed, QToolButton:pressed { background: #303030; }
        QPushButton:disabled, QToolButton:disabled { color: #bdbdbd; background: #353535; border-color: #515151; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
            color: #eeeeee; background: #262626; border: 1px solid #666666;
            selection-background-color: #3069aa; selection-color: white;
        }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
            color: #9f9f9f; background: #303030; border-color: #505050;
        }
        QComboBox QAbstractItemView { color: #eeeeee; background: #262626; selection-background-color: #3069aa; }
        QTabBar::tab {
            color: #dddddd; background: #343434; border: 1px solid #5b5b5b;
        }
        QTabBar::tab:selected { color: white; background: #505050; border-color: #808080; }
        QTabBar::tab:hover:!selected { color: white; background: #424242; }
        QHeaderView::section { color: #eeeeee; background: #3c3c3c; border-color: #5e5e5e; }
        QTreeView, QTableView, QListView, QListWidget, QTreeWidget, QTableWidget {
            color: #eeeeee; background: #1f1f1f; alternate-background-color: #292929; border-color: #555555;
        }
        QTreeView::item:selected, QTableView::item:selected, QListView::item:selected,
        QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {
            background: #3069aa; color: white;
        }
        QMenu { color: #eeeeee; background: #2d2d2d; border: 1px solid #555555; }
        QMenu::item:selected { background: #3069aa; color: white; }
        QToolTip { color: #202020; background: #f1f1f1; border: 1px solid #888888; }
    """


def apply_appearance(app: QtWidgets.QApplication, config: AppearanceConfig | None = None) -> AppearanceConfig:
    """Apply appearance to current and future widgets."""
    capture_application_baseline(app)
    config = config or load_appearance_config()
    global _CHECK_STYLE
    try:
        if _CHECK_STYLE is None:
            _CHECK_STYLE = ExactCheckStyle("Fusion")
        _CHECK_STYLE.dark_mode = config.theme is UiTheme.DARK
        app.setStyle(_CHECK_STYLE)
    except Exception:
        try:
            app.setStyle("Fusion")
        except Exception:
            pass
    try:
        if config.theme is UiTheme.DARK:
            app.setPalette(_dark_palette())
        elif config.theme is UiTheme.LIGHT:
            app.setPalette(_light_palette(app))
        elif _SYSTEM_PALETTE is not None:
            app.setPalette(QtGui.QPalette(_SYSTEM_PALETTE))
    except Exception:
        pass

    font_size_pt = None
    try:
        base = QtGui.QFont(_BASE_FONT or app.font())
        font = QtGui.QFont(base)
        increment = BASELINE_FONT_INCREMENT + int(config.font_offset_pt)
        if base.pointSize() > 0:
            font_size_pt = int(base.pointSize()) + increment
            font.setPointSize(font_size_pt)
        elif base.pixelSize() > 0:
            font.setPixelSize(int(base.pixelSize()) + increment)
        app.setFont(font)
    except Exception:
        pass
    metrics = metrics_for_font_offset(config.font_offset_pt)
    try:
        app.setProperty("exact_ui_metrics", metrics)
        app.setStyleSheet(_stylesheet(config.theme, font_size_pt, metrics))
        app.setProperty("exact_ui_theme", config.theme.value)
        app.setProperty("exact_ui_font_offset_pt", int(config.font_offset_pt))
    except Exception:
        pass
    return config


def apply_appearance_live(config: AppearanceConfig) -> None:
    save_appearance_config(config)
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    apply_appearance(app, config)
    try:
        refresh_ui_metrics(app)
        for widget in app.allWidgets():
            widget.updateGeometry()
            widget.update()
        app.processEvents()
    except Exception:
        pass


def current_appearance_config() -> AppearanceConfig:
    return load_appearance_config()
