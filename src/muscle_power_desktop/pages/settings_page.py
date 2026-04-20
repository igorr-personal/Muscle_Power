"""Settings page for the desktop app — sensor, application, account, about."""
from __future__ import annotations

import yaml
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, QSlider,
    QPushButton, QSpinBox, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt

from muscle_power_desktop.app import AppState
from muscle_power.utils.config import get_config, reset_config
from muscle_power.services.auth_service import (
    update_display_name, delete_user, list_users,
)


_CONFIG_PATH = Path("config.yaml")


def _save_yaml(updates: dict) -> None:
    """Merge *updates* into config.yaml and reload config."""
    raw: dict = {}
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    def _deep_merge(base: dict, patch: dict) -> dict:
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    _deep_merge(raw, updates)
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False)
    reset_config()


class SettingsPage(QWidget):
    """QTabWidget with four settings tabs."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("⚙️ Settings")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_sensor_tab(), "🔵 Sensor")
        tabs.addTab(self._build_app_tab(), "🖥️ Application")
        tabs.addTab(self._build_account_tab(), "👤 Account")
        tabs.addTab(self._build_about_tab(), "ℹ️ About")
        root.addWidget(tabs)

    # ------------------------------------------------------------------
    # Sensor tab
    # ------------------------------------------------------------------

    def _build_sensor_tab(self) -> QWidget:
        cfg = get_config()
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)
        form.setContentsMargins(12, 12, 12, 12)

        self._pref_addr = QLineEdit(cfg.sensor.preferred_address)
        self._pref_addr.setPlaceholderText("AA:BB:CC:DD:EE:FF — leave blank to select manually")
        form.addRow("Preferred sensor address:", self._pref_addr)

        self._fs_combo = QComboBox()
        fs_options = [125, 250, 500, 1000, 2000]
        self._fs_combo.addItems([str(f) for f in fs_options])
        idx = fs_options.index(cfg.sensor.sampling_frequency) if cfg.sensor.sampling_frequency in fs_options else 1
        self._fs_combo.setCurrentIndex(idx)
        form.addRow("Sampling frequency (Hz):", self._fs_combo)

        self._sig_type_combo = QComboBox()
        sig_types = ["EMG", "EEG", "ECG", "EDA"]
        self._sig_type_combo.addItems(sig_types)
        t_idx = sig_types.index(cfg.sensor.signal_type) if cfg.sensor.signal_type in sig_types else 0
        self._sig_type_combo.setCurrentIndex(t_idx)
        form.addRow("Signal type:", self._sig_type_combo)

        self._display_w_spin = QSpinBox()
        self._display_w_spin.setRange(2, 30)
        self._display_w_spin.setSuffix(" s")
        self._display_w_spin.setValue(cfg.sensor.display_window_seconds)
        form.addRow("Live display window:", self._display_w_spin)

        self._rms_spin = QSpinBox()
        self._rms_spin.setRange(50, 1000)
        self._rms_spin.setSingleStep(25)
        self._rms_spin.setSuffix(" ms")
        self._rms_spin.setValue(cfg.sensor.rms_window_ms)
        form.addRow("RMS envelope window:", self._rms_spin)

        self._batt_warn_spin = QSpinBox()
        self._batt_warn_spin.setRange(10, 50)
        self._batt_warn_spin.setSuffix(" %")
        self._batt_warn_spin.setValue(cfg.sensor.battery_warn_pct)
        form.addRow("Battery yellow warning:", self._batt_warn_spin)

        self._batt_alert_spin = QSpinBox()
        self._batt_alert_spin.setRange(5, 20)
        self._batt_alert_spin.setSuffix(" %")
        self._batt_alert_spin.setValue(cfg.sensor.battery_alert_pct)
        form.addRow("Battery red alert:", self._batt_alert_spin)

        save_btn = QPushButton("💾 Save Sensor Settings")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save_sensor)
        form.addRow("", save_btn)
        return w

    # ------------------------------------------------------------------
    # Application tab
    # ------------------------------------------------------------------

    def _build_app_tab(self) -> QWidget:
        cfg = get_config()
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)
        form.setContentsMargins(12, 12, 12, 12)

        self._log_level_combo = QComboBox()
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        self._log_level_combo.addItems(levels)
        lvl_idx = levels.index(cfg.log_level) if cfg.log_level in levels else 1
        self._log_level_combo.setCurrentIndex(lvl_idx)
        form.addRow("Log level:", self._log_level_combo)

        self._db_url_edit = QLineEdit(cfg.database.url)
        form.addRow("Database URL:", self._db_url_edit)

        self._min_sess_spin = QSpinBox()
        self._min_sess_spin.setRange(5, 300)
        self._min_sess_spin.setSuffix(" s")
        self._min_sess_spin.setValue(cfg.session.min_duration_seconds)
        form.addRow("Min session duration:", self._min_sess_spin)

        save_btn = QPushButton("💾 Save App Settings")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save_app)
        form.addRow("", save_btn)

        note = QLabel("⚠️ Log-level changes take effect after restart.")
        note.setObjectName("dimLabel")
        form.addRow("", note)
        return w

    # ------------------------------------------------------------------
    # Account tab
    # ------------------------------------------------------------------

    def _build_account_tab(self) -> QWidget:
        w = QWidget()
        self._account_layout = QVBoxLayout(w)
        self._account_layout.setContentsMargins(12, 12, 12, 12)
        self._account_layout.setSpacing(10)
        self._rebuild_account_tab()
        return w

    def _rebuild_account_tab(self) -> None:
        # Clear existing widgets
        while self._account_layout.count():
            item = self._account_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # My account
        my_box = QGroupBox("My Account")
        my_form = QFormLayout(my_box)

        user = self._state.current_display_name or self._state.current_username
        my_form.addRow("Username:", QLabel(f"<b>{self._state.current_username}</b>"))
        my_form.addRow("Display name:", QLabel(f"<b>{user}</b>"))

        self._new_display_edit = QLineEdit(
            self._state.current_display_name or self._state.current_username
        )
        my_form.addRow("New display name:", self._new_display_edit)

        rename_btn = QPushButton("✏️ Update Name")
        rename_btn.clicked.connect(self._on_rename)
        my_form.addRow("", rename_btn)
        self._account_layout.addWidget(my_box)

        # All users
        users_box = QGroupBox("All Users")
        users_layout = QVBoxLayout(users_box)
        try:
            all_users = list_users()
        except Exception:
            all_users = []
        for u in all_users:
            row_frame = QFrame()
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"{u['display_name']} (#{u['id']})")
            row.addWidget(lbl, stretch=1)
            if u["id"] != self._state.current_user_id:
                del_btn = QPushButton("🗑")
                del_btn.setObjectName("dangerBtn")
                del_btn.setFixedWidth(36)
                del_btn.setToolTip(f"Delete user {u['display_name']}")
                uid = u["id"]
                del_btn.clicked.connect(lambda _, uId=uid, uName=u["display_name"]: self._on_delete_user(uId, uName))
                row.addWidget(del_btn)
            users_layout.addWidget(row_frame)
        self._account_layout.addWidget(users_box)
        self._account_layout.addStretch()

    # ------------------------------------------------------------------
    # About tab
    # ------------------------------------------------------------------

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(QLabel("💪 <b>Muscle Power</b>", w))
        layout.addWidget(QLabel("Version 0.1.0 — Desktop Edition"))
        layout.addWidget(QLabel("EMG sensor real-time visualiser"))
        layout.addWidget(QLabel("Powered by PyQt6 + pyqtgraph + pyneurosdk2"))
        layout.addWidget(QLabel(
            "<a href='https://github.com'>GitHub</a> &nbsp;|&nbsp; "
            "SQLite database: muscle_power.db"
        ))
        layout.addStretch()
        return w

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_save_sensor(self) -> None:
        try:
            _save_yaml({
                "sensor": {
                    "preferred_address": self._pref_addr.text().strip(),
                    "sampling_frequency": int(self._fs_combo.currentText()),
                    "signal_type": self._sig_type_combo.currentText(),
                    "display_window_seconds": self._display_w_spin.value(),
                    "rms_window_ms": self._rms_spin.value(),
                    "battery_warn_pct": self._batt_warn_spin.value(),
                    "battery_alert_pct": self._batt_alert_spin.value(),
                }
            })
            QMessageBox.information(self, "Saved", "Sensor settings saved.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{exc}")

    def _on_save_app(self) -> None:
        try:
            _save_yaml({
                "log_level": self._log_level_combo.currentText(),
                "database": {"url": self._db_url_edit.text().strip()},
                "session": {"min_duration_seconds": self._min_sess_spin.value()},
            })
            QMessageBox.information(self, "Saved",
                                    "Application settings saved. "
                                    "Restart the app to apply log-level changes.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{exc}")

    def _on_rename(self) -> None:
        new_name = self._new_display_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Validation", "Display name cannot be empty.")
            return
        try:
            update_display_name(self._state.current_user_id, new_name)
            self._state.current_display_name = new_name
            QMessageBox.information(self, "Updated", f"Display name changed to: {new_name}")
            self._rebuild_account_tab()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_delete_user(self, user_id: int, display_name: str) -> None:
        reply = QMessageBox.question(
            self, "Confirm delete",
            f"Delete user '{display_name}' and all their sessions?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_user(user_id)
            self._rebuild_account_tab()
            QMessageBox.information(self, "Deleted", f"User '{display_name}' deleted.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    # ------------------------------------------------------------------
    # User switch hook
    # ------------------------------------------------------------------

    def on_user_changed(self) -> None:
        self._rebuild_account_tab()
