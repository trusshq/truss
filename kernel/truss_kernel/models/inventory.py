"""Inventory model (Phase U): products with stock levels and adjustments.

Product is a sellable/trackable item with SKU, pricing, and stock quantity.
StockAdjustment records every change to a product's quantity (in/out/set)
with a reason, giving a full audit trail of stock movement. Low-stock
thresholds flag products that need reordering.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="General", index=True)
    # price in integer cents
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # stock
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class StockAdjustment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stock_adjustments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # kind: in (receive), out (ship/consume), set (absolute correction)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    adjusted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # resulting quantity after this adjustment (snapshot for the audit trail)
    resulting_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
