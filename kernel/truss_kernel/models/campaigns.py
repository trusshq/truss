"""Campaigns model (Phase AC): marketing campaigns with audience + performance.

Campaign tracks a marketing push across a channel (email/sms/social/ads):
subject/content, audience targeting (a filter description or explicit
recipient count), schedule date, and a lifecycle draft -> scheduled ->
sent -> completed. Performance counters (sent/opened/clicked) are recorded
to compute open/click rates.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campaigns"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # email | sms | social | ads
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email", index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # free-form audience description (e.g. "all active customers in EU")
    audience: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # estimated recipient count for the targeted audience
    audience_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # draft | scheduled | sent | completed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    scheduled_for: Mapped[str] = mapped_column(String(40), nullable=False, default="")  # ISO datetime
    sent_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # performance counters
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
