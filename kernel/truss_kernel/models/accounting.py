"""Accounting / general ledger model (Major Phase 8).

Double-entry bookkeeping: Account is a ledger account (code unique per
tenant, typed asset/liability/equity/revenue/expense). JournalEntry is a
dated batch of JournalLines that must balance (total debits == total
credits) before posting. Draft entries are editable/deletable; posted
entries are immutable.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "gl_accounts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # asset | liability | equity | revenue | expense
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # active | archived
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)


class JournalEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "gl_journal_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # draft -> posted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    # manual | invoice | expense | payroll | import
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class JournalLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "gl_journal_lines"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gl_journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gl_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    debit_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default="")
