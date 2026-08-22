"""Global search — one query across the whole workspace (Phase I).

Searches records in every object (JSON ilike), plus AI employees and goals.
This is the retrieval layer the command palette and chat agent use to ground
answers in real workspace data (RAG-lite: retrieve → feed to model/UI).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.models.agent import Agent
from truss_kernel.models.metadata import ObjectDef, Record
from truss_kernel.models.org import Goal

router = APIRouter(prefix="/api/search", tags=["search"])


async def run_global_search(db: AsyncSession, tenant_id, q: str, limit: int = 5) -> dict:
    """Core search logic — shared by the REST route and the chat agent."""
    needle = f"%{q.strip()}%"

    # --- records across every object ---
    objs = (await db.execute(
        select(ObjectDef).where(ObjectDef.tenant_id == tenant_id)
        .options(selectinload(ObjectDef.fields))
    )).scalars().all()

    record_hits: list[dict] = []
    for obj in objs:
        stmt = (
            select(Record)
            .where(
                Record.tenant_id == tenant_id,
                Record.object_id == obj.id,
                Record.deleted_at.is_(None),
                Record.data.cast(String).ilike(needle),
            )
            .order_by(Record.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        # title = first field's value if present
        title_field = obj.fields[0].slug if obj.fields else "name"
        for r in rows:
            data = r.data or {}
            title = str(data.get(title_field) or str(r.id)[:8])
            # snippet: first matching field value
            snippet = ""
            ql = q.strip().lower()
            for k, v in data.items():
                if ql in str(v).lower():
                    snippet = f"{k}: {str(v)[:80]}"
                    break
            record_hits.append({
                "object": obj.slug,
                "object_name": obj.name,
                "icon": obj.icon,
                "id": str(r.id),
                "title": title,
                "snippet": snippet,
            })
        if len(record_hits) >= limit * 3:
            break

    # --- agents ---
    agent_rows = (await db.execute(
        select(Agent).where(
            Agent.tenant_id == tenant_id,
            or_(Agent.name.ilike(needle), Agent.role.ilike(needle)),
        ).limit(limit)
    )).scalars().all()
    agent_hits = [
        {"id": str(a.id), "name": a.name, "role": a.role, "icon": a.icon, "status": a.status.value}
        for a in agent_rows
    ]

    # --- goals ---
    goal_rows = (await db.execute(
        select(Goal).where(
            Goal.tenant_id == tenant_id,
            Goal.title.ilike(needle),
        ).limit(limit)
    )).scalars().all()
    goal_hits = [
        {"id": str(g.id), "title": g.title, "status": g.status.value}
        for g in goal_rows
    ]

    return {
        "query": q.strip(),
        "records": record_hits,
        "agents": agent_hits,
        "goals": goal_hits,
        "total": len(record_hits) + len(agent_hits) + len(goal_hits),
    }


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(5, ge=1, le=20),
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Search records across ALL objects, plus agents and goals.

    Returns grouped results: {records: [{object, object_name, icon, id, title, snippet}],
    agents: [...], goals: [...]}.
    """
    return await run_global_search(db, auth.tenant_id, q, limit)
