"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _in_memory_db():
    """Use an in-memory SQLite DB for all tests."""
    import os
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from muscle_power.db.database import get_engine, init_db, reset_engine
    reset_engine()
    init_db()
    yield
    reset_engine()
