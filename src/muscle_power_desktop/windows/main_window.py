"""Main application window — QTabWidget with all pages."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QStatusBar,
    QLabel, QHBoxLayout, QPushButton, QMessageBox,
)

from muscle_power_desktop.app import AppState
from muscle_power_desktop.pages.live_session import LiveSessionPage
from muscle_power_desktop.pages.history import HistoryPage
from muscle_power_desktop.pages.export_page import ExportPage
from muscle_power_desktop.pages.settings_page import SettingsPage
from muscle_power_desktop.windows.auth_dialog import AuthDialog


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self.setWindowTitle("Muscle Power")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self._build_ui()
        self._update_status_bar()

        # Poll sensor / connection status every 2 s for the status bar
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(2000)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Tab widget ─────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        self._live_page = LiveSessionPage(self._state)
        self._history_page = HistoryPage(self._state)
        self._export_page = ExportPage(self._state)
        self._settings_page = SettingsPage(self._state)

        self._tabs.addTab(self._live_page,     "⚡ Live Session")
        self._tabs.addTab(self._history_page,  "📊 Workout History")
        self._tabs.addTab(self._export_page,   "📁 Export")
        self._tabs.addTab(self._settings_page, "⚙️  Settings")

        # ── Menu bar ───────────────────────────────────────────────────
        menu_bar = self.menuBar()

        app_menu = menu_bar.addMenu("App")
        act_logout = app_menu.addAction("Switch User")
        act_logout.triggered.connect(self._on_switch_user)
        app_menu.addSeparator()
        act_quit = app_menu.addAction("Quit")
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)

        # ── Status bar ─────────────────────────────────────────────────
        self._status_user_label = QLabel()
        self._status_sensor_label = QLabel()
        sb = QStatusBar()
        sb.addWidget(self._status_user_label)
        sb.addPermanentWidget(self._status_sensor_label)
        self.setStatusBar(sb)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _update_status_bar(self) -> None:
        user = self._state.current_display_name or self._state.current_username
        self._status_user_label.setText(f"👤 {user}")

        svc = self._state.sensor_service
        state_str = svc.state if hasattr(svc, "state") else "unknown"
        color = "#3ddc84" if state_str == "connected" else \
                "#FFC107" if state_str == "connecting" else "#888"
        self._status_sensor_label.setText(
            f"<span style='color:{color}'>●</span> Sensor: {state_str}"
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_switch_user(self) -> None:
        """Save current user's settings, then show auth dialog to pick a new user."""
        self._state.save_settings()
        # Pause live scope timer if running
        if hasattr(self._live_page, "pause"):
            self._live_page.pause()
        dlg = AuthDialog(self._state, parent=self)
        if dlg.exec():
            # Notify pages that the user changed
            self._live_page.on_user_changed()
            self._history_page.on_user_changed()
            self._settings_page.on_user_changed()
            self._update_status_bar()

    def closeEvent(self, event) -> None:
        self._state.save_settings()
        self._status_timer.stop()
        super().closeEvent(event)
