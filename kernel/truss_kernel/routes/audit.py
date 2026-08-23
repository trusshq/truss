"""Audit log routes (Phase K): filtered, actor-resolved event history + CSV export.

Built on the EventLog seam — every meaningful action already lands there. This
adds:
- GET /api/audit: paginated, filterable (type prefix, actor, plugin, since/until),
  with actor names resolved (user full_name or agent name) and human summaries.
- GET /api/audit/export.csv: the same rows as CSV for compliance/offline review.
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.models.agent import Agent
from truss_kernel.models.plugin import EventLog
from truss_kernel.models.tenant import User

router = APIRouter(prefix="/api/audit", tags=["audit"])

# Human-readable summaries for common event types
_SUMMARIES = {
    "record.created": "created a record",
    "record.updated": "updated a record",
    "record.deleted": "deleted a record",
    "record.restored": "restored a record",
    "object.created": "created an object",
    "field.created": "added a field",
    "plugin.installed": "installed a plugin",
    "plugin.published": "published a plugin",
    "plugin.version_updated": "updated a plugin version",
    "plugin.unpublished": "unpublished a plugin",
    "agent.hired": "hired an AI employee",
    "agent.task.created": "assigned a task",
    "agent.task.completed": "completed a task",
    "agent.task.failed": "failed a task",
    "automation.created": "created an automation",
    "automation.triggered": "triggered an automation",
    "template.applied": "applied a template",
    "member.invited": "invited a member",
    "member.joined": "joined the workspace",
    "goal.created": "created a goal",
    "approval.requested": "requested an approval",
    "approval.decided": "decided an approval",
}


def _summarize(event_type: str, payload: dict) -> str:
    base = _SUMMARIES.get(event_type)
    if base is None:
        return event_type
    # enrich with the most identifying payload field
    for key in ("name", "title", "object", "plugin_id", "agent"):
        v = payload.get(key)
        if v:
            return f"{base} — {v}"
    return base


async def _resolve_actors(db: AsyncSession, actor_ids: set) -> dict:
    """Map actor UUIDs -> display name (user full_name, else agent name)."""
    if not actor_ids:
        return {}
    names: dict = {}
    users = (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars().all()
    for u in users:
        names[str(u.id)] = u.full_name or u.email
    remaining = actor_ids - {u.id for u in users}
    if remaining:
        agents = (await db.execute(select(Agent).where(Agent.id.in_(remaining)))).scalars().all()
        for a in agents:
            names[str(a.id)] = f"{a.name} (AI)"
    return names


def _base_query(auth: AuthContext, type_prefix: str | None, actor: str | None,
                plugin: str | None, since: datetime | None, until: datetime | None):
    stmt = select(EventLog).where(EventLog.tenant_id == auth.tenant_id)
    if type_prefix:
        stmt = stmt.where(EventLog.type.like(f"{type_prefix}%"))
    if actor:
        stmt = stmt.where(EventLog.actor_id == actor)
    if plugin:
        stmt = stmt.where(EventLog.plugin_id == plugin)
    if since:
        stmt = stmt.where(EventLog.created_at >= since)
    if until:
        stmt = stmt.where(EventLog.created_at <= until)
    return stmt.order_by(EventLog.created_at.desc())


@router.get("")
async def list_audit(
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    type: str | None = Query(None, description="event type prefix filter, e.g. 'record'"),
    actor: str | None = Query(None, description="actor UUID filter"),
    plugin: str | None = Query(None, description="plugin id filter"),
    since: datetime | None = None,
    until: datetime | None = None,
):
    stmt = _base_query(auth, type, actor, plugin, since, until)
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()

    actor_ids = {e.actor_id for e in rows if e.actor_id}
    names = await _resolve_actors(db, actor_ids)

    items = []
    for e in rows:
        actor_str = str(e.actor_id) if e.actor_id else None
        items.append({
            "id": str(e.id),
            "type": e.type,
            "summary": _summarize(e.type, e.payload or {}),
            "actor_id": actor_str,
            "actor_name": names.get(actor_str, "System" if not actor_str else "Unknown"),
            "plugin_id": e.plugin_id or None,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return {"items": items, "total": len(items), "offset": offset, "limit": limit}


@router.get("/export.csv")
async def export_audit_csv(
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(1000, ge=1, le=5000),
    type: str | None = None,
    actor: str | None = None,
    plugin: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    stmt = _base_query(auth, type, actor, plugin, since, until)
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    actor_ids = {e.actor_id for e in rows if e.actor_id}
    names = await _resolve_actors(db, actor_ids)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "type", "summary", "actor", "plugin_id"])
    for e in rows:
        actor_str = str(e.actor_id) if e.actor_id else None
        w.writerow([
            e.created_at.isoformat() if e.created_at else "",
            e.type,
            _summarize(e.type, e.payload or {}),
            names.get(actor_str, "System" if not actor_str else "Unknown"),
            e.plugin_id or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
