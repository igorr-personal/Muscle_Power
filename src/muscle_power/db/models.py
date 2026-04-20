"""SQLAlchemy ORM models for Muscle Power."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """Application user — each user has their own workout history."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sensor_address: Mapped[str] = mapped_column(String(64), nullable=False)
    sensor_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sampling_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=250)
    muscle_group: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[Optional[User]] = relationship("User", back_populates="sessions")
    signal_data: Mapped[List["SignalData"]] = relationship(
        "SignalData", back_populates="session", cascade="all, delete-orphan"
    )
    summary: Mapped[Optional["SessionSummary"]] = relationship(
        "SessionSummary", back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class SignalData(Base):
    __tablename__ = "signal_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    envelope_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="signal_data")


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.id"), primary_key=True
    )
    peak_amplitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_amplitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fatigue_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rep_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="summary")


class SensorRecord(Base):
    """Known sensors the user has previously connected to."""

    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    availability_status: Mapped[str] = mapped_column(String(32), default="available")
    maintenance_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)


class StatusHistory(Base):
    """Audit log for sensor availability status transitions."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_address: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    """Key-value store for persistent user preferences."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UserSetting(Base):
    """Per-user key-value store for user-specific configuration."""

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class KBDocument(Base):
    """Knowledge base document index entry."""

    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
