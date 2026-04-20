"""Authentication dialog — shown at startup before the main window.

No password required: users pick their display name from a list, or
create a new account here.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout, QSizePolicy,
    QMessageBox, QFrame,
)

from muscle_power_desktop.app import AppState
from muscle_power.services.auth_service import UserExistsError


class AuthDialog(QDialog):
    """Login / register dialog."""

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self.setWindowTitle("Muscle Power — Select Account")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()
        self._refresh_users()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(28, 28, 28, 28)

        # Title
        title = QLabel("💪 Muscle Power")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("Choose your account to continue")
        subtitle.setObjectName("dimLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.12);")
        root.addWidget(sep)

        # ── Login section ──────────────────────────────────────────────
        login_box = QGroupBox("Select account")
        login_layout = QVBoxLayout(login_box)
        login_layout.setSpacing(8)

        self._user_combo = QComboBox()
        self._user_combo.setMinimumHeight(34)
        login_layout.addWidget(self._user_combo)

        self._no_users_label = QLabel("No accounts yet — create one below.")
        self._no_users_label.setObjectName("dimLabel")
        self._no_users_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_users_label.hide()
        login_layout.addWidget(self._no_users_label)

        btn_enter = QPushButton("▶  Enter")
        btn_enter.setObjectName("primaryBtn")
        btn_enter.setMinimumHeight(36)
        btn_enter.clicked.connect(self._on_login)
        login_layout.addWidget(btn_enter)

        root.addWidget(login_box)

        # ── Register section ───────────────────────────────────────────
        reg_box = QGroupBox("➕  Create new account")
        reg_box.setCheckable(True)
        reg_box.setChecked(False)
        self._reg_box = reg_box
        reg_layout = QFormLayout(reg_box)
        reg_layout.setSpacing(8)

        self._uname_edit = QLineEdit()
        self._uname_edit.setPlaceholderText("e.g. alex")
        reg_layout.addRow("Username *", self._uname_edit)

        self._display_edit = QLineEdit()
        self._display_edit.setPlaceholderText("e.g. Alex (optional)")
        reg_layout.addRow("Display name", self._display_edit)

        btn_reg = QPushButton("Create Account")
        btn_reg.setObjectName("primaryBtn")
        btn_reg.clicked.connect(self._on_register)
        reg_layout.addRow("", btn_reg)

        root.addWidget(reg_box)

        # ── Cancel ────────────────────────────────────────────────────
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        root.addWidget(btn_cancel)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _refresh_users(self) -> None:
        users = self._state.list_users()
        self._users = users
        self._user_combo.clear()
        if users:
            self._user_combo.addItems([u["display_name"] for u in users])
            self._user_combo.show()
            self._no_users_label.hide()
            # Auto-expand register box only if no users exist
            self._reg_box.setChecked(False)
        else:
            self._user_combo.hide()
            self._no_users_label.show()
            self._reg_box.setChecked(True)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_login(self) -> None:
        idx = self._user_combo.currentIndex()
        if idx < 0 or idx >= len(self._users):
            QMessageBox.warning(self, "No account", "Please select an account first.")
            return
        user = self._users[idx]
        self._state.login(user)
        self.accept()

    def _on_register(self) -> None:
        username = self._uname_edit.text().strip()
        display_name = self._display_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "Validation", "Username is required.")
            self._uname_edit.setFocus()
            return
        try:
            self._state.register_and_login(username, display_name)
            self.accept()
        except UserExistsError as exc:
            QMessageBox.critical(self, "Username taken", str(exc))
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
