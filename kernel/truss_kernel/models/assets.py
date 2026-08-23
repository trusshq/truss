"""Assets model (Phase AD): company asset tracking with assignment + lifecycle.

Asset tracks a physical/digital company item (laptop, license, vehicle):
tag, category, purchase cost, purchase date, and an optional assignee
(employee or workspace member). Status moves through available ->
assigned -> maintenance -> retired. AssetHistory records every status or
assignment change for an audit trail.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Asset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # AST-0001
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="General", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # purchase cost in integer cents
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    purchase_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    # available | assigned | maintenance | retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available", index=True)
    # who currently holds it (workspace member id); null when unassigned
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class AssetHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_history"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # created/assigned/returned/maintenance/retired/restored
    detail: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
