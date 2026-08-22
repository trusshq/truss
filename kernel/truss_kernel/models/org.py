"""Phase B models: org-chart collaboration layer (the Paperclip layer).

- Goal: a measurable objective an agent (or human) works toward. Goals can
  nest (parent_goal_id) so a manager decomposes a big goal into sub-goals,
  and each goal can be decomposed into AgentTasks.
- Notification: an in-app alert delivered to a human member (the bell).
  Agents emit notifications; humans read/dismiss them.
- TaskComment: threaded discussion on an AgentTask, with @mentions. Humans
  and agents both comment; mentions notify the named member.
"""
import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GoalStatus(str, PyEnum):
    active = "active"
    achieved = "achieved"
    dropped = "dropped"


class Goal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A measurable objective owned by an agent or a human member.

    Decomposition: a goal may have a parent (it is a sub-goal) and may be
    broken into AgentTasks via goal_id on the task. Progress is tracked as
    current_value vs target_value on a named metric.
    """

    __tablename__ = "goals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # measurable target, e.g. metric='qualified_leads', target_value=50
    metric: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    target_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus), nullable=False, default=GoalStatus.active, index=True
    )
    # owner: exactly one of agent or human member
    owner_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # decomposition tree
    parent_goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    due_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An in-app alert for a human member (the bell icon)."""

    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # recipient (always a human user)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # who/what produced it
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user|agent|system
    kind: Mapped[str] = mapped_column(String(60), nullable=False, default="info", index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # deep link into the UI, e.g. "/agents/<id>" or "/review"
    link: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    read_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")  # '' = unread


class TaskComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A comment on an AgentTask. Humans and agents both comment."""

    __tablename__ = "task_comments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    author_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user|agent
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # resolved @mentions (user ids) for notification fan-out
    mentions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
