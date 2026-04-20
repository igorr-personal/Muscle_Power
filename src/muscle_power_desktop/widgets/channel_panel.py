"""Channel configuration panel — enable/disable + label each EMG channel."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QLineEdit, QPushButton, QGroupBox, QColorDialog, QFrame,
)
from PyQt6.QtGui import QColor, QPalette

from muscle_power_desktop.app import AppState

SENSOR_SLOTS = [
    {"id": "red",   "default_color": "#FF4444", "label": "Red"},
    {"id": "blue",  "default_color": "#00BFFF", "label": "Blue"},
    {"id": "green", "default_color": "#39FF14", "label": "Green"},
    {"id": "white", "default_color": "#FFFFFF", "label": "White"},
]


class ChannelCard(QFrame):
    """One channel card: toggle + muscle name + optional colour picker."""

    changed = pyqtSignal()

    def __init__(self, slot: dict, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._slot = slot
        self._state = state
        sid = slot["id"]
        color = self._current_color()

        self.setStyleSheet(
            f"QFrame {{ background: linear-gradient(135deg, {color}22, {color}08); "
            f"border: 1.5px solid {color}55; border-radius: 8px; "
            f"padding: 8px; margin: 2px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 6, 8, 6)

        # Active toggle
        self._chk = QCheckBox()
        self._chk.setChecked(bool(state.get(f"slot_active_{sid}", False)))
        self._chk.toggled.connect(self._on_active_changed)
        layout.addWidget(self._chk)

        # Colour dot
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        layout.addWidget(self._dot)

        # Muscle name
        self._name_edit = QLineEdit(str(state.get(f"muscle_en_{sid}", sid.title())))
        self._name_edit.setPlaceholderText("Muscle name")
        self._name_edit.setStyleSheet("background: transparent; border: none; "
                                      "border-bottom: 1px solid rgba(255,255,255,0.2);")
        self._name_edit.textChanged.connect(self._on_name_changed)
        layout.addWidget(self._name_edit, stretch=1)

        # Color picker (white channel only)
        if sid == "white":
            self._color_btn = QPushButton("🎨")
            self._color_btn.setFixedSize(30, 26)
            self._color_btn.setToolTip("Pick channel colour")
            self._color_btn.clicked.connect(self._on_pick_color)
            layout.addWidget(self._color_btn)

    def _current_color(self) -> str:
        sid = self._slot["id"]
        if sid == "white":
            return str(self._state.get("white_color", "#FFFFFF"))
        return self._slot["default_color"]

    def _on_active_changed(self, checked: bool) -> None:
        self._state.set(f"slot_active_{self._slot['id']}", checked)
        self._state.save_settings()
        self.changed.emit()

    def _on_name_changed(self, text: str) -> None:
        self._state.set(f"muscle_en_{self._slot['id']}", text)
        self._state.save_settings()
        self.changed.emit()

    def _on_pick_color(self) -> None:
        current = QColor(self._current_color())
        color = QColorDialog.getColor(current, self, "Pick channel colour")
        if color.isValid():
            hex_color = color.name()
            self._state.set("white_color", hex_color)
            self._state.save_settings()
            self._dot.setStyleSheet(f"color: {hex_color}; font-size: 16px;")
            self.setStyleSheet(
                f"QFrame {{ background: linear-gradient(135deg, {hex_color}22, {hex_color}08); "
                f"border: 1.5px solid {hex_color}55; border-radius: 8px; "
                f"padding: 8px; margin: 2px; }}"
            )
            self.changed.emit()

    def reload_from_state(self) -> None:
        """Refresh UI from current AppState (e.g., after user switch)."""
        sid = self._slot["id"]
        self._chk.blockSignals(True)
        self._name_edit.blockSignals(True)
        self._chk.setChecked(bool(self._state.get(f"slot_active_{sid}", False)))
        self._name_edit.setText(str(self._state.get(f"muscle_en_{sid}", sid.title())))
        self._chk.blockSignals(False)
        self._name_edit.blockSignals(False)


class ChannelPanel(QGroupBox):
    """Panel containing all 4 channel cards."""

    changed = pyqtSignal()

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__("Sensor Channels", parent)
        self._state = state
        self._cards: list[ChannelCard] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        for slot in SENSOR_SLOTS:
            card = ChannelCard(slot, state)
            card.changed.connect(self.changed)
            layout.addWidget(card)
            self._cards.append(card)

    def reload_from_state(self) -> None:
        for card in self._cards:
            card.reload_from_state()
