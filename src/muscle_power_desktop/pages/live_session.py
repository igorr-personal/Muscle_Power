"""Live Session page — real-time EMG oscilloscope for the desktop app."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QScrollArea,
    QGroupBox, QPushButton, QLabel, QLineEdit, QFrame,
    QListWidget, QListWidgetItem, QMessageBox,
)

from muscle_power_desktop.app import AppState
from muscle_power_desktop.widgets.oscilloscope import OscilloscopeWidget
from muscle_power_desktop.widgets.channel_panel import ChannelPanel
from muscle_power_desktop.widgets.display_panel import DisplayPanel
from muscle_power_desktop.widgets.signal_panel import SignalPanel
from muscle_power.services.signal_processing import (
    bandpass_filter, compute_rms_envelope, detect_reps, compute_fatigue_index,
)
from muscle_power.utils.errors import (
    SDKNotInstalledError, SensorConnectionError,
)
from muscle_power.services.sim_generator import SIM_FS


class LiveSessionPage(QWidget):
    """Full Live Session page — sidebar + oscilloscope."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._scanning = False
        self._found_devices: list = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(5)

        # ── LEFT: sidebar ──────────────────────────────────────────────
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setMinimumWidth(240)
        sidebar_scroll.setMaximumWidth(300)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(8)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)

        # Title
        title = QLabel("⚡ Muscle Power")
        title.setObjectName("titleLabel")
        sidebar_layout.addWidget(title)

        # Simulation mode toggle
        sim_box = QGroupBox("Mode")
        sim_inner = QVBoxLayout(sim_box)
        self._sim_btn = QPushButton()
        self._sim_btn.setCheckable(True)
        self._sim_btn.setChecked(bool(self._state.get("sim_mode", False)))
        self._sim_btn.clicked.connect(self._on_sim_toggled)
        self._refresh_sim_button_text()
        sim_inner.addWidget(self._sim_btn)
        sidebar_layout.addWidget(sim_box)

        # Sensor connection panel
        self._conn_box = QGroupBox("Sensor Connection")
        conn_inner = QVBoxLayout(self._conn_box)

        self._sensor_status_label = QLabel("Disconnected")
        self._sensor_status_label.setObjectName("dimLabel")
        conn_inner.addWidget(self._sensor_status_label)

        self._scan_btn = QPushButton("🔍 Scan for Devices")
        self._scan_btn.clicked.connect(self._on_scan)
        conn_inner.addWidget(self._scan_btn)

        self._device_list = QListWidget()
        self._device_list.setMaximumHeight(100)
        self._device_list.hide()
        conn_inner.addWidget(self._device_list)

        self._connect_btn = QPushButton("🔗 Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._connect_btn.hide()
        conn_inner.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("🔌 Disconnect")
        self._disconnect_btn.setObjectName("dangerBtn")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._disconnect_btn.hide()
        conn_inner.addWidget(self._disconnect_btn)

        sidebar_layout.addWidget(self._conn_box)
        self._update_sensor_ui()

        # Channel panel
        self._channel_panel = ChannelPanel(self._state)
        self._channel_panel.changed.connect(self._on_panel_changed)
        sidebar_layout.addWidget(self._channel_panel)

        # Display Options panel
        self._display_panel = DisplayPanel(self._state)
        self._display_panel.changed.connect(self._on_panel_changed)
        sidebar_layout.addWidget(self._display_panel)

        # Signal Processing panel
        self._signal_panel = SignalPanel(self._state)
        self._signal_panel.changed.connect(self._on_panel_changed)
        sidebar_layout.addWidget(self._signal_panel)

        sidebar_layout.addStretch()
        sidebar_scroll.setWidget(sidebar)
        splitter.addWidget(sidebar_scroll)

        # ── RIGHT: oscilloscope + controls ────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        # Recording controls
        rec_box = QGroupBox("Session Recording")
        rec_inner = QHBoxLayout(rec_box)

        rec_inner.addWidget(QLabel("Muscle group:"))
        self._muscle_edit = QLineEdit()
        self._muscle_edit.setPlaceholderText("e.g. Bicep curls")
        self._muscle_edit.setMaximumWidth(180)
        rec_inner.addWidget(self._muscle_edit)

        rec_inner.addWidget(QLabel("Name:"))
        self._recname_edit = QLineEdit(str(self._state.get("rec_name", "Recording")))
        self._recname_edit.setMaximumWidth(160)
        self._recname_edit.textChanged.connect(
            lambda t: (self._state.set("rec_name", t), self._state.save_settings())
        )
        rec_inner.addWidget(self._recname_edit)

        rec_inner.addSpacing(16)
        self._start_btn = QPushButton("▶ Start")
        self._start_btn.setObjectName("primaryBtn")
        self._start_btn.clicked.connect(self._on_start_scope)
        rec_inner.addWidget(self._start_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setObjectName("dangerBtn")
        self._stop_btn.clicked.connect(self._on_stop_scope)
        self._stop_btn.setEnabled(False)
        rec_inner.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("🗑 Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        rec_inner.addWidget(self._clear_btn)

        rec_inner.addStretch()
        right_layout.addWidget(rec_box)

        # Oscilloscope
        self._scope = OscilloscopeWidget(self._state)
        right_layout.addWidget(self._scope, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 1000])

        root.addWidget(splitter)

        # Sensor status update timer
        self._sensor_poll_timer = QTimer(self)
        self._sensor_poll_timer.timeout.connect(self._update_sensor_ui)
        self._sensor_poll_timer.start(2000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_sim_button_text(self) -> None:
        sim = self._sim_btn.isChecked()
        self._sim_btn.setText(
            "🎮 Simulation Mode  ON" if sim else "🎮 Simulation Mode  OFF"
        )

    def _update_sensor_ui(self) -> None:
        svc = self._state.sensor_service
        state_str = getattr(svc, "state", "disconnected")
        sim_on = bool(self._state.get("sim_mode", False))

        if sim_on:
            self._conn_box.setVisible(False)
            return
        self._conn_box.setVisible(True)

        color = "#3ddc84" if state_str == "connected" else \
                "#FFC107" if state_str == "connecting" else "#E8E8F0"
        sensor_name = ""
        if hasattr(svc, "sensor_info") and svc.sensor_info:
            sensor_name = f" — {svc.sensor_info.name}"
        batt = getattr(svc, "battery", -1)
        batt_str = f"  🔋 {batt}%" if batt >= 0 else ""
        self._sensor_status_label.setText(
            f"<span style='color:{color}'>●</span> {state_str.title()}{sensor_name}{batt_str}"
        )

        is_connected = state_str == "connected"
        self._scan_btn.setVisible(not is_connected)
        self._connect_btn.setVisible(bool(self._found_devices) and not is_connected)
        self._device_list.setVisible(bool(self._found_devices) and not is_connected)
        self._disconnect_btn.setVisible(is_connected)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_sim_toggled(self, checked: bool) -> None:
        self._state.set("sim_mode", checked)
        self._state.save_settings()
        self._refresh_sim_button_text()
        self._update_sensor_ui()

    def _on_panel_changed(self) -> None:
        """Propagate any panel config change to the oscilloscope."""
        self._scope.refresh_from_settings()

    def _on_scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("🔍 Scanning...")
        self._found_devices = []
        self._device_list.clear()

        svc = self._state.sensor_service
        timeout = float(self._state.get("scan_timeout", 10))

        def do_scan() -> None:
            try:
                results = svc.scan_all_ble(timeout=timeout)
                self._found_devices = results
            except Exception as e:
                self._found_devices = []
                # Schedule UI update on main thread
                QTimer.singleShot(0, lambda: self._show_scan_error(str(e)))
            QTimer.singleShot(0, self._on_scan_done)

        t = threading.Thread(target=do_scan, daemon=True)
        t.start()

    def _on_scan_done(self) -> None:
        self._scanning = False
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("🔍 Scan for Devices")
        self._device_list.clear()
        for dev in self._found_devices:
            tag = "" if dev.is_callibri else "  (not Callibri)"
            item = QListWidgetItem(f"{dev.name} ({dev.address}){tag}")
            if dev.is_callibri:
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#3ddc84"))
            self._device_list.addItem(item)
        self._update_sensor_ui()

    def _show_scan_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Scan Error", msg)

    def _on_connect(self) -> None:
        idx = self._device_list.currentRow()
        if idx < 0 or idx >= len(self._found_devices):
            QMessageBox.warning(self, "No device", "Select a device from the list first.")
            return
        dev = self._found_devices[idx]
        if not dev.is_callibri:
            QMessageBox.warning(self, "Not a Callibri", "Only Callibri sensors are supported.")
            return
        svc = self._state.sensor_service

        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting...")

        def do_connect() -> None:
            try:
                raw_sensors = getattr(svc._scanner, "sensors", lambda: [])()
                matching = [r for r in raw_sensors if r.address == dev.address]
                if matching:
                    with ThreadPoolExecutor() as ex:
                        fut = ex.submit(svc.connect, matching[0])
                        fut.result(timeout=30)
                else:
                    QTimer.singleShot(0, lambda: QMessageBox.warning(
                        self, "Error", "Raw sensor not found — please re-scan."
                    ))
            except SensorConnectionError as exc:
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Connection Error", str(exc)))
            QTimer.singleShot(0, self._on_connect_done)

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_connect_done(self) -> None:
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("🔗 Connect")
        self._update_sensor_ui()

    def _on_disconnect(self) -> None:
        svc = self._state.sensor_service
        self._scope.stop()
        svc.disconnect()
        self._update_sensor_ui()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _on_start_scope(self) -> None:
        self._scope.start()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def _on_stop_scope(self) -> None:
        self._scope.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _on_clear(self) -> None:
        self._scope.clear_buffers()

    # ------------------------------------------------------------------
    # Called by MainWindow on user switch
    # ------------------------------------------------------------------

    def on_user_changed(self) -> None:
        """Reload all panel widgets and scope settings for the new user."""
        self._recname_edit.setText(str(self._state.get("rec_name", "Recording")))
        self._sim_btn.blockSignals(True)
        self._sim_btn.setChecked(bool(self._state.get("sim_mode", False)))
        self._sim_btn.blockSignals(False)
        self._refresh_sim_button_text()
        self._channel_panel.reload_from_state()
        self._display_panel.reload_from_state()
        self._signal_panel.reload_from_state()
        self._scope.refresh_from_settings()

    def pause(self) -> None:
        self._scope.stop()
