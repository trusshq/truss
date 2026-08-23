"""Time tracking model (Phase R): time entries with optional live timers.

TimeEntry logs work against an optional object + record (e.g. a deal or
ticket). An entry is either a completed log (started_at + duration_minutes)
or a running timer (started_at set, stopped_at null, duration computed live).
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TimeEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "time_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # ISO-8601 UTC; stopped_at null => running timer
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    stopped_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # optional link to a record
    object_slug: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
