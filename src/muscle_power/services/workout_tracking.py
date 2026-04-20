"""Workout session lifecycle and history management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from muscle_power.db.database import db_session
from muscle_power.db.models import Session, SessionSummary, SignalData
from muscle_power.utils.errors import DuplicateSessionError, SessionConflictError
from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)


class WorkoutTracker:
    """Manages the lifecycle of a single workout recording session."""

    def __init__(self, db: Any = None) -> None:
        # db is injected in tests; None → use real db_session
        self._db = db
        self._state = "IDLE"
        self._current_session_id: int | None = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        sensor_address: str,
        sensor_name: str = "",
        sampling_rate: int = 250,
        muscle_group: str = "",
        notes: str = "",
        user_id: int | None = None,
    ) -> int:
        if self._state == "RECORDING":
            raise SessionConflictError(
                "A workout session is already in progress. "
                "Stop or save the current session before starting a new one."
            )
        session = Session(
            started_at=datetime.now(tz=timezone.utc),
            sensor_address=sensor_address,
            sensor_name=sensor_name,
            sampling_rate=sampling_rate,
            muscle_group=muscle_group,
            notes=notes,
            user_id=user_id,
        )
        if self._db is not None:
            self._db.save(session)
            self._current_session_id = getattr(session, "id", 0) or 0
        else:
            with db_session() as dbs:
                dbs.add(session)
                dbs.flush()
                self._current_session_id = session.id
        self._state = "RECORDING"
        log_action(_log, "session_started", {
            "session_id": self._current_session_id,
            "sensor": sensor_address,
            "muscle_group": muscle_group,
            "user_id": user_id,
        })
        return self._current_session_id or 0

    def pause_session(self) -> None:
        if self._state == "RECORDING":
            self._state = "PAUSED"

    def resume_session(self) -> None:
        if self._state == "PAUSED":
            self._state = "RECORDING"

    def stop_session(self, summary: dict[str, Any] | None = None) -> None:
        if self._state not in ("RECORDING", "PAUSED"):
            return
        if not self._current_session_id:
            self._state = "SAVED"
            return
        with db_session() as dbs:
            sess = dbs.get(Session, self._current_session_id)
            if sess:
                sess.ended_at = datetime.now(tz=timezone.utc)
                if summary:
                    existing = dbs.get(SessionSummary, self._current_session_id)
                    if not existing:
                        su = SessionSummary(
                            session_id=self._current_session_id,
                            peak_amplitude=summary.get("peak_amplitude"),
                            mean_amplitude=summary.get("mean_amplitude"),
                            duration_seconds=summary.get("duration_seconds"),
                            fatigue_index=summary.get("fatigue_index"),
                            rep_count=summary.get("rep_count"),
                        )
                        dbs.add(su)
        self._state = "SAVED"
        log_action(_log, "session_stopped", {"session_id": self._current_session_id})

    # ------------------------------------------------------------------
    # Persistence helpers (also used directly in tests)
    # ------------------------------------------------------------------

    def save_session(self, session_dict: dict[str, Any]) -> None:
        if self._db is not None:
            self._db.save(session_dict)
            return
        with db_session() as dbs:
            sess = Session(
                started_at=datetime.fromisoformat(
                    session_dict.get("date", datetime.now(tz=timezone.utc).isoformat())
                ),
                sensor_address=session_dict.get("sensor_id", "unknown"),
                sensor_name=session_dict.get("sensor_id", ""),
                sampling_rate=250,
                muscle_group=session_dict.get("muscle_group", ""),
            )
            dbs.add(sess)
            dbs.flush()
            su = SessionSummary(
                session_id=sess.id,
                peak_amplitude=session_dict.get("peak_power"),
                mean_amplitude=session_dict.get("avg_power"),
                duration_seconds=session_dict.get("duration_seconds"),
            )
            dbs.add(su)

    def get_sessions(
        self,
        muscle_group: str | None = None,
        days: int | None = None,
        include_deleted: bool = False,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if self._db is not None:
            return self._db.get_sessions(muscle_group=muscle_group, days=days)
        from sqlalchemy import select

        with db_session() as dbs:
            stmt = select(Session, SessionSummary).outerjoin(
                SessionSummary, SessionSummary.session_id == Session.id
            )
            if not include_deleted:
                stmt = stmt.where(Session.is_deleted.is_(False))
            if muscle_group:
                stmt = stmt.where(Session.muscle_group == muscle_group)
            if days:
                cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
                stmt = stmt.where(Session.started_at >= cutoff)
            if user_id is not None:
                stmt = stmt.where(Session.user_id == user_id)
            stmt = stmt.order_by(Session.started_at)
            rows = dbs.execute(stmt).all()

        return [
            {
                "id": sess.id,
                "date": sess.started_at.isoformat(),
                "ended_at": sess.ended_at.isoformat() if sess.ended_at else None,
                "muscle_group": sess.muscle_group or "",
                "sensor_id": sess.sensor_address,
                "sensor_name": sess.sensor_name or "",
                "notes": sess.notes or "",
                "duration_seconds": summ.duration_seconds if summ else None,
                "avg_power": summ.mean_amplitude if summ else None,
                "peak_power": summ.peak_amplitude if summ else None,
                "fatigue_index": summ.fatigue_index if summ else None,
                "rep_count": summ.rep_count if summ else None,
            }
            for sess, summ in rows
        ]

    def soft_delete_session(self, session_id: int) -> None:
        """Soft-delete a session (recoverable for 30 days)."""
        with db_session() as dbs:
            sess = dbs.get(Session, session_id)
            if sess:
                sess.is_deleted = True
                sess.deleted_at = datetime.now(tz=timezone.utc)
        log_action(_log, "session_soft_deleted", {"session_id": session_id})

    def rename_session(self, session_id: int, new_name: str) -> None:
        """Rename a session (updates muscle_group field used as display name)."""
        with db_session() as dbs:
            sess = dbs.get(Session, session_id)
            if sess:
                sess.muscle_group = new_name
        log_action(_log, "session_renamed", {"session_id": session_id, "new_name": new_name})

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def check_for_duplicate(
        self,
        sensor_address: str,
        start_time: datetime,
        min_duration_seconds: int = 30,
    ) -> None:
        """Raise DuplicateSessionError if a very recent session already exists."""
        from sqlalchemy import select

        with db_session() as dbs:
            cutoff = start_time - timedelta(seconds=min_duration_seconds * 2)
            stmt = (
                select(Session)
                .where(Session.sensor_address == sensor_address)
                .where(Session.started_at >= cutoff)
                .where(Session.is_deleted.is_(False))
                .order_by(Session.started_at.desc())
            )
            recent = dbs.execute(stmt).scalars().first()
        if recent and (start_time - recent.started_at).total_seconds() < min_duration_seconds:
            raise DuplicateSessionError(
                f"This session appears to be a duplicate of the session recorded at "
                f"{recent.started_at.isoformat()}. "
                "Save as new session, merge with existing, or discard?"
            )

    # ------------------------------------------------------------------
    # Bulk signal storage
    # ------------------------------------------------------------------

    def add_signal_batch(self, session_id: int, samples: list[dict[str, Any]]) -> None:
        if not samples:
            return
        with db_session() as dbs:
            dbs.bulk_insert_mappings(
                SignalData,
                [{"session_id": session_id, **s} for s in samples],
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: WorkoutTracker | None = None


def get_tracker() -> WorkoutTracker:
    global _tracker
    if _tracker is None:
        _tracker = WorkoutTracker()
    return _tracker
