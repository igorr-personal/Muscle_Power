"""Signal Processing panel — RMS avg window and wave smoothing."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QSpinBox,
)

from muscle_power_desktop.app import AppState


class SignalPanel(QGroupBox):
    """Controls for RMS window duration and display smoothing."""

    changed = pyqtSignal()

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__("Signal Processing", parent)
        self._state = state
        self._build_ui()
        self._load_from_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Avg window ─────────────────────────────────────────────────
        avg_row = QHBoxLayout()
        avg_row.addWidget(QLabel("Avg window (s):"))
        self._avg_spin = QDoubleSpinBox()
        self._avg_spin.setRange(0.1, 2.0)
        self._avg_spin.setSingleStep(0.05)
        self._avg_spin.setDecimals(2)
        self._avg_spin.setSuffix(" s")
        self._avg_spin.setToolTip(
            "RMS average is recomputed over this many seconds of samples."
        )
        self._avg_spin.valueChanged.connect(self._on_avg_changed)
        avg_row.addWidget(self._avg_spin)
        avg_row.addStretch()
        root.addLayout(avg_row)

        # ── Wave smoothing ─────────────────────────────────────────────
        smooth_row = QHBoxLayout()
        smooth_row.addWidget(QLabel("Wave smoothing:"))
        self._smooth_spin = QSpinBox()
        self._smooth_spin.setRange(1, 8)
        self._smooth_spin.setSingleStep(1)
        self._smooth_spin.setToolTip(
            "Moving-average half-width for display.\n"
            "1 = no smoothing, 8 = widest kernel."
        )
        self._smooth_spin.valueChanged.connect(self._on_smooth_changed)
        smooth_row.addWidget(self._smooth_spin)
        smooth_row.addStretch()
        root.addLayout(smooth_row)

    def _load_from_state(self) -> None:
        self._avg_spin.blockSignals(True)
        self._smooth_spin.blockSignals(True)
        self._avg_spin.setValue(float(self._state.get("avg_window_sec", 0.5)))
        self._smooth_spin.setValue(int(self._state.get("wave_smooth", 1)))
        self._avg_spin.blockSignals(False)
        self._smooth_spin.blockSignals(False)

    def reload_from_state(self) -> None:
        self._load_from_state()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_avg_changed(self, value: float) -> None:
        self._state.set("avg_window_sec", value)
        self._state.save_settings()
        self.changed.emit()

    def _on_smooth_changed(self, value: int) -> None:
        self._state.set("wave_smooth", value)
        self._state.save_settings()
        self.changed.emit()
