"""Simple version-based database migration manager."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from muscle_power.db.database import db_session, get_engine, init_db
from muscle_power.utils.errors import MigrationError
from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)

CURRENT_SCHEMA_VERSION = 4

# SQL for each migration version
MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE IF NOT EXISTS schema_version (
            version  INTEGER NOT NULL,
            applied_at TEXT NOT NULL
        );
    """,
    2: """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            display_name  TEXT,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1
        );
    """,
    3: """
        ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id);
    """,
    4: """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id    INTEGER NOT NULL REFERENCES users(id),
            key        TEXT    NOT NULL,
            value      TEXT,
            updated_at TEXT    NOT NULL,
            PRIMARY KEY (user_id, key)
        );
    """,
}


def _get_schema_version() -> int:
    try:
        with db_session() as session:
            result = session.execute(
                text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            ).fetchone()
            return int(result[0]) if result else 0
    except Exception:
        return 0


def _backup_database(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    db_path = Path(db_url.replace("sqlite:///", ""))
    if not db_path.exists():
        return None
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_suffix(f".backup_{ts}.db")
    shutil.copy2(db_path, backup)
    _log.info("Database backed up to %s", backup)
    return backup


def run_migrations() -> None:
    """Apply pending migrations. Safe to call on every startup."""
    from muscle_power.utils.config import get_config

    cfg = get_config()
    db_url = cfg.database.url
    init_db()

    current = _get_schema_version()
    pending = sorted(v for v in MIGRATIONS if v > current)

    if not pending:
        _log.info("Schema up to date (version=%d)", current)
        return

    backup = _backup_database(db_url)
    engine = get_engine()
    version = 0
    try:
        for version in pending:
            log_action(_log, "db_migration", {"version": version})
            with engine.begin() as conn:
                conn.execute(text(MIGRATIONS[version]))
                conn.execute(
                    text(
                        "INSERT INTO schema_version (version, applied_at) VALUES (:v, :ts)"
                    ),
                    {"v": version, "ts": datetime.now(tz=timezone.utc).isoformat()},
                )
        log_action(_log, "db_migration_complete", {"version": CURRENT_SCHEMA_VERSION})
    except Exception as exc:
        if backup:
            shutil.copy2(backup, Path(db_url.replace("sqlite:///", "")))
            _log.error("Migration failed — backup restored from %s", backup)
        raise MigrationError(
            f"Database upgrade failed (DB_MIG_{version}): {exc}"
        ) from exc
