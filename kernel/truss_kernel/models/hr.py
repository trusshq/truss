"""HR model (Phase V): employee directory + leave requests with approvals.

Employee is a tenant-scoped directory entry (optionally linked to a login
user). LeaveRequest moves through pending -> approved | rejected, mirroring
the expense approval workflow.
"""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Employee(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employees"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    department: Mapped[str] = mapped_column(String(100), nullable=False, default="General", index=True)
    hire_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")  # YYYY-MM-DD
    # active | on_leave | terminated
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    # optional link to a login user in this tenant
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class LeaveRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "leave_requests"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # vacation | sick | personal | other
    leave_type: Mapped[str] = mapped_column(String(20), nullable=False, default="vacation", index=True)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
