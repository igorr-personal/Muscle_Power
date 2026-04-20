"""User authentication service — user management without passwords."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from muscle_power.db.database import db_session
from muscle_power.db.models import User
from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UserExistsError(Exception):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_users() -> list[dict]:
    """Return a list of all active users ordered by display name."""
    with db_session() as dbs:
        users = dbs.execute(
            select(User).where(User.is_active.is_(True)).order_by(User.display_name)
        ).scalars().all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name or u.username,
                "created_at": u.created_at,
            }
            for u in users
        ]


def register_user(username: str, display_name: str = "") -> dict:
    """Create a new user (no password).  Raises UserExistsError if username is taken."""
    username = username.strip().lower()
    if not username:
        raise ValueError("Username cannot be empty.")
    with db_session() as dbs:
        existing = dbs.execute(
            select(User).where(User.username == username)
        ).scalars().first()
        if existing:
            raise UserExistsError(f"Username '{username}' is already taken.")
        user = User(
            username=username,
            display_name=display_name.strip() or username,
            password_hash="",
            created_at=datetime.now(tz=timezone.utc),
            is_active=True,
        )
        dbs.add(user)
        dbs.flush()
        new_id = user.id
        new_display = user.display_name or username
    log_action(_log, "user_registered", {"username": username})
    return {"id": new_id, "username": username, "display_name": new_display}


def get_user(user_id: int) -> Optional[dict]:
    """Return user dict or None."""
    with db_session() as dbs:
        user = dbs.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
        }


def update_display_name(user_id: int, display_name: str) -> None:
    with db_session() as dbs:
        user = dbs.get(User, user_id)
        if user:
            user.display_name = display_name.strip()
    log_action(_log, "display_name_updated", {"user_id": user_id})


def delete_user(user_id: int) -> None:
    """Soft-delete a user by setting is_active=False."""
    with db_session() as dbs:
        user = dbs.get(User, user_id)
        if user:
            user.is_active = False
    log_action(_log, "user_deleted", {"user_id": user_id})

    change_password = staticmethod(change_password)
    update_display_name = staticmethod(update_display_name)
    list_users = staticmethod(list_users)


def get_auth_service() -> _AuthService:
    global _service_instance
    if _service_instance is None:
        _service_instance = _AuthService()
    return _service_instance
