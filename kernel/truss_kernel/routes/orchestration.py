"""Phase C routes: schedules, triggers, pipelines (autonomous orchestration).

RBAC: manage orchestration = admin+; view = viewer+; run pipeline = member+.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.agents import orchestration as orch
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.models.agent import Agent
from truss_kernel.models.orchestration import (
    AgentPipeline,
    AgentSchedule,
    AgentTrigger,
    PipelineStatus,
    ScheduleKind,
)

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


# ---------- schemas ----------

class ScheduleIn(BaseModel):
    agent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    prompt: str = Field(default="", max_length=8000)
    kind: str = Field(default="interval")
    every_minutes: int = Field(default=60, ge=1)
    cron: str = Field(default="", max_length=100)
    enabled: bool = True
    needs_review: bool = False


class SchedulePatch(BaseModel):
    name: str | None = None
    title: str | None = None
    prompt: str | None = None
    kind: str | None = None
    every_minutes: int | None = Field(default=None, ge=1)
    cron: str | None = None
    enabled: bool | None = None
    needs_review: bool | None = None


class TriggerIn(BaseModel):
    agent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    object_slug: str = Field(default="", max_length=120)
    title: str = Field(min_length=1, max_length=300)
    prompt: str = Field(default="", max_length=8000)
    enabled: bool = True
    needs_review: bool = False
    cooldown_seconds: int = Field(default=0, ge=0)


class TriggerPatch(BaseModel):
    name: str | None = None
    event_type: str | None = None
    object_slug: str | None = None
    title: str | None = None
    prompt: str | None = None
    enabled: bool | None = None
    needs_review: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0)


class PipelineStep(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(default="", max_length=300)
    prompt: str = Field(default="", max_length=8000)


class PipelineIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    steps: list[PipelineStep] = Field(default_factory=list)


class PipelinePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    steps: list[PipelineStep] | None = None


class PipelineRunIn(BaseModel):
    input: str = Field(default="", max_length=8000)


def schedule_to_dict(s: AgentSchedule) -> dict:
    return {
        "id": str(s.id),
        "agent_id": str(s.agent_id),
        "name": s.name,
        "title": s.title,
        "prompt": s.prompt,
        "kind": s.kind.value,
        "every_minutes": s.every_minutes,
        "cron": s.cron,
        "enabled": s.enabled,
        "needs_review": s.needs_review,
        "last_run_at": s.last_run_at,
        "next_run_at": s.next_run_at,
        "runs_count": s.runs_count,
        "last_status": s.last_status,
        "last_error": s.last_error,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def trigger_to_dict(t: AgentTrigger) -> dict:
    return {
        "id": str(t.id),
        "agent_id": str(t.agent_id),
        "name": t.name,
        "event_type": t.event_type,
        "object_slug": t.object_slug,
        "title": t.title,
        "prompt": t.prompt,
        "enabled": t.enabled,
        "needs_review": t.needs_review,
        "cooldown_seconds": t.cooldown_seconds,
        "last_fired_at": t.last_fired_at,
        "fires_count": t.fires_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def pipeline_to_dict(p: AgentPipeline) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "status": p.status.value,
        "steps": p.steps or [],
        "runs_count": p.runs_count,
        "last_run_at": p.last_run_at,
        "last_status": p.last_status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _get_agent(db: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    a = (await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "agent not found")
    return a


def _validate_schedule_fields(kind: str, every_minutes: int, cron: str) -> None:
    try:
        k = ScheduleKind(kind)
    except ValueError:
        raise HTTPException(422, "kind must be 'interval' or 'cron'")
    if k == ScheduleKind.cron:
        if len(cron.split()) != 5:
            raise HTTPException(422, "cron must be a 5-field expression (minute hour dom month dow)")
        now = datetime.now(timezone.utc)
        if not orch.cron_matches(cron, now) and orch.next_cron_run(cron, now) is None:
            raise HTTPException(422, "cron expression never matches")


# ---------- schedules ----------

@router.get("/schedules")
async def list_schedules(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentSchedule).where(
        AgentSchedule.tenant_id == auth.tenant_id
    ).order_by(AgentSchedule.created_at.desc()))).scalars().all()
    return [schedule_to_dict(s) for s in rows]


@router.post("/schedules", status_code=201)
async def create_schedule(body: ScheduleIn, auth: AuthContext = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    await _get_agent(db, auth.tenant_id, body.agent_id)
    _validate_schedule_fields(body.kind, body.every_minutes, body.cron)
    now = datetime.now(timezone.utc)
    s = AgentSchedule(
        tenant_id=auth.tenant_id,
        agent_id=body.agent_id,
        name=body.name,
        title=body.title,
        prompt=body.prompt,
        kind=ScheduleKind(body.kind),
        every_minutes=body.every_minutes,
        cron=body.cron,
        enabled=body.enabled,
        needs_review=body.needs_review,
        next_run_at=orch._iso(orch.compute_next_run_raw(body.kind, body.every_minutes, body.cron, now)),
        created_by=auth.user_id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return schedule_to_dict(s)


@router.patch("/schedules/{schedule_id}")
async def update_schedule(schedule_id: uuid.UUID, body: SchedulePatch,
                          auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(AgentSchedule).where(
        AgentSchedule.id == schedule_id, AgentSchedule.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "schedule not found")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data:
        _validate_schedule_fields(data.get("kind", s.kind.value),
                                  data.get("every_minutes", s.every_minutes),
                                  data.get("cron", s.cron))
        data["kind"] = ScheduleKind(data["kind"])
    for k, v in data.items():
        setattr(s, k, v)
    # recompute next run when timing fields change
    if any(k in data for k in ("kind", "every_minutes", "cron", "enabled")):
        s.next_run_at = orch._iso(orch.compute_next_run(s, datetime.now(timezone.utc)))
    await db.commit()
    await db.refresh(s)
    return schedule_to_dict(s)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: uuid.UUID, auth: AuthContext = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(AgentSchedule).where(
        AgentSchedule.id == schedule_id, AgentSchedule.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "schedule not found")
    await db.delete(s)
    await db.commit()


@router.post("/schedules/tick", status_code=200)
async def manual_tick(auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Fire all due schedules immediately (for testing / manual runs)."""
    fired = await orch.scheduler.tick()
    return {"fired": fired}


# ---------- triggers ----------

@router.get("/triggers")
async def list_triggers(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentTrigger).where(
        AgentTrigger.tenant_id == auth.tenant_id
    ).order_by(AgentTrigger.created_at.desc()))).scalars().all()
    return [trigger_to_dict(t) for t in rows]


@router.post("/triggers", status_code=201)
async def create_trigger(body: TriggerIn, auth: AuthContext = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    await _get_agent(db, auth.tenant_id, body.agent_id)
    t = AgentTrigger(
        tenant_id=auth.tenant_id,
        agent_id=body.agent_id,
        name=body.name,
        event_type=body.event_type,
        object_slug=body.object_slug,
        title=body.title,
        prompt=body.prompt,
        enabled=body.enabled,
        needs_review=body.needs_review,
        cooldown_seconds=body.cooldown_seconds,
        created_by=auth.user_id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return trigger_to_dict(t)


@router.patch("/triggers/{trigger_id}")
async def update_trigger(trigger_id: uuid.UUID, body: TriggerPatch,
                         auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(AgentTrigger).where(
        AgentTrigger.id == trigger_id, AgentTrigger.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "trigger not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return trigger_to_dict(t)


@router.delete("/triggers/{trigger_id}", status_code=204)
async def delete_trigger(trigger_id: uuid.UUID, auth: AuthContext = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(AgentTrigger).where(
        AgentTrigger.id == trigger_id, AgentTrigger.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if t is None:
        raise HTTPException(404, "trigger not found")
    await db.delete(t)
    await db.commit()


# ---------- pipelines ----------

@router.get("/pipelines")
async def list_pipelines(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentPipeline).where(
        AgentPipeline.tenant_id == auth.tenant_id
    ).order_by(AgentPipeline.created_at.desc()))).scalars().all()
    return [pipeline_to_dict(p) for p in rows]


@router.post("/pipelines", status_code=201)
async def create_pipeline(body: PipelineIn, auth: AuthContext = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    if not body.steps:
        raise HTTPException(422, "a pipeline needs at least one step")
    for step in body.steps:
        await _get_agent(db, auth.tenant_id, step.agent_id)
    p = AgentPipeline(
        tenant_id=auth.tenant_id,
        name=body.name,
        description=body.description,
        steps=[s.model_dump() | {"agent_id": str(s.agent_id)} for s in body.steps],
        created_by=auth.user_id,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return pipeline_to_dict(p)


@router.patch("/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: uuid.UUID, body: PipelinePatch,
                          auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(AgentPipeline).where(
        AgentPipeline.id == pipeline_id, AgentPipeline.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "pipeline not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        try:
            data["status"] = PipelineStatus(data["status"])
        except ValueError:
            raise HTTPException(422, "invalid status")
    if "steps" in data:
        if not data["steps"]:
            raise HTTPException(422, "a pipeline needs at least one step")
        for step in data["steps"]:
            await _get_agent(db, auth.tenant_id, uuid.UUID(step["agent_id"]))
        data["steps"] = [dict(s) | {"agent_id": str(s["agent_id"])} for s in data["steps"]]
    for k, v in data.items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return pipeline_to_dict(p)


@router.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: uuid.UUID, auth: AuthContext = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(AgentPipeline).where(
        AgentPipeline.id == pipeline_id, AgentPipeline.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "pipeline not found")
    await db.delete(p)
    await db.commit()


@router.post("/pipelines/{pipeline_id}/run", status_code=200)
async def run_pipeline(pipeline_id: uuid.UUID, body: PipelineRunIn,
                       auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Execute the pipeline now, handing each step's reply to the next agent."""
    p = (await db.execute(select(AgentPipeline).where(
        AgentPipeline.id == pipeline_id, AgentPipeline.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "pipeline not found")
    result = await orch.run_pipeline(db, auth.tenant_id, p, initial_input=body.input)
    await db.refresh(p)
    return {"pipeline": pipeline_to_dict(p), "run": result}
