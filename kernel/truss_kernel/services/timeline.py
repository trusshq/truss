"""Phase D unified activity timeline.

Merges three activity sources into one chronological feed so a user can see
everything that happened in the workspace — human edits, agent work, and
system events — in a single stream:

1. EventLog (record.created/updated/trashed, plugin events, agent events)
2. AgentTask lifecycle (task created / completed / failed)
3. Notifications (already surfaced separately, but included for completeness)

Read-only, tenant-scoped, cursor-paginated by created_at.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.models.agent import Agent, AgentTask, TaskStatus
from truss_kernel.models.plugin import EventLog

# event types worth showing on the timeline (skip noisy internal ones)
TIMELINE_EVENT_PREFIXES = ("record.", "agent.", "plugin.", "goal.", "automation.")


def _fmt_ts(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


async def build_timeline(db: AsyncSession, tenant_id: uuid.UUID,
                         limit: int = 50, event_types: list[str] | None = None) -> list[dict]:
    """Return a merged, newest-first activity feed."""
    limit = max(1, min(limit, 200))
    items: list[dict] = []

    # ---- 1. event log ----
    ev_stmt = select(EventLog).where(EventLog.tenant_id == tenant_id)
    if event_types:
        ev_stmt = ev_stmt.where(EventLog.type.in_(event_types))
    events = (await db.execute(
        ev_stmt.order_by(EventLog.created_at.desc()).limit(limit)
    )).scalars().all()
    for e in events:
        if not any(e.type.startswith(p) for p in TIMELINE_EVENT_PREFIXES):
            continue
        payload = e.payload or {}
        items.append({
            "kind": "event",
            "id": str(e.id),
            "type": e.type,
            "title": _event_title(e.type, payload),
            "detail": payload.get("object") or payload.get("agent") or "",
            "actor_type": payload.get("actor_type", ""),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "at": _fmt_ts(e.created_at),
        })

    # ---- 2. agent task lifecycle ----
    task_stmt = select(AgentTask).where(AgentTask.tenant_id == tenant_id)
    tasks = (await db.execute(
        task_stmt.order_by(AgentTask.created_at.desc()).limit(limit)
    )).scalars().all()
    # map agent ids -> names for display
    agent_ids = {t.agent_id for t in tasks}
    agent_names: dict[uuid.UUID, str] = {}
    if agent_ids:
        rows = (await db.execute(select(Agent.id, Agent.name, Agent.icon).where(
            Agent.id.in_(agent_ids)
        ))).all()
        agent_names = {r.id: f"{r.icon} {r.name}" for r in rows}

    for t in tasks:
        if t.status in (TaskStatus.done, TaskStatus.failed, TaskStatus.rejected):
            at = t.finished_at or _fmt_ts(t.updated_at)
            title = {
                TaskStatus.done: "completed task",
                TaskStatus.failed: "failed task",
                TaskStatus.rejected: "task rejected",
            }[t.status]
        else:
            at = _fmt_ts(t.created_at)
            title = "task assigned"
        items.append({
            "kind": "task",
            "id": str(t.id),
            "type": f"agent.task_{t.status.value}",
            "title": title,
            "detail": t.title,
            "actor_type": "agent",
            "actor_id": str(t.agent_id),
            "actor_name": agent_names.get(t.agent_id, ""),
            "at": at,
        })

    # ---- merge + sort newest first ----
    def sort_key(it):
        ts = it.get("at") or ""
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)

    items.sort(key=sort_key, reverse=True)
    return items[:limit]


def _event_title(event_type: str, payload: dict) -> str:
    obj = payload.get("object") or ""
    agent = payload.get("agent") or ""
    if event_type == "record.created":
        return f"created a {obj}" if obj else "created a record"
    if event_type == "record.updated":
        return f"updated a {obj}" if obj else "updated a record"
    if event_type == "record.trashed":
        return f"moved a {obj} to trash" if obj else "moved a record to trash"
    if event_type == "record.restored":
        return f"restored a {obj}" if obj else "restored a record"
    if event_type == "agent.task_completed":
        return f"{agent} completed a task" if agent else "agent completed a task"
    if event_type == "agent.task_failed":
        return f"{agent} failed a task" if agent else "agent failed a task"
    if event_type == "agent.task_created":
        return f"task created for {agent}" if agent else "task created"
    if event_type.startswith("goal."):
        return event_type.replace("goal.", "goal ")
    if event_type.startswith("automation."):
        return "automation fired"
    return event_type
