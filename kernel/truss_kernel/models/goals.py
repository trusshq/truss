"""Goals & OKRs model (Phase AG): goals with weighted key results.

Goal tracks an objective for a period (e.g. a quarter) with a lifecycle
draft -> active -> achieved | missed | cancelled. Each goal carries key
results with a target and current value; overall progress is the weighted
average of key-result completion (current/target, capped at 100%).
"""
import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OKRGoal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "okr_goals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # e.g. "2026-Q3"
    period: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    # optional owner (workspace member id)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # draft | active | achieved | missed | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class OKRKeyResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "okr_key_results"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("okr_goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # unit label, e.g. "users", "%", "$"
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_value: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    current_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # relative weight in the goal's progress rollup
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
