"""Phase C models: autonomous orchestration (the Grok-bot / Hermes layer).

- AgentSchedule: run an agent on a recurring basis (interval minutes or a
  5-field cron expression). The scheduler tick creates + executes a task.
- AgentTrigger: run an agent reactively when a matching event fires on the
  bus (e.g. record.created on a specific object).
- AgentPipeline: an ordered chain of agent steps; each step's reply is
  handed to the next agent as context (multi-agent handoff).
"""
import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ScheduleKind(str, PyEnum):
    interval = "interval"
    cron = "cron"


class AgentSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recurring autonomous work for one agent."""

    __tablename__ = "agent_schedules"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # the task title + description created on each tick
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[ScheduleKind] = mapped_column(Enum(ScheduleKind), nullable=False, default=ScheduleKind.interval)
    # interval kind: run every N minutes
    every_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # cron kind: standard 5-field expression (minute hour dom month dow)
    cron: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # human approval gate for each generated task
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # bookkeeping
    last_run_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    next_run_at: Mapped[str] = mapped_column(String(40), nullable=False, default="", index=True)
    runs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class AgentTrigger(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reactive agent work: fire when a matching event hits the bus."""

    __tablename__ = "agent_triggers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # exact event type to match, e.g. 'record.created'
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # optional object filter for record.* events, e.g. 'lead'
    object_slug: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # the task created on fire; {event} / {object} / {record_id} placeholders expand
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # debounce: don't re-fire within N seconds (guards event storms)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fired_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    fires_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class PipelineStatus(str, PyEnum):
    active = "active"
    paused = "paused"


class AgentPipeline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An ordered chain of agent steps (multi-agent handoff)."""

    __tablename__ = "agent_pipelines"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[PipelineStatus] = mapped_column(
        Enum(PipelineStatus), nullable=False, default=PipelineStatus.active
    )
    # ordered steps: [{agent_id, title, prompt}] — each receives the prior reply
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    runs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    last_status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
