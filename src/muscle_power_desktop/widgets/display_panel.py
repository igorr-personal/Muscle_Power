"""Display Options panel — amplitude scale, V/div, time window, envelope."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QCheckBox, QComboBox, QButtonGroup, QRadioButton,
    QWidget,
)

from muscle_power_desktop.app import AppState
from muscle_power_desktop.widgets.oscilloscope import VDIV_STEPS

VDIV_LABELS = [
    "0.1 mV", "0.2 mV", "0.5 mV",
    "1 mV",   "2 mV",   "5 mV",
    "10 mV",  "20 mV",  "50 mV",
    "100 mV", "200 mV", "500 mV",
    "1 V",    "2 V",    "5 V",
]


class DisplayPanel(QGroupBox):
    """Controls that affect the oscilloscope visual presentation."""

    changed = pyqtSignal()

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__("Display Options", parent)
        self._state = state
        self._build_ui()
        self._load_from_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Scale mode radio ───────────────────────────────────────────
        root.addWidget(QLabel("Amplitude scale:"))
        radio_row = QHBoxLayout()
        self._auto_radio = QRadioButton("Auto")
        self._manual_radio = QRadioButton("Manual")
        self._scale_group = QButtonGroup(self)
        self._scale_group.addButton(self._auto_radio, 0)
        self._scale_group.addButton(self._manual_radio, 1)
        radio_row.addWidget(self._auto_radio)
        radio_row.addWidget(self._manual_radio)
        radio_row.addStretch()
        root.addLayout(radio_row)
        self._scale_group.idToggled.connect(self._on_scale_mode_changed)

        # ── V/div combo (visible in Manual mode only) ──────────────────
        self._vdiv_row = QWidget()
        vdiv_layout = QHBoxLayout(self._vdiv_row)
        vdiv_layout.setContentsMargins(0, 0, 0, 0)
        vdiv_layout.addWidget(QLabel("V/div:"))
        self._vdiv_combo = QComboBox()
        self._vdiv_combo.addItems(VDIV_LABELS)
        self._vdiv_combo.currentIndexChanged.connect(self._on_vdiv_changed)
        vdiv_layout.addWidget(self._vdiv_combo, stretch=1)
        root.addWidget(self._vdiv_row)

        # ── Time window slider ─────────────────────────────────────────
        root.addWidget(QLabel("Time window (samples):"))
        win_row = QHBoxLayout()
        self._window_slider = QSlider(Qt.Orientation.Horizontal)
        self._window_slider.setRange(200, 2000)
        self._window_slider.setSingleStep(50)
        self._window_slider.setPageStep(100)
        self._window_slider.valueChanged.connect(self._on_window_changed)
        self._window_val_label = QLabel()
        win_row.addWidget(self._window_slider, stretch=1)
        win_row.addWidget(self._window_val_label)
        root.addLayout(win_row)

        # ── Show envelope ──────────────────────────────────────────────
        self._env_chk = QCheckBox("Show envelope")
        self._env_chk.setToolTip("Overlay the RMS amplitude envelope on the signal.")
        self._env_chk.toggled.connect(self._on_envelope_changed)
        root.addWidget(self._env_chk)

    def _load_from_state(self) -> None:
        """Initialise all widgets from current AppState values."""
        # Block signals to avoid triggering saves during init
        for w in (self._vdiv_combo, self._window_slider, self._env_chk):
            w.blockSignals(True)

        mode = str(self._state.get("scope_scale_mode", "Auto"))
        is_manual = mode == "Manual"
        self._auto_radio.setChecked(not is_manual)
        self._manual_radio.setChecked(is_manual)
        self._vdiv_row.setVisible(is_manual)

        idx = int(self._state.get("scope_vdiv_idx", 4))
        self._vdiv_combo.setCurrentIndex(max(0, min(idx, len(VDIV_LABELS) - 1)))

        win = int(self._state.get("scope_window", 800))
        self._window_slider.setValue(win)
        self._window_val_label.setText(str(win))

        self._env_chk.setChecked(bool(self._state.get("show_envelope", False)))

        for w in (self._vdiv_combo, self._window_slider, self._env_chk):
            w.blockSignals(False)

    def reload_from_state(self) -> None:
        self._load_from_state()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_scale_mode_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        mode = "Manual" if btn_id == 1 else "Auto"
        self._vdiv_row.setVisible(mode == "Manual")
        self._state.set("scope_scale_mode", mode)
        self._state.save_settings()
        self.changed.emit()

    def _on_vdiv_changed(self, idx: int) -> None:
        self._state.set("scope_vdiv_idx", idx)
        self._state.save_settings()
        self.changed.emit()

    def _on_window_changed(self, value: int) -> None:
        self._window_val_label.setText(str(value))
        self._state.set("scope_window", value)
        self._state.save_settings()
        self.changed.emit()

    def _on_envelope_changed(self, checked: bool) -> None:
        self._state.set("show_envelope", checked)
        self._state.save_settings()
        self.changed.emit()
