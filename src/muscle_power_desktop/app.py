"""Application state singleton for the desktop app.

Replaces Streamlit's st.session_state + @st.cache_resource pattern.
Holds: current user, service singletons, and per-user panel settings.
"""
from __future__ import annotations

from typing import Optional

from muscle_power.services.auth_service import list_users, register_user, UserExistsError
from muscle_power.services.sensor_service import CallibriService, get_sensor_service
from muscle_power.services.workout_tracking import WorkoutTracker, get_tracker
from muscle_power.services.user_settings import (
    PANEL_DEFAULTS,
    PERSISTED_KEYS,
    load_user_settings,
    save_user_settings,
)
from muscle_power.utils.config import get_config
from muscle_power.utils.logger import get_logger

_log = get_logger(__name__)


class AppState:
    """Central state container shared across all desktop pages."""

    def __init__(self) -> None:
        # ── Auth ──────────────────────────────────────────────────────────
        self.current_user_id: Optional[int] = None
        self.current_username: str = ""
        self.current_display_name: str = ""

        # ── Panel / display settings (persisted per user) ─────────────────
        # Start from canonical defaults; overwritten on login.
        self.settings: dict[str, object] = dict(PANEL_DEFAULTS)

        # ── Service singletons ────────────────────────────────────────────
        self.sensor_service: CallibriService = get_sensor_service()
        self.tracker: WorkoutTracker = get_tracker()
        self.config = get_config()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        return self.current_user_id is not None

    def login(self, user: dict) -> None:
        """Set the active user and restore their saved settings."""
        self.current_user_id = user["id"]
        self.current_username = user["username"]
        self.current_display_name = user["display_name"]
        saved = load_user_settings(user["id"], PANEL_DEFAULTS)
        self.settings = {**PANEL_DEFAULTS, **saved}
        _log.info("Logged in as %s (id=%d)", user["display_name"], user["id"])

    def logout(self) -> None:
        """Clear auth state; service singletons are kept alive."""
        self.save_settings()
        self.current_user_id = None
        self.current_username = ""
        self.current_display_name = ""
        self.settings = dict(PANEL_DEFAULTS)
        _log.info("Logged out")

    def register_and_login(self, username: str, display_name: str = "") -> dict:
        """Register a new user, seed defaults, and log in.

        Returns the new user dict.  Raises UserExistsError if taken.
        """
        user = register_user(username, display_name=display_name)
        save_user_settings(user["id"], PANEL_DEFAULTS)
        self.login(user)
        return user

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def get(self, key: str, default: object = None) -> object:
        return self.settings.get(key, default)

    def set(self, key: str, value: object) -> None:
        self.settings[key] = value

    def save_settings(self) -> None:
        """Persist current settings to DB for the active user."""
        if self.current_user_id is None:
            return
        save_user_settings(self.current_user_id, self.settings)

    def list_users(self) -> list[dict]:
        return list_users()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_app_state: Optional[AppState] = None


def get_app_state() -> AppState:
    """Return the process-wide AppState singleton."""
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state
