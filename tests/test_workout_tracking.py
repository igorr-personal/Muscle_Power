"""Tests for workout_tracking.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from muscle_power.services.workout_tracking import WorkoutTracker
from muscle_power.utils.errors import DuplicateSessionError, SessionConflictError


class TestWorkoutTracker:
    """Tests using the real in-memory SQLite DB (initialised by conftest)."""

    def test_start_and_stop_session(self):
        tracker = WorkoutTracker()
        sid = tracker.start_session(
            sensor_address="AA:BB:CC:DD:EE:FF",
            muscle_group="biceps",
        )
        assert sid > 0
        assert tracker.state == "RECORDING"
        tracker.stop_session({"peak_amplitude": 0.002, "mean_amplitude": 0.001, "duration_seconds": 30.0})
        assert tracker.state == "SAVED"

    def test_double_start_raises_conflict(self):
        tracker = WorkoutTracker()
        tracker.start_session(sensor_address="AA:BB:CC:DD:EE:FF")
        with pytest.raises(SessionConflictError, match="already in progress"):
            tracker.start_session(sensor_address="AA:BB:CC:DD:EE:FF")

    def test_pause_and_resume(self):
        tracker = WorkoutTracker()
        tracker.start_session(sensor_address="AA:BB:CC:DD:EE:01")
        tracker.pause_session()
        assert tracker.state == "PAUSED"
        tracker.resume_session()
        assert tracker.state == "RECORDING"
        tracker.stop_session()

    def test_save_and_retrieve_session(self):
        tracker = WorkoutTracker()
        now = datetime.now(tz=timezone.utc)
        tracker.save_session({
            "date": now.isoformat(),
            "muscle_group": "quads",
            "sensor_id": "BB:CC:DD:EE:FF:01",
            "avg_power": 0.75,
            "peak_power": 1.2,
            "duration_seconds": 300,
        })
        sessions = tracker.get_sessions(muscle_group="quads")
        assert len(sessions) >= 1
        assert any(s.get("muscle_group") == "quads" for s in sessions)

    def test_get_sessions_compare_power(self):
        """Sessions retrieved in date order should show power progression."""
        tracker = WorkoutTracker()
        now = datetime.now(tz=timezone.utc)
        tracker.save_session({
            "date": (now - timedelta(days=7)).isoformat(),
            "muscle_group": "test_bicep",
            "sensor_id": "Callibri_MF_001",
            "avg_power": 0.60,
            "peak_power": 1.0,
            "duration_seconds": 300,
        })
        tracker.save_session({
            "date": now.isoformat(),
            "muscle_group": "test_bicep",
            "sensor_id": "Callibri_MF_001",
            "avg_power": 0.75,
            "peak_power": 1.2,
            "duration_seconds": 300,
        })
        sessions = tracker.get_sessions(muscle_group="test_bicep", days=30)
        assert len(sessions) >= 2
        # Most recent should have higher avg_power
        avgs = [s["avg_power"] for s in sessions if s.get("avg_power") is not None]
        assert avgs[-1] >= avgs[0]

    def test_soft_delete_session(self):
        tracker = WorkoutTracker()
        sid = tracker.start_session(sensor_address="CC:DD:EE:FF:00:01", muscle_group="traps")
        tracker.stop_session()
        tracker.soft_delete_session(sid)
        sessions = tracker.get_sessions(muscle_group="traps")
        assert all(s.get("id") != sid for s in sessions)


class TestWorkoutTrackerWithMock:
    """Tests with injected DB mock (unit-test style)."""

    def test_save_session_calls_db(self):
        db = MagicMock()
        tracker = WorkoutTracker(db=db)
        payload = {
            "date": datetime.now(tz=timezone.utc).isoformat(),
            "muscle_group": "biceps",
            "avg_power": 0.75,
            "peak_power": 1.2,
            "duration_seconds": 300,
            "sensor_id": "Callibri_MF_001",
        }
        tracker.save_session(payload)
        db.save.assert_called_once()

    def test_get_sessions_calls_db(self):
        db = MagicMock()
        db.get_sessions.return_value = [
            {"date": "2025-01-01T10:00:00", "avg_power": 0.6, "muscle_group": "biceps"},
            {"date": "2025-01-08T10:00:00", "avg_power": 0.75, "muscle_group": "biceps"},
        ]
        tracker = WorkoutTracker(db=db)
        sessions = tracker.get_sessions(muscle_group="biceps", days=30)
        assert len(sessions) == 2
        assert sessions[1]["avg_power"] > sessions[0]["avg_power"]
