"""Connectors: user-owned bridges to external systems (BYO-everything).

A connector is a tenant-scoped, admin-managed config blob:
- webhook  : forward kernel events to an external URL (BYO-analytics!)
- postgres : read-only access to an external Postgres/Neon database
- s3       : object storage (adapter lands later)
- smtp     : outbound email (adapter lands later)

The whole config is encrypted at rest with the same vault as AI keys.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Connector(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connector_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(40))  # webhook | postgres | s3 | smtp
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_enc: Mapped[str] = mapped_column(Text, default="")  # encrypted JSON
    description: Mapped[str] = mapped_column(String(300), default="")


class WebhookDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Outbox row per (event x webhook connector). Delivered after commit."""

    __tablename__ = "webhook_deliveries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    event_type: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|success|failed
    attempts: Mapped[int] = mapped_column(default=0)
    last_http_status: Mapped[int | None] = mapped_column(default=None)
    last_error: Mapped[str] = mapped_column(Text, default="")
