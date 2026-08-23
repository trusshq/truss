"""Subscriptions model (Phase AE): recurring billing with plans + MRR.

SubscriptionPlan defines a recurring offer (name, interval, price in cents).
Subscription ties a customer to a plan with a lifecycle active -> paused ->
cancelled, tracks current_period_end for renewal, and computes MRR from
active subscriptions.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customer_subscription_plans"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # monthly | yearly
    interval: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    # price per interval in integer cents
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # whether new subscriptions can be created on this plan
    active: Mapped[bool] = mapped_column(default=True)


class CustomerSubscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customer_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_subscription_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer: Mapped[str] = mapped_column(String(300), nullable=False)
    # active | paused | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    # ISO date the current billing period ends (renewal date)
    current_period_end: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    cancelled_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
