"""Event log routes (read-only for now; forwarding/webhooks come with connectors)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.models.plugin import EventLog

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def list_events(
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    type: str | None = None,
):
    stmt = select(EventLog).where(EventLog.tenant_id == auth.tenant_id)
    if type:
        stmt = stmt.where(EventLog.type == type)
    rows = (await db.execute(stmt.order_by(EventLog.created_at.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": str(e.id),
            "type": e.type,
            "plugin_id": e.plugin_id,
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
