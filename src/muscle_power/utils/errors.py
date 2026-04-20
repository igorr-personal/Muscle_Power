"""Custom exceptions for the Muscle Power application."""
from __future__ import annotations


class MusclePowerError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id


class SensorNotFoundError(MusclePowerError):
    """Raised when no Callibri sensor is found during BLE scan."""


class SensorConnectionError(MusclePowerError):
    """Raised when a sensor connection fails or drops."""


class SensorNotAvailableError(MusclePowerError):
    """Raised when sensor is in maintenance or unavailable state."""


class SDKNotInstalledError(MusclePowerError):
    """Raised when pyneurosdk2 library is not installed."""


class SignalProcessingError(MusclePowerError):
    """Raised when signal processing fails (bad input, NaN, etc.)."""


class DatabaseError(MusclePowerError):
    """Raised when a database operation fails."""


class MigrationError(DatabaseError):
    """Raised when a database migration fails."""


class SessionConflictError(MusclePowerError):
    """Raised when conflicting workout sessions are detected."""


class DuplicateSessionError(MusclePowerError):
    """Raised when a near-duplicate session is detected."""


class ExportError(MusclePowerError):
    """Raised when exporting data fails."""


class DataImportError(MusclePowerError):
    """Raised when importing data fails."""


class ValidationError(MusclePowerError):
    """Raised when input validation fails."""


class ConfigError(MusclePowerError):
    """Raised when configuration is invalid or missing."""


class InvalidStatusTransitionError(MusclePowerError):
    """Raised when an invalid sensor status transition is attempted."""
