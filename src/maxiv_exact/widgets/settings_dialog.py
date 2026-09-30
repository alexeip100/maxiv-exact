from __future__ import annotations

"""Compact EXACT application settings dialog."""

from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QVBoxLayout, QWidget

from ..appearance import AppearanceConfig, UiTheme


class SettingsDialog(QDialog):
    def __init__(self, config: AppearanceConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(330)

        root = QVBoxLayout(self)
        group = QGroupBox("Appearance", self)
        form = QFormLayout(group)

        self.theme_combo = QComboBox(group)
        self.theme_combo.addItem("System", UiTheme.SYSTEM.value)
        self.theme_combo.addItem("Light", UiTheme.LIGHT.value)
        self.theme_combo.addItem("Dark", UiTheme.DARK.value)
        idx = self.theme_combo.findData(config.theme.value)
        self.theme_combo.setCurrentIndex(max(0, idx))
        self.theme_combo.setToolTip("Choose the application color theme.")
        form.addRow("Theme:", self.theme_combo)

        self.font_combo = QComboBox(group)
        self.font_combo.addItem("Default (current)", 0)
        self.font_combo.addItem("Larger (+1 pt)", 1)
        self.font_combo.addItem("Largest (+2 pt)", 2)
        idx = self.font_combo.findData(int(config.font_offset_pt))
        self.font_combo.setCurrentIndex(max(0, idx))
        self.font_combo.setToolTip("Enlarge the Qt interface font. Plot/figure fonts are unchanged.")
        form.addRow("UI font size:", self.font_combo)

        root.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def configuration(self) -> AppearanceConfig:
        return AppearanceConfig(
            theme=UiTheme(str(self.theme_combo.currentData())),
            font_offset_pt=int(self.font_combo.currentData()),
        )
