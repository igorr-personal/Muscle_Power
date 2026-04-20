"""Real-time EMG oscilloscope widget using pyqtgraph.

Displays up to 4 channels stacked vertically at 30 fps.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout,
)

from muscle_power.services.sim_generator import (
    next_chunk as _sim_next_chunk,
    SIM_CHUNK,
    SIM_FS,
)

# --------------------------------------------------------------------------
# Colour palette — matches the Streamlit web version
# --------------------------------------------------------------------------
SLOT_COLORS: dict[str, str] = {
    "red":   "#FF4444",
    "blue":  "#00BFFF",
    "green": "#39FF14",
    "white": "#FFFFFF",
}

SENSOR_SLOTS = ["red", "blue", "green", "white"]

# V/div steps and labels (mirrors 1_Live_Session.py)
VDIV_STEPS = [
    0.0001, 0.0002, 0.0005,
    0.001,  0.002,  0.005,
    0.01,   0.02,   0.05,
    0.1,    0.2,    0.5,
    1.0,    2.0,    5.0,
]
N_DIVISIONS = 10
DEFAULT_VDIV_IDX = 4


def _auto_vdiv(max_abs_v: float) -> float:
    if max_abs_v <= 0:
        return VDIV_STEPS[DEFAULT_VDIV_IDX]
    target = max_abs_v / (N_DIVISIONS / 2 * 0.8)
    for vdiv in VDIV_STEPS:
        if vdiv >= target:
            return vdiv
    return VDIV_STEPS[-1]


def _fmt_v(v: float) -> str:
    mv = v * 1000
    if abs(mv) >= 1000:
        return f"{v:.2g} V"
    if abs(mv) >= 1:
        return f"{mv:.4g} mV"
    return f"{mv * 1000:.4g} µV"


class ChannelPlotItem:
    """Holds all pyqtgraph items for one channel."""

    def __init__(self, slot_id: str, color: str, plot_widget: pg.PlotWidget) -> None:
        self.slot_id = slot_id
        self.color = color
        self.pw = plot_widget

        pen = pg.mkPen(color=color, width=1.5)
        self.curve = plot_widget.plot(pen=pen, name=slot_id)

        env_pen = pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine)
        self.env_curve = plot_widget.plot(pen=env_pen, name=f"{slot_id}_env")
        self.env_curve.hide()

        # RMS guide lines (±)
        self.rms_pos = pg.InfiniteLine(angle=0, movable=False,
                                       pen=pg.mkPen(color=color, width=0.8,
                                                    style=Qt.PenStyle.DotLine))
        self.rms_neg = pg.InfiniteLine(angle=0, movable=False,
                                       pen=pg.mkPen(color=color, width=0.8,
                                                    style=Qt.PenStyle.DotLine))
        plot_widget.addItem(self.rms_pos)
        plot_widget.addItem(self.rms_neg)

        self.buf: deque = deque(maxlen=2000)
        self.avg_acc: list = []
        self.avg_val: float = 0.0
        self.auto_vdiv: float = VDIV_STEPS[DEFAULT_VDIV_IDX]

    def push(self, samples: np.ndarray, avg_window_samples: int) -> None:
        self.buf.extend(samples.tolist())
        self.avg_acc.extend(samples.tolist())
        if len(self.avg_acc) >= avg_window_samples:
            chunk = self.avg_acc[:avg_window_samples]
            self.avg_val = float(np.sqrt(np.mean(np.square(chunk))))
            self.avg_acc = self.avg_acc[avg_window_samples:]

    def update_auto_vdiv(self) -> None:
        if self.buf:
            arr = np.array(self.buf)
            self.auto_vdiv = _auto_vdiv(float(np.max(np.abs(arr))))

    def clear(self) -> None:
        self.buf.clear()
        self.avg_acc.clear()
        self.avg_val = 0.0
        self.curve.setData([])
        self.env_curve.setData([])


class OscilloscopeWidget(QWidget):
    """Stacked multi-channel EMG oscilloscope at ~30 fps.

    Signals
    -------
    avg_updated(slot_id, rms_value)
        Emitted every update cycle with the current RMS average for each channel.
    """

    avg_updated = pyqtSignal(str, float)

    def __init__(self, state, parent=None) -> None:
        """
        Parameters
        ----------
        state:
            AppState — used to read settings (scope_window, scale_mode, etc.)
        """
        super().__init__(parent)
        self._state = state
        self._running = False
        self._sim_frame = 0
        self._channels: dict[str, ChannelPlotItem] = {}
        self._plot_widgets: dict[str, pg.PlotWidget] = {}
        self._kpi_labels: dict[str, QLabel] = {}

        # Configure pyqtgraph global options
        pg.setConfigOptions(antialias=True, background="#0a0818", foreground="#E8E8F0")

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._update)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(2)
        root.setContentsMargins(0, 0, 0, 0)

        # KPI row at the top
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)

        for slot_id in SENSOR_SLOTS:
            color = self._slot_color(slot_id)
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: rgba(255,255,255,0.05); "
                f"border: 1px solid {color}44; border-radius: 6px; padding: 4px; }}"
            )
            clt = QVBoxLayout(card)
            clt.setContentsMargins(8, 4, 8, 4)
            clt.setSpacing(1)
            name_lbl = QLabel(self._state.get(f"muscle_en_{slot_id}", slot_id.title()))
            name_lbl.setStyleSheet(f"color: {color}; font-weight:bold; font-size:12px;")
            name_lbl.setObjectName(f"kpi_name_{slot_id}")
            val_lbl = QLabel("---")
            val_lbl.setStyleSheet("color: #E8E8F0; font-size:13px; font-weight:bold;")
            val_lbl.setObjectName(f"kpi_val_{slot_id}")
            clt.addWidget(name_lbl)
            clt.addWidget(val_lbl)
            kpi_row.addWidget(card)
            self._kpi_labels[slot_id] = val_lbl

        root.addLayout(kpi_row)

        # Plot area — one PlotWidget per channel
        for slot_id in SENSOR_SLOTS:
            color = self._slot_color(slot_id)
            pw = pg.PlotWidget()
            pw.setMinimumHeight(80)
            pw.showGrid(x=False, y=True, alpha=0.15)
            pw.getAxis("left").setStyle(tickFont=None)
            pw.getAxis("bottom").hide()
            pw.setMouseEnabled(x=False, y=False)
            pw.setMenuEnabled(False)

            # Channel colour title on the left axis
            pw.getAxis("left").setLabel(
                self._state.get(f"muscle_en_{slot_id}", slot_id.title()),
                color=color,
            )

            self._plot_widgets[slot_id] = pw
            self._channels[slot_id] = ChannelPlotItem(slot_id, color, pw)

            # Wrap in a frame for visual separation
            frame = QFrame()
            frame.setStyleSheet(
                f"QFrame {{ border: 1px solid {color}22; border-radius:4px; }}"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.addWidget(pw)
            root.addWidget(frame)

    # ------------------------------------------------------------------
    # Runtime settings
    # ------------------------------------------------------------------

    def _slot_color(self, slot_id: str) -> str:
        if slot_id == "white":
            return str(self._state.get("white_color", "#FFFFFF"))
        return SLOT_COLORS.get(slot_id, "#AAAAAA")

    def _is_active(self, slot_id: str) -> bool:
        return bool(self._state.get(f"slot_active_{slot_id}", False))

    def _scope_window(self) -> int:
        return int(self._state.get("scope_window", 800))

    def _scale_mode(self) -> str:
        return str(self._state.get("scope_scale_mode", "Auto"))

    def _vdiv_manual(self) -> float:
        idx = int(self._state.get("scope_vdiv_idx", DEFAULT_VDIV_IDX))
        return VDIV_STEPS[max(0, min(idx, len(VDIV_STEPS) - 1))]

    def _wave_smooth(self) -> int:
        return max(1, int(self._state.get("wave_smooth", 1)))

    def _avg_window_samples(self) -> int:
        sec = float(self._state.get("avg_window_sec", 0.5))
        return max(1, int(round(sec * SIM_FS)))

    def _show_envelope(self) -> bool:
        return bool(self._state.get("show_envelope", False))

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the oscilloscope update loop."""
        self._running = True
        self._timer.start()

    def stop(self) -> None:
        """Stop updates (does not clear data)."""
        self._running = False
        self._timer.stop()

    def pause(self) -> None:
        self.stop()

    def clear_buffers(self) -> None:
        for ch in self._channels.values():
            ch.clear()
        self._sim_frame = 0

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Refresh channel visibility and labels from current settings
    # ------------------------------------------------------------------

    def refresh_from_settings(self) -> None:
        for slot_id, pw in self._plot_widgets.items():
            active = self._is_active(slot_id)
            pw.setVisible(active)
            color = self._slot_color(slot_id)
            muscle = str(self._state.get(f"muscle_en_{slot_id}", slot_id.title()))
            # Update axis label colour
            pw.getAxis("left").setLabel(muscle, color=color)
            # Update KPI name label
            name_lbl = self.findChild(QLabel, f"kpi_name_{slot_id}")
            if name_lbl:
                name_lbl.setText(muscle)
                name_lbl.setStyleSheet(
                    f"color: {color}; font-weight:bold; font-size:12px;"
                )
            # Update curve pen colour in case white_color changed
            ch = self._channels[slot_id]
            ch.color = color
            ch.curve.setPen(pg.mkPen(color=color, width=1.5))
            ch.env_curve.setPen(
                pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine)
            )
            ch.env_curve.setVisible(active and self._show_envelope())

    # ------------------------------------------------------------------
    # Update loop
    # ------------------------------------------------------------------

    def _update(self) -> None:
        svc = self._state.sensor_service
        sim_mode = bool(self._state.get("sim_mode", True))
        window = self._scope_window()
        scale_mode = self._scale_mode()
        manual_vdiv = self._vdiv_manual()
        smooth = self._wave_smooth()
        avg_win = self._avg_window_samples()
        show_env = self._show_envelope()

        for slot_id in SENSOR_SLOTS:
            if not self._is_active(slot_id):
                self._plot_widgets[slot_id].setVisible(False)
                continue
            self._plot_widgets[slot_id].setVisible(True)
            ch = self._channels[slot_id]

            # ── Acquire new samples ────────────────────────────────────
            if sim_mode:
                new_samples = _sim_next_chunk(slot_id, self._sim_frame)
            else:
                if hasattr(svc, "get_raw_samples") and svc.state == "connected":
                    raw = svc.get_raw_samples(max_samples=SIM_CHUNK)
                    new_samples = np.array(
                        [s.raw_value for s in raw[-SIM_CHUNK:]], dtype=float
                    )
                else:
                    new_samples = np.zeros(SIM_CHUNK)

            ch.push(new_samples, avg_win)
            ch.update_auto_vdiv()

            # ── Build display array (last `window` samples) ────────────
            buf = list(ch.buf)[-window:]
            if not buf:
                continue
            display = np.array(buf, dtype=float)

            # Wave smoothing (moving average)
            if smooth > 1:
                kernel = np.ones(smooth * 2 - 1) / (smooth * 2 - 1)
                if len(display) >= len(kernel):
                    display = np.convolve(display, kernel, mode="same")

            ch.curve.setData(display)

            # Envelope overlay
            if show_env:
                from muscle_power.services.signal_processing import (
                    compute_rms_envelope,
                )
                env = compute_rms_envelope(display, fs=float(SIM_FS))
                ch.env_curve.setData(env)
                ch.env_curve.show()
            else:
                ch.env_curve.hide()

            # ── Y-axis scaling ─────────────────────────────────────────
            if scale_mode == "Manual":
                vdiv = manual_vdiv
            else:
                vdiv = ch.auto_vdiv

            half_range = vdiv * N_DIVISIONS / 2
            pw = self._plot_widgets[slot_id]
            pw.setYRange(-half_range, half_range, padding=0)

            # RMS guide lines
            rms = ch.avg_val
            ch.rms_pos.setPos(rms)
            ch.rms_neg.setPos(-rms)

            # ── KPI label ──────────────────────────────────────────────
            kpi = self._kpi_labels.get(slot_id)
            if kpi:
                kpi.setText(_fmt_v(rms))
            self.avg_updated.emit(slot_id, rms)

        # Advance frame counter (used by sim generator)
        if sim_mode:
            self._sim_frame += 1
