"""Billing models (Phase L): subscriptions, invoices, usage snapshots.

Self-hosted-first: checkout is a mock payment flow (no external PSP), but the
data model is real — plans, seat-based pricing, period tracking, invoices, and
hard usage limits enforced at the kernel chokepoints.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    plan: Mapped[str] = mapped_column(String(30), nullable=False, default="free")  # free | pro | business
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")  # active | canceled
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "invoices"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False)  # INV-0001
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paid")  # paid | open | void
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lines: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"description": ..., "qty": ..., "unit_cents": ...}
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
