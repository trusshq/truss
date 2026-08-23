"""File storage model (Phase O): tenant files, optionally attached to records.

Files are stored on local disk under settings.storage_dir/<tenant_id>/<id>.
The DB row carries metadata (name, size, content type) and an optional link
to an object + record so any record can have attachments.
"""
import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoredFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stored_files"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False, default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # optional attachment target
    object_slug: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
