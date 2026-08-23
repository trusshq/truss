"""Knowledge base model (Phase Q): team wiki articles with a public help center.

KBArticle is a tenant-scoped markdown document. Articles are draft until
published; published articles are readable at an unauthenticated endpoint
(/api/public/kb/{slug}) so any workspace can expose a help center. Articles
can optionally link to an object + record.
"""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KBArticle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "kb_articles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)  # draft | published
    # optional link to a record
    object_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
