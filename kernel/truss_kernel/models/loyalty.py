"""Loyalty & rewards model (Phase AI): members, points ledger, rewards, redemptions.

LoyaltyMember is a customer enrolled in the program with a points balance
and an auto-computed tier (bronze < 1000, silver < 5000, gold >= 5000).
LoyaltyPointEvent is an immutable ledger entry (delta + reason) backing
every balance change. LoyaltyReward is a catalog item with a points
cost; LoyaltyRedemption ties a member to a reward (pending -> fulfilled
| cancelled; cancel refunds the points).
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LoyaltyMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "loyalty_members"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    phone: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # current points balance (never negative)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # active | inactive
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class LoyaltyPointEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "loyalty_point_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loyalty_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # positive = award, negative = redeem/refund-adjust
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # balance after this event
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class LoyaltyReward(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "loyalty_rewards"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    points_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LoyaltyRedemption(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "loyalty_redemptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loyalty_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reward_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loyalty_rewards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # snapshot of the cost at redemption time
    points_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending | fulfilled | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
