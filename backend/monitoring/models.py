from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), str: Text}


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint("interval_seconds BETWEEN 5 AND 3600", name="monitor_interval_range"),
        CheckConstraint(
            "timeout_seconds > 0 AND timeout_seconds < interval_seconds", name="monitor_timeout_range"
        ),
        CheckConstraint("expected_status BETWEEN 100 AND 599", name="monitor_status_range"),
        CheckConstraint("enabled = (next_run_at IS NOT NULL)", name="monitor_schedule_enabled"),
        Index("ix_monitors_due", "next_run_at", "id", postgresql_where=text("enabled")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str]
    method: Mapped[str] = mapped_column(server_default="GET")
    request_headers: Mapped[dict[str, str]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    request_body: Mapped[str | None]
    interval_seconds: Mapped[int]
    expected_status: Mapped[int]
    timeout_seconds: Mapped[float]
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime]
    next_run_at: Mapped[datetime | None]
    awaiting_since: Mapped[datetime | None]
    generation: Mapped[int] = mapped_column(default=0)
    failure_streak: Mapped[int] = mapped_column(default=0)
    first_failure_at: Mapped[datetime | None]
    recovery_streak: Mapped[int] = mapped_column(default=0)

    @property
    def has_request_headers(self) -> bool:
        return bool(self.request_headers)

    @property
    def has_request_body(self) -> bool:
        return self.request_body is not None


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        UniqueConstraint("monitor_id", "scheduled_at", name="uq_check_monitor_slot"),
        Index("ix_checks_monitor_started", "monitor_id", "started_at", "id"),
        CheckConstraint("elapsed_ms >= 0", name="check_elapsed_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    scheduled_at: Mapped[datetime]
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime]
    elapsed_ms: Mapped[int]
    success: Mapped[bool]
    http_status: Mapped[int | None]
    failure_reason: Mapped[str | None]
    gap_before: Mapped[bool]
    generation: Mapped[int]


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "uq_incident_monitor_open", "monitor_id", unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("ix_incidents_monitor_confirmed", "monitor_id", "confirmed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    first_failure_at: Mapped[datetime]
    confirmed_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("incident_id", "event_type", name="uq_notification_incident_event"),
        CheckConstraint("event_type IN ('outage', 'recovery')", name="notification_event_type"),
        Index("ix_notifications_created", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"))
    event_type: Mapped[str]
    created_at: Mapped[datetime]
    message: Mapped[str]
