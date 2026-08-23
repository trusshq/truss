"""Public forms model (Phase N): shareable intake forms backed by an object.

A PublicForm exposes a subset of an object's fields at an unauthenticated
endpoint (/api/public/forms/{slug}). Submissions create real records through
the same validated path as the API, so automations and AI triggers fire.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PublicForm(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "public_forms"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)  # public token
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    object_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    # ordered list of field slugs to expose; empty = all non-hidden fields
    fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    submissions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
