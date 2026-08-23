"""Payroll model (Major Phase 7): profiles, pay runs, payslips.

PayrollProfile attaches compensation terms to an Employee (annual salary
in cents, pay frequency, flat tax rate). PayRun is a payroll batch for a
period: draft -> approved -> paid | cancelled. Generating a draft run
creates one Payslip per active profile (gross from salary/frequency,
tax = gross * rate, net = gross - tax). Paying the run marks every
payslip paid.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PayrollProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payroll_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    annual_salary_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # monthly | biweekly | weekly
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    # flat tax rate, 0-100 (percent)
    tax_rate_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # active | paused
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)


class PayRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pay_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)    # YYYY-MM-DD
    # draft -> approved -> paid | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    total_gross_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_net_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Payslip(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payslips"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pay_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pay_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending | paid
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
