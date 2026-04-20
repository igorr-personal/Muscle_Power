"""Per-user settings persistence.

Stores and restores user-configurable session_state keys so each user
gets their own saved configuration across logins.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from muscle_power.db.database import db_session
from muscle_power.db.models import UserSetting
from muscle_power.utils.logger import get_logger

_log = get_logger(__name__)

# Keys that should be persisted per user.
# Only user-controlled preferences — NOT transient runtime state.
PERSISTED_KEYS: list[str] = [
    "sim_mode",
    "slot_active_red",
    "slot_active_blue",
    "slot_active_green",
    "slot_active_white",
    "muscle_en_red",
    "muscle_en_blue",
    "muscle_en_green",
    "muscle_en_white",
    "white_color",
    "scope_scale_mode",
    "scope_vdiv_idx",
    "scope_window",
    "scope_fullscreen",
    "show_envelope",
    "avg_window_sec",
    "wave_smooth",
    "scan_timeout",
    "rec_name",
]

# Canonical default values for every key in PERSISTED_KEYS.
# Used as fallback when a user has no saved settings, e.g. on first login.
# This prevents inheriting another user's session state as defaults.
PANEL_DEFAULTS: dict[str, object] = {
    "sim_mode": False,
    "slot_active_red":   True,
    "slot_active_blue":  True,
    "slot_active_green": False,
    "slot_active_white": False,
    "muscle_en_red":   "Bicep",
    "muscle_en_blue":  "Tricep",
    "muscle_en_green": "Deltoid",
    "muscle_en_white": "Custom",
    "white_color": "#FFFFFF",
    "scope_scale_mode": "Auto",
    "scope_vdiv_idx": 4,          # index into VDIV_STEPS → 2 mV/div
    "scope_window": 800,
    "scope_fullscreen": False,
    "show_envelope": False,
    "avg_window_sec": 0.5,
    "wave_smooth": 1,
    "scan_timeout": 10,
    "rec_name": "Recording",
}


def _serialise(value: object) -> str:
    """Convert a Python value to a JSON string for storage."""
    return json.dumps(value)


def _deserialise(raw: str, reference: object) -> object:
    """Restore the original Python type using *reference* value's type."""
    val = json.loads(raw)
    # Coerce to the same type as the reference (handles bool before int).
    if isinstance(reference, bool):
        return bool(val)
    if isinstance(reference, int):
        return int(val)
    if isinstance(reference, float):
        return float(val)
    return val


def save_user_settings(user_id: int, session_state: dict) -> None:
    """Persist all PERSISTED_KEYS from *session_state* for *user_id*."""
    now = datetime.now(tz=timezone.utc)
    with db_session() as ses:
        for key in PERSISTED_KEYS:
            if key not in session_state:
                continue
            raw = _serialise(session_state[key])
            existing = ses.get(UserSetting, (user_id, key))
            if existing:
                existing.value = raw
                existing.updated_at = now
            else:
                ses.add(UserSetting(
                    user_id=user_id, key=key, value=raw, updated_at=now,
                ))
    _log.debug("Saved %d settings for user %d", len(PERSISTED_KEYS), user_id)


def load_user_settings(user_id: int, defaults: dict) -> dict[str, object]:
    """Return a dict of saved settings for *user_id*.

    Only returns keys present in PERSISTED_KEYS.  For keys without a
    saved value the corresponding *defaults* value is returned so the
    caller always gets the full set.
    """
    result: dict[str, object] = {}
    with db_session() as ses:
        rows = (
            ses.query(UserSetting)
            .filter(
                UserSetting.user_id == user_id,
                UserSetting.key.in_(PERSISTED_KEYS),
            )
            .all()
        )
        saved = {r.key: r.value for r in rows}

    for key in PERSISTED_KEYS:
        if key in saved and saved[key] is not None:
            result[key] = _deserialise(saved[key], defaults.get(key, ""))
        elif key in defaults:
            result[key] = defaults[key]
    return result
