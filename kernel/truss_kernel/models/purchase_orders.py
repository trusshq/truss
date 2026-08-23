"""Purchase orders model (Phase Z): procurement orders that receive into inventory.

PurchaseOrder moves through draft -> sent -> received | cancelled. Each order
carries line items referencing inventory products (product_id, quantity,
unit_cost_cents). Receiving an order applies a stock 'in' adjustment to each
referenced product, closing the procurement -> inventory loop.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PurchaseOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # PO-0001
    vendor_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    # draft | sent | received | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    expected_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    # line items: [{product_id, description, quantity, unit_cost_cents}]
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    received_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
