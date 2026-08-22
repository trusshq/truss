"""Phase B routes: org chart, goals, notifications, comments, review inbox.

RBAC:
- org structure (set reports_to): admin+
- goals: create/edit admin+, view viewer+
- notifications: read own, mark-read own
- comments: member+
- review inbox: viewer+ (approve/reject stays admin+ on the agents router)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.agents import org as org_svc
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.models.agent import Agent, AgentTask, TaskStatus
from truss_kernel.models.org import Goal, GoalStatus, Notification, TaskComment

router = APIRouter(prefix="/api/org", tags=["org"])


# ---------- schemas ----------

class ReportsToIn(BaseModel):
    agent_id: uuid.UUID
    manager_agent_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=8000)
    metric: str = Field(default="", max_length=120)
    target_value: float = Field(default=0.0, ge=0)
    unit: str = Field(default="", max_length=40)
    owner_agent_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    parent_goal_id: uuid.UUID | None = None
    due_at: str = Field(default="", max_length=40)


class GoalPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    metric: str | None = None
    target_value: float | None = Field(default=None, ge=0)
    current_value: float | None = Field(default=None, ge=0)
    unit: str | None = None
    status: str | None = None
    due_at: str | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


def goal_to_dict(g: Goal) -> dict:
    return {
        "id": str(g.id),
        "title": g.title,
        "description": g.description,
        "metric": g.metric,
        "target_value": g.target_value,
        "current_value": g.current_value,
        "unit": g.unit,
        "progress": org_svc.goal_progress(g),
        "status": g.status.value,
        "owner_agent_id": str(g.owner_agent_id) if g.owner_agent_id else None,
        "owner_user_id": str(g.owner_user_id) if g.owner_user_id else None,
        "parent_goal_id": str(g.parent_goal_id) if g.parent_goal_id else None,
        "due_at": g.due_at,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def notif_to_dict(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "actor_id": str(n.actor_id) if n.actor_id else None,
        "actor_type": n.actor_type,
        "read": bool(n.read_at),
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def comment_to_dict(c: TaskComment) -> dict:
    return {
        "id": str(c.id),
        "task_id": str(c.task_id),
        "body": c.body,
        "author_id": str(c.author_id) if c.author_id else None,
        "author_type": c.author_type,
        "mentions": c.mentions or [],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _get_agent(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    a = (await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "agent not found")
    return a


async def _get_goal(db: AsyncSession, tenant_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    g = (await db.execute(select(Goal).where(
        Goal.id == goal_id, Goal.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if g is None:
        raise HTTPException(404, "goal not found")
    return g


# ---------- org chart ----------

@router.get("/tree")
async def org_tree(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return await org_svc.build_org_tree(db, auth.tenant_id)


@router.post("/reports-to", status_code=200)
async def set_reports_to(body: ReportsToIn, auth: AuthContext = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, body.agent_id)
    try:
        await org_svc.set_reports_to(db, auth.tenant_id, a,
                                     body.manager_agent_id, body.manager_user_id)
    except org_svc.OrgError as e:
        raise HTTPException(422, str(e))
    await db.commit()
    await db.refresh(a)
    return {
        "id": str(a.id), "name": a.name,
        "reports_to_agent_id": str(a.reports_to_agent_id) if a.reports_to_agent_id else None,
        "reports_to_user_id": str(a.reports_to_user_id) if a.reports_to_user_id else None,
    }


# ---------- goals ----------

@router.get("/goals")
async def list_goals(status: str | None = None, auth: AuthContext = Depends(require_viewer),
                     db: AsyncSession = Depends(get_db)):
    stmt = select(Goal).where(Goal.tenant_id == auth.tenant_id)
    if status:
        try:
            stmt = stmt.where(Goal.status == GoalStatus(status))
        except ValueError:
            raise HTTPException(422, "invalid status filter")
    rows = (await db.execute(stmt.order_by(Goal.created_at.desc()))).scalars().all()
    return [goal_to_dict(g) for g in rows]


@router.post("/goals", status_code=201)
async def create_goal(body: GoalIn, auth: AuthContext = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    if body.owner_agent_id:
        await _get_agent(db, auth.tenant_id, body.owner_agent_id)
    if body.parent_goal_id:
        await _get_goal(db, auth.tenant_id, body.parent_goal_id)
    # default the owner to the current user ONLY when no agent owner is given
    owner_user = body.owner_user_id
    if not body.owner_agent_id and not owner_user:
        owner_user = auth.user_id
    try:
        g = await org_svc.create_goal(
            db, auth.tenant_id, title=body.title, description=body.description,
            metric=body.metric, target_value=body.target_value, unit=body.unit,
            owner_agent_id=body.owner_agent_id, owner_user_id=owner_user,
            parent_goal_id=body.parent_goal_id, created_by=auth.user_id, due_at=body.due_at,
        )
    except org_svc.OrgError as e:
        raise HTTPException(422, str(e))
    await db.commit()
    await db.refresh(g)
    return goal_to_dict(g)


@router.patch("/goals/{goal_id}")
async def update_goal(goal_id: uuid.UUID, body: GoalPatch,
                      auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        try:
            data["status"] = GoalStatus(data["status"])
        except ValueError:
            raise HTTPException(422, "invalid status")
    for k, v in data.items():
        setattr(g, k, v)
    # progress roll-up for the parent when a sub-goal moves
    if g.parent_goal_id:
        parent = (await db.execute(select(Goal).where(
            Goal.id == g.parent_goal_id, Goal.tenant_id == auth.tenant_id
        ))).scalar_one_or_none()
        if parent:
            await org_svc.roll_up_progress(db, auth.tenant_id, parent)
    await db.commit()
    await db.refresh(g)
    return goal_to_dict(g)


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    # detach children + tasks rather than cascade-delete
    await db.execute(update(Goal).where(Goal.parent_goal_id == goal_id).values(parent_goal_id=None))
    await db.execute(update(AgentTask).where(AgentTask.goal_id == goal_id).values(goal_id=None))
    await db.delete(g)
    await db.commit()


@router.get("/goals/{goal_id}/tasks")
async def goal_tasks(goal_id: uuid.UUID, auth: AuthContext = Depends(require_viewer),
                     db: AsyncSession = Depends(get_db)):
    await _get_goal(db, auth.tenant_id, goal_id)
    rows = (await db.execute(select(AgentTask).where(
        AgentTask.tenant_id == auth.tenant_id, AgentTask.goal_id == goal_id
    ).order_by(AgentTask.created_at.desc()))).scalars().all()
    from truss_kernel.routes.agents import task_to_dict
    return [task_to_dict(t) for t in rows]


# ---------- budget ledger ----------

@router.get("/budget")
async def budget_ledger(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Token spend across the org: per-agent usage vs cap + totals."""
    agents = (await db.execute(
        select(Agent).where(Agent.tenant_id == auth.tenant_id).order_by(Agent.created_at)
    )).scalars().all()
    rows = []
    total_used = 0
    total_cap = 0
    for a in agents:
        pct = (a.tokens_used / a.budget_tokens) if a.budget_tokens > 0 else None
        rows.append({
            "agent_id": str(a.id),
            "name": a.name,
            "icon": a.icon,
            "status": a.status.value,
            "tokens_used": a.tokens_used,
            "budget_tokens": a.budget_tokens,
            "utilization": round(pct, 4) if pct is not None else None,
            "runs_count": a.runs_count,
            "over_budget": a.budget_tokens > 0 and a.tokens_used >= a.budget_tokens,
        })
        total_used += a.tokens_used
        total_cap += a.budget_tokens
    return {
        "agents": rows,
        "total_tokens_used": total_used,
        "total_budget": total_cap,
        "uncapped_agents": sum(1 for a in agents if a.budget_tokens == 0),
    }


# ---------- review inbox (all pending approvals across agents) ----------

@router.get("/review")
async def review_inbox(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Everything awaiting human attention: proposed tasks + unread notifications."""
    tasks = (await db.execute(select(AgentTask).where(
        AgentTask.tenant_id == auth.tenant_id,
        AgentTask.status == TaskStatus.proposed,
    ).order_by(AgentTask.priority.desc(), AgentTask.created_at))).scalars().all()
    agents = {str(a.id): a.name for a in (await db.execute(
        select(Agent).where(Agent.tenant_id == auth.tenant_id)
    )).scalars().all()}
    from truss_kernel.routes.agents import task_to_dict
    items = []
    for t in tasks:
        d = task_to_dict(t)
        d["agent_name"] = agents.get(str(t.agent_id), "")
        items.append(d)
    return {"pending_tasks": items, "count": len(items)}


# ---------- notifications ----------

@router.get("/notifications")
async def list_notifications(unread_only: bool = False, limit: int = 50,
                             auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Notification).where(
        Notification.tenant_id == auth.tenant_id, Notification.user_id == auth.user_id
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at == "")
    rows = (await db.execute(stmt.order_by(Notification.created_at.desc()).limit(min(limit, 200)))).scalars().all()
    unread = (await db.execute(select(Notification.id).where(
        Notification.tenant_id == auth.tenant_id, Notification.user_id == auth.user_id,
        Notification.read_at == "",
    ))).scalars().all()
    return {"items": [notif_to_dict(n) for n in rows], "unread_count": len(unread)}


@router.post("/notifications/{notif_id}/read", status_code=200)
async def mark_read(notif_id: uuid.UUID, auth: AuthContext = Depends(require_viewer),
                    db: AsyncSession = Depends(get_db)):
    n = (await db.execute(select(Notification).where(
        Notification.id == notif_id, Notification.tenant_id == auth.tenant_id,
        Notification.user_id == auth.user_id,
    ))).scalar_one_or_none()
    if n is None:
        raise HTTPException(404, "notification not found")
    if not n.read_at:
        n.read_at = datetime.now(timezone.utc).isoformat()
        await db.commit()
    return notif_to_dict(n)


@router.post("/notifications/read-all", status_code=200)
async def mark_all_read(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    res = await db.execute(update(Notification).where(
        Notification.tenant_id == auth.tenant_id, Notification.user_id == auth.user_id,
        Notification.read_at == "",
    ).values(read_at=now))
    await db.commit()
    return {"marked": res.rowcount}


# ---------- task comments ----------

@router.get("/tasks/{task_id}/comments")
async def list_comments(task_id: uuid.UUID, auth: AuthContext = Depends(require_viewer),
                        db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TaskComment).where(
        TaskComment.tenant_id == auth.tenant_id, TaskComment.task_id == task_id
    ).order_by(TaskComment.created_at))).scalars().all()
    return [comment_to_dict(c) for c in rows]


@router.post("/tasks/{task_id}/comments", status_code=201)
async def add_comment(task_id: uuid.UUID, body: CommentIn,
                      auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(AgentTask).where(
        AgentTask.id == task_id, AgentTask.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    c = await org_svc.add_comment(db, auth.tenant_id, t, body=body.body,
                                  author_id=auth.user_id, author_type="user")
    await db.commit()
    await db.refresh(c)
    return comment_to_dict(c)
