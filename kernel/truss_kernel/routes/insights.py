"""Phase D routes: insights — analytics, agent scorecards, activity timeline.

All read-only. RBAC: viewer+ can view insights.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.services import analytics, insights, timeline

router = APIRouter(prefix="/api/insights", tags=["insights"])


class AnalyticsQueryIn(BaseModel):
    object: str = Field(min_length=1, max_length=100)
    metric: str = Field(default="count")
    field: str | None = None
    value_field: str | None = None
    bucket: str = Field(default="day")
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=100, ge=1, le=100)


@router.post("/query")
async def analytics_query(body: AnalyticsQueryIn,
                          auth: AuthContext = Depends(require_viewer),
                          db: AsyncSession = Depends(get_db)):
    """Run a structured read-only analytics query over an object's records."""
    try:
        return await analytics.run_query(db, auth.tenant_id, body.model_dump())
    except analytics.AnalyticsError as e:
        raise HTTPException(422, str(e))


@router.get("/objects")
async def object_counts(auth: AuthContext = Depends(require_viewer),
                        db: AsyncSession = Depends(get_db)):
    """Record count per object — the dashboard's top-line numbers."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from truss_kernel.models.metadata import ObjectDef

    objs = (await db.execute(
        select(ObjectDef).where(ObjectDef.tenant_id == auth.tenant_id)
        .options(selectinload(ObjectDef.fields))
        .order_by(ObjectDef.created_at)
    )).scalars().all()
    out = []
    for o in objs:
        out.append({
            "slug": o.slug,
            "name": o.name,
            "name_plural": o.name_plural or o.name,
            "icon": o.icon,
            "count": await analytics.count_records(db, auth.tenant_id, o),
            "fields": [f.slug for f in o.fields],
        })
    return out


@router.get("/agents")
async def agent_scorecards(auth: AuthContext = Depends(require_viewer),
                           db: AsyncSession = Depends(get_db)):
    """Performance scorecard for every AI employee."""
    return await insights.all_scorecards(db, auth.tenant_id)


@router.get("/agents/{agent_id}")
async def agent_scorecard(agent_id: uuid.UUID,
                          auth: AuthContext = Depends(require_viewer),
                          db: AsyncSession = Depends(get_db)):
    """One agent's performance scorecard."""
    from sqlalchemy import select
    from truss_kernel.models.agent import Agent

    agent = (await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, "agent not found")
    return await insights.agent_scorecard(db, auth.tenant_id, agent)


@router.get("/overview")
async def workspace_overview(auth: AuthContext = Depends(require_viewer),
                             db: AsyncSession = Depends(get_db)):
    """Tenant-wide rollup across all agents."""
    return await insights.workspace_overview(db, auth.tenant_id)


@router.get("/timeline")
async def activity_timeline(limit: int = Query(default=50, ge=1, le=200),
                            auth: AuthContext = Depends(require_viewer),
                            db: AsyncSession = Depends(get_db)):
    """Unified activity feed: record events + agent task lifecycle."""
    return await timeline.build_timeline(db, auth.tenant_id, limit=limit)
