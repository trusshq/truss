"""Plugin installation state per tenant + event store."""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PluginInstall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A plugin enabled/disabled for a tenant. Manifest itself comes from disk."""

    __tablename__ = "plugin_installs"
    __table_args__ = (UniqueConstraint("tenant_id", "plugin_id", name="uq_plugininstall_tenant_plugin"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="0.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # user-supplied plugin settings (e.g. BYOK keys reference names, feature flags)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class EventLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Internal event seam: every meaningful action lands here.

    Feeds (later) analytics forwarding, automation triggers, and AI context.
    """

    __tablename__ = "event_log"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)  # e.g. record.created
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
