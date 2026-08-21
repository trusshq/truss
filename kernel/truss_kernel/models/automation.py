"""Automation run history: every fired rule leaves an auditable row."""
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "automation_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    plugin_id: Mapped[str] = mapped_column(String(120))
    automation_slug: Mapped[str] = mapped_column(String(120))
    trigger_event: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="success")  # success | error
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
