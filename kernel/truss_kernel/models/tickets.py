"""Support tickets model (Phase AB): helpdesk with assignment, SLA, and comments.

Ticket moves through open -> in_progress -> resolved -> closed (reopenable).
Carries priority (low/medium/high/urgent) which drives an SLA due offset,
an optional assignee (workspace member), and a requester. TicketComment holds
the threaded conversation on a ticket.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tickets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # TK-0001
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requester_email: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="General", index=True)
    # low | medium | high | urgent
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", index=True)
    # open | in_progress | resolved | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    # workspace member assigned (nullable = unassigned)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # SLA: hours allowed to first resolution based on priority
    sla_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    closed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class TicketComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ticket_comments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # internal note vs public reply
    internal: Mapped[bool] = mapped_column(default=False, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
