"""Quotes model (Phase Y): sales quotes with line items and a lifecycle.

Quote moves through draft -> sent -> accepted | declined -> (accepted can
convert to an invoice record). Each quote carries line items (description,
quantity, unit price in cents) and computed totals. Optionally links to a
CRM contact/company record and the customer name.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Quote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "quotes"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # QT-0001
    customer_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # optional link to a CRM record (object slug + record id)
    object: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    # draft | sent | accepted | declined | converted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    valid_until: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    # line items: [{description, quantity, unit_price_cents}]
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # totals (denormalized for fast reads; recomputed on save)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # set when converted to an invoice record
    invoice_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
