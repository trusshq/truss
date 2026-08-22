"""Agent routes: hire/manage AI employees + assign & run tasks.

RBAC:
- hire/edit/pause/terminate agents, approve tasks: admin+
- assign tasks, run approved tasks: member+
- view agents/tasks: viewer+
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.agents import engine as agent_engine
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.agent import Agent, AgentStatus, AgentTask, TaskStatus

router = APIRouter(prefix="/api/agents", tags=["agents"])

VALID_PERMISSION_ROLES = ("member", "viewer")


# ---------- schemas ----------

class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=120)
    persona: str = Field(default="", max_length=8000)
    icon: str = Field(default="🤖", max_length=10)
    ai_key_id: uuid.UUID | None = None
    model_override: str = Field(default="", max_length=120)
    permission_role: str = Field(default="member", max_length=20)
    allowed_plugins: list[str] = Field(default_factory=list)
    budget_tokens: int = Field(default=0, ge=0)
    settings: dict = Field(default_factory=dict)


class AgentPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    persona: str | None = None
    icon: str | None = None
    status: str | None = None
    ai_key_id: uuid.UUID | None = None
    model_override: str | None = None
    permission_role: str | None = None
    allowed_plugins: list[str] | None = None
    budget_tokens: int | None = Field(default=None, ge=0)
    settings: dict | None = None


class TaskIn(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=8000)
    needs_review: bool = False
    priority: int = Field(default=0, ge=0, le=10)


def agent_to_dict(a: Agent) -> dict:
    return {
        "id": str(a.id),
        "name": a.name,
        "role": a.role,
        "persona": a.persona,
        "icon": a.icon,
        "status": a.status.value,
        "ai_key_id": str(a.ai_key_id) if a.ai_key_id else None,
        "model_override": a.model_override,
        "permission_role": a.permission_role,
        "allowed_plugins": a.allowed_plugins or [],
        "budget_tokens": a.budget_tokens,
        "tokens_used": a.tokens_used,
        "runs_count": a.runs_count,
        "settings": a.settings or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def task_to_dict(t: AgentTask) -> dict:
    return {
        "id": str(t.id),
        "agent_id": str(t.agent_id),
        "title": t.title,
        "description": t.description,
        "status": t.status.value,
        "needs_review": t.needs_review,
        "priority": t.priority,
        "created_by": str(t.created_by) if t.created_by else None,
        "approved_by": str(t.approved_by) if t.approved_by else None,
        "result": t.result or {},
        "error": t.error,
        "steps": t.steps,
        "tokens_used": t.tokens_used,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


async def _get_agent(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    a = (await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "agent not found")
    return a


async def _get_task(db: AsyncSession, tenant_id: uuid.UUID, task_id: uuid.UUID) -> AgentTask:
    t = (await db.execute(select(AgentTask).where(
        AgentTask.id == task_id, AgentTask.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "task not found")
    return t


# ---------- agent management ----------

@router.get("")
async def list_agents(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Agent).where(Agent.tenant_id == auth.tenant_id).order_by(Agent.created_at)
    )).scalars().all()
    return [agent_to_dict(a) for a in rows]


@router.post("", status_code=201)
async def hire_agent(body: AgentIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if body.permission_role not in VALID_PERMISSION_ROLES:
        raise HTTPException(422, f"permission_role must be one of {VALID_PERMISSION_ROLES}")
    exists = (await db.execute(select(Agent).where(
        Agent.tenant_id == auth.tenant_id, Agent.name == body.name
    ))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"an agent named '{body.name}' already exists")

    a = Agent(
        tenant_id=auth.tenant_id,
        name=body.name,
        role=body.role,
        persona=body.persona,
        icon=body.icon,
        ai_key_id=body.ai_key_id,
        model_override=body.model_override,
        permission_role=body.permission_role,
        allowed_plugins=body.allowed_plugins,
        budget_tokens=body.budget_tokens,
        settings=body.settings,
    )
    db.add(a)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.hired",
                   payload={"agent_id": str(a.id), "agent": a.name, "role": a.role,
                            "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return agent_to_dict(a)


@router.get("/{agent_id}")
async def get_agent(agent_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    return agent_to_dict(a)


@router.patch("/{agent_id}")
async def update_agent(agent_id: uuid.UUID, body: AgentPatch,
                       auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    data = body.model_dump(exclude_unset=True)
    if "permission_role" in data and data["permission_role"] not in VALID_PERMISSION_ROLES:
        raise HTTPException(422, f"permission_role must be one of {VALID_PERMISSION_ROLES}")
    if "status" in data:
        try:
            data["status"] = AgentStatus(data["status"])
        except ValueError:
            raise HTTPException(422, "invalid status")
    if "name" in data and data["name"] != a.name:
        clash = (await db.execute(select(Agent).where(
            Agent.tenant_id == auth.tenant_id, Agent.name == data["name"]
        ))).scalar_one_or_none()
        if clash:
            raise HTTPException(409, f"an agent named '{data['name']}' already exists")
    for k, v in data.items():
        setattr(a, k, v)
    await db.commit()
    await db.refresh(a)
    return agent_to_dict(a)


@router.post("/{agent_id}/pause", status_code=200)
async def pause_agent(agent_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    a.status = AgentStatus.paused
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.paused",
                   payload={"agent_id": str(a.id), "agent": a.name, "reason": "manual",
                            "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    return agent_to_dict(a)


@router.post("/{agent_id}/resume", status_code=200)
async def resume_agent(agent_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    if a.status == AgentStatus.terminated:
        raise HTTPException(409, "terminated agents cannot be resumed — hire a new one")
    a.status = AgentStatus.active
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.resumed",
                   payload={"agent_id": str(a.id), "agent": a.name, "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    return agent_to_dict(a)


@router.delete("/{agent_id}", status_code=204)
async def terminate_agent(agent_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.terminated",
                   payload={"agent_id": str(a.id), "agent": a.name, "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.delete(a)
    await db.commit()


# ---------- tasks ----------

@router.get("/{agent_id}/tasks")
async def list_tasks(agent_id: uuid.UUID, status: str | None = None,
                     auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_agent(db, auth.tenant_id, agent_id)
    stmt = select(AgentTask).where(
        AgentTask.tenant_id == auth.tenant_id, AgentTask.agent_id == agent_id
    )
    if status:
        try:
            stmt = stmt.where(AgentTask.status == TaskStatus(status))
        except ValueError:
            raise HTTPException(422, "invalid status filter")
    rows = (await db.execute(stmt.order_by(AgentTask.created_at.desc()).limit(100))).scalars().all()
    return [task_to_dict(t) for t in rows]


@router.post("/{agent_id}/tasks", status_code=201)
async def create_task(agent_id: uuid.UUID, body: TaskIn,
                      auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_agent(db, auth.tenant_id, agent_id)
    if body.agent_id != agent_id:
        raise HTTPException(422, "agent_id in body must match the path")
    t = AgentTask(
        tenant_id=auth.tenant_id,
        agent_id=agent_id,
        title=body.title,
        description=body.description,
        needs_review=body.needs_review,
        priority=body.priority,
        created_by=auth.user_id,
        # tasks that don't need review are auto-approved
        status=TaskStatus.proposed if body.needs_review else TaskStatus.approved,
        approved_by=None if body.needs_review else auth.user_id,
    )
    db.add(t)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.task_created",
                   payload={"agent_id": str(agent_id), "agent": a.name,
                            "task_id": str(t.id), "title": t.title,
                            "needs_review": t.needs_review, "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(t)
    return task_to_dict(t)


@router.post("/{agent_id}/tasks/{task_id}/approve", status_code=200)
async def approve_task(agent_id: uuid.UUID, task_id: uuid.UUID,
                       auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    t = await _get_task(db, auth.tenant_id, task_id)
    if t.agent_id != agent_id:
        raise HTTPException(422, "task does not belong to this agent")
    if t.status != TaskStatus.proposed:
        raise HTTPException(409, f"task is {t.status.value}, only proposed tasks can be approved")
    t.status = TaskStatus.approved
    t.approved_by = auth.user_id
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.task_approved",
                   payload={"agent_id": str(agent_id), "task_id": str(t.id),
                            "title": t.title, "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    return task_to_dict(t)


@router.post("/{agent_id}/tasks/{task_id}/reject", status_code=200)
async def reject_task(agent_id: uuid.UUID, task_id: uuid.UUID,
                      auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    t = await _get_task(db, auth.tenant_id, task_id)
    if t.agent_id != agent_id:
        raise HTTPException(422, "task does not belong to this agent")
    if t.status not in (TaskStatus.proposed, TaskStatus.approved):
        raise HTTPException(409, f"task is {t.status.value}, cannot reject")
    t.status = TaskStatus.rejected
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="agent.task_rejected",
                   payload={"agent_id": str(agent_id), "task_id": str(t.id),
                            "title": t.title, "actor_type": "user"},
                   actor_id=auth.user_id)
    await db.commit()
    return task_to_dict(t)


@router.post("/{agent_id}/tasks/{task_id}/run", status_code=200)
async def run_task(agent_id: uuid.UUID, task_id: uuid.UUID,
                   auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Execute an approved task now (synchronous — returns when done)."""
    a = await _get_agent(db, auth.tenant_id, agent_id)
    t = await _get_task(db, auth.tenant_id, task_id)
    if t.agent_id != agent_id:
        raise HTTPException(422, "task does not belong to this agent")
    if t.status == TaskStatus.proposed:
        raise HTTPException(409, "task needs approval before it can run")
    if t.status not in (TaskStatus.approved, TaskStatus.failed):
        raise HTTPException(409, f"task is {t.status.value}, cannot run")
    result = await agent_engine.run_task(db, auth.tenant_id, a, t)
    await db.refresh(t)
    return {"task": task_to_dict(t), "run": result}
