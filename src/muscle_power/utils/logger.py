"""Structured JSON logging for Muscle Power."""
from __future__ import annotations

import json
import logging
import random
import string
import sys
from datetime import datetime, timezone
from typing import Any


def _generate_correlation_id() -> str:
    date_part = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{date_part}-{rand}"


class StructuredFormatter(logging.Formatter):
    """Emit log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            obj["correlation_id"] = record.correlation_id
        if hasattr(record, "action"):
            obj["action"] = record.action
        if hasattr(record, "details"):
            obj["details"] = record.details
        if hasattr(record, "duration_ms"):
            obj["duration_ms"] = record.duration_ms
        if record.exc_info:
            obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with structured JSON output."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_action(
    logger: logging.Logger,
    action: str,
    details: dict[str, Any] | None = None,
    level: str = "INFO",
    duration_ms: float | None = None,
    correlation_id: str | None = None,
) -> None:
    """Log a structured action event."""
    cid = correlation_id or _generate_correlation_id()
    lvl = getattr(logging, level.upper(), logging.INFO)
    record = logging.LogRecord(
        name=logger.name,
        level=lvl,
        pathname="",
        lineno=0,
        msg=action,
        args=(),
        exc_info=None,
    )
    record.correlation_id = cid  # type: ignore[attr-defined]
    record.action = action  # type: ignore[attr-defined]
    if details is not None:
        record.details = details  # type: ignore[attr-defined]
    if duration_ms is not None:
        record.duration_ms = duration_ms  # type: ignore[attr-defined]
    logger.handle(record)
