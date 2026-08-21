"""AI key model: one or more named provider configs per tenant."""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_aikey_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), default="default")
    provider: Mapped[str] = mapped_column(String(80), default="openai-compatible")
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(120))
    api_key_enc: Mapped[str] = mapped_column(String(2000), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
