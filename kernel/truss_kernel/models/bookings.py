"""Bookings model (Phase AF): appointment scheduling with services.

BookingService defines an offerable appointment type (name, duration in
minutes, price in cents, active flag). Booking ties a customer to a service
at a start time with a lifecycle pending -> confirmed -> completed |
cancelled | no_show. Overlap detection prevents double-booking.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BookingService(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "booking_services"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # price per appointment in integer cents
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # whether new bookings can be made on this service
    active: Mapped[bool] = mapped_column(default=True)


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bookings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("booking_services.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(300), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # ISO datetime the appointment starts; end = start + service duration
    start_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    end_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # pending | confirmed | completed | cancelled | no_show
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
