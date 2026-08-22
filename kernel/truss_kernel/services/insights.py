"""Phase D agent insights: performance scorecards for AI employees.

Aggregates AgentTask history per agent into a scorecard:
- throughput: total / done / failed / rejected / pending tasks
- completion rate: done / (done + failed)
- review stats: how many tasks needed review, approval vs rejection
- token efficiency: tokens per completed task, budget utilization
- recency: last activity

Read-only, tenant-scoped. Powers the Insights dashboard and the agent
performance endpoint.
"""
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.models.agent import Agent, AgentTask, TaskStatus


async def agent_scorecard(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent) -> dict:
    """Build one agent's performance scorecard from its task history."""
    stmt = select(
        func.count(AgentTask.id).label("total"),
        func.count(case((AgentTask.status == TaskStatus.done, 1))).label("done"),
        func.count(case((AgentTask.status == TaskStatus.failed, 1))).label("failed"),
        func.count(case((AgentTask.status == TaskStatus.rejected, 1))).label("rejected"),
        func.count(case((AgentTask.status.in_([TaskStatus.proposed, TaskStatus.approved, TaskStatus.running]), 1))).label("pending"),
        func.count(case((AgentTask.needs_review.is_(True), 1))).label("reviewed"),
        func.coalesce(func.sum(AgentTask.tokens_used), 0).label("tokens"),
        func.max(AgentTask.finished_at).label("last_finished"),
    ).where(AgentTask.tenant_id == tenant_id, AgentTask.agent_id == agent.id)
    row = (await db.execute(stmt)).one()

    total = int(row.total or 0)
    done = int(row.done or 0)
    failed = int(row.failed or 0)
    rejected = int(row.rejected or 0)
    pending = int(row.pending or 0)
    reviewed = int(row.reviewed or 0)
    tokens = int(row.tokens or 0)

    finished = done + failed
    completion_rate = round(done / finished, 3) if finished else None
    tokens_per_done = round(tokens / done, 1) if done else None
    budget_util = round(agent.tokens_used / agent.budget_tokens, 3) if agent.budget_tokens > 0 else None

    return {
        "agent_id": str(agent.id),
        "name": agent.name,
        "role": agent.role,
        "icon": agent.icon,
        "status": agent.status.value,
        "tasks": {
            "total": total,
            "done": done,
            "failed": failed,
            "rejected": rejected,
            "pending": pending,
        },
        "completion_rate": completion_rate,
        "review": {
            "needed_review": reviewed,
            "rejected": rejected,
        },
        "tokens": {
            "total_used": agent.tokens_used,
            "budget": agent.budget_tokens,
            "utilization": budget_util,
            "per_completed_task": tokens_per_done,
        },
        "runs_count": agent.runs_count,
        "last_finished_at": row.last_finished or None,
    }


async def all_scorecards(db: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """Scorecards for every agent in the tenant, sorted by task volume desc."""
    agents = (await db.execute(select(Agent).where(
        Agent.tenant_id == tenant_id
    ))).scalars().all()
    cards = [await agent_scorecard(db, tenant_id, a) for a in agents]
    cards.sort(key=lambda c: c["tasks"]["total"], reverse=True)
    return cards


async def workspace_overview(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    """Tenant-wide rollup: totals across all agents."""
    cards = await all_scorecards(db, tenant_id)
    total_tasks = sum(c["tasks"]["total"] for c in cards)
    total_done = sum(c["tasks"]["done"] for c in cards)
    total_failed = sum(c["tasks"]["failed"] for c in cards)
    total_tokens = sum(c["tokens"]["total_used"] for c in cards)
    active = sum(1 for c in cards if c["status"] == "active")
    finished = total_done + total_failed
    return {
        "agents_total": len(cards),
        "agents_active": active,
        "tasks_total": total_tasks,
        "tasks_done": total_done,
        "tasks_failed": total_failed,
        "completion_rate": round(total_done / finished, 3) if finished else None,
        "tokens_total": total_tokens,
    }
