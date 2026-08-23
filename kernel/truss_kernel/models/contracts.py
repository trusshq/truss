"""Contracts model (Phase AA): contract lifecycle with renewal tracking.

Contract tracks an agreement with a customer or vendor: value, start/end
dates, auto-renew flag, and renewal notice window. Status moves through
draft -> active -> expired | cancelled. Optionally links to a CRM record.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Contract(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "contracts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # CT-0001
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # optional link to a CRM record (object slug + record id)
    object: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    value_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # draft | active | expired | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # days before end_date to flag for renewal
    renewal_notice_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
