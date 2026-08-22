"""Agent engine models: AI employees (Agent) + their work items (AgentTask).

Design:
- An Agent acts through the SAME validated record path as humans
  (truss_kernel.services.records) using its own UUID as the actor.
  Safety is architectural: agents cannot bypass schema, tenancy, or validation.
- AgentTask is a small state machine:
    proposed -> approved -> running -> done | failed
  with `needs_review` as a human-approval gate before execution.
- Every run records steps + token usage against the agent's budget.
"""
import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from truss_kernel.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentStatus(str, PyEnum):
    active = "active"
    paused = "paused"
    terminated = "terminated"


class TaskStatus(str, PyEnum):
    proposed = "proposed"
    approved = "approved"
    running = "running"
    done = "done"
    failed = "failed"
    rejected = "rejected"


class Agent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An AI employee hired into a workspace.

    `role` is the job title (e.g. 'SDR'), `persona` is the system-prompt
    character. The agent executes with the RBAC `permission_role` (member or
    viewer) — it is NOT a login user; it acts via its own UUID through the
    validated record service.
    """

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_agent_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    persona: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="🤖")
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus), nullable=False, default=AgentStatus.active
    )
    # which model/provider this employee uses ('' = tenant default AI key)
    ai_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_override: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # RBAC role the agent operates under when touching records
    permission_role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    # restrict the agent to specific plugin ids ('' = all enabled plugins)
    allowed_plugins: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # budget caps (0 = unlimited); usage accumulates per run
    budget_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # org chart (Phase B): manager agent or human member this agent reports to
    reports_to_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reports_to_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # free-form config (temperature, max_steps, future adapter settings)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AgentTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A unit of work assigned to an agent."""

    __tablename__ = "agent_tasks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), nullable=False, default=TaskStatus.proposed, index=True
    )
    # human approval gate: task must be approved before it may run
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # execution results
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    finished_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
