"""Saved reports models (Phase M): reusable analytics queries + scheduled runs.

A SavedReport stores a named analytics query (same shape as
/api/insights/query). Reports can be run on demand or on a cron schedule;
every run snapshots its result into a ReportRun row.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SavedReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "saved_reports"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # analytics query: {object, metric, field?, value_field?, bucket?, days?, limit?}
    query: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # optional schedule: 5-field cron expression; None/"" = manual only
    cron: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ReportRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "report_runs"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")  # ok | error
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual | schedule
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
