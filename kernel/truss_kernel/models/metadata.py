"""Metadata-driven data layer: ObjectDef + FieldDef.

Objects and fields are DATA, not DDL. Actual records live in `records`
with dynamic field values stored as JSONB. This is the kernel's heart:
plugins (and users) declare new business objects without migrations.
"""
import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FieldType(str, PyEnum):
    text = "text"
    textarea = "textarea"
    number = "number"
    currency = "currency"
    boolean = "boolean"
    date = "date"
    datetime = "datetime"
    email = "email"
    phone = "phone"
    url = "url"
    select = "select"        # options stored in field.options
    multiselect = "multiselect"
    relation = "relation"    # points at another ObjectDef via field.related_object_id
    user = "user"            # references users.id


class ObjectDef(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A business object (e.g. 'lead', 'invoice') declared as metadata."""

    __tablename__ = "object_defs"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_objectdef_tenant_slug"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_plural: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="📦")
    # which plugin created it ('' = user-created / kernel)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fields: Mapped[list["FieldDef"]] = relationship(
        back_populates="object", cascade="all, delete-orphan", order_by="FieldDef.position"
    )


class FieldDef(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "field_defs"
    __table_args__ = (UniqueConstraint("object_id", "slug", name="uq_fielddef_object_slug"),)

    object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("object_defs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[FieldType] = mapped_column(Enum(FieldType), nullable=False, default=FieldType.text)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # select/multiselect options, default value, relation target, etc.
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    related_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    object: Mapped["ObjectDef"] = relationship(back_populates="fields")


class Record(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A row of a metadata-defined object. `data` holds field_slug -> value."""

    __tablename__ = "records"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("object_defs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
