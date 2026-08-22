"""Tenant + User + Membership + Invite models (multi-tenancy core)."""
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantRole(str, PyEnum):
    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"


# Role hierarchy for comparisons (higher = more privilege)
ROLE_RANK = {TenantRole.viewer: 0, TenantRole.member: 1, TenantRole.admin: 2, TenantRole.owner: 3}


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A workspace. The slug is the public namespace (truss.app/<slug>)."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # workspace profile / namespace fields
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    website: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    company_size: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    logo_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en-US")
    # free-form workspace settings (feature flags, defaults, branding)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    invites: Mapped[list["Invite"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # profile fields
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en-US")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Membership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's role inside a tenant. One user can belong to many tenants."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[TenantRole] = mapped_column(Enum(TenantRole), nullable=False, default=TenantRole.member)

    tenant: Mapped["Tenant"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Invite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A pending invitation to join a workspace with a pre-assigned role."""

    __tablename__ = "invites"
    __table_args__ = (UniqueConstraint("tenant_id", "email", "token", name="uq_invite_tenant_email_token"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[TenantRole] = mapped_column(Enum(TenantRole), nullable=False, default=TenantRole.member)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="invites")

    @property
    def is_pending(self) -> bool:
        from datetime import datetime as _dt, timezone as _tz

        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > _dt.now(_tz.utc)
        )
