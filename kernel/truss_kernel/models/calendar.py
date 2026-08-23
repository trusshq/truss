"""Calendar model (Phase P): workspace events with attendees and reminders.

CalendarEvent is a tenant-scoped scheduled item (meeting, call, deadline).
It can optionally link to an object + record (e.g. a deal review meeting) so
any record can carry a schedule. Attendees are stored as a JSON list of user
ids; reminders are declarative (minutes before).
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CalendarEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "calendar_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ISO-8601 UTC strings; end may be None for all-day / open-ended
    starts_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    ends_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # list of user UUID strings invited
    attendees: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # optional link to a record (object slug + record id)
    object_slug: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
