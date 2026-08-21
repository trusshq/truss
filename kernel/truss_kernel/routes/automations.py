"""Automations routes: declared rules (from enabled plugins) + run history."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_member
from truss_kernel.models.automation import AutomationRun
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.registry import registry

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("")
async def list_automations(auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """All automation rules declared by the tenant's ENABLED plugins."""
    installs = (await db.execute(
        select(PluginInstall).where(
            PluginInstall.tenant_id == auth.tenant_id,
            PluginInstall.enabled.is_(True),
        )
    )).scalars().all()

    rules = []
    for inst in installs:
        manifest = registry.get(inst.plugin_id)
        if manifest is None:
            continue
        for auto in manifest.automations:
            rules.append({
                "plugin_id": manifest.id,
                "plugin_name": manifest.name,
                "slug": auto.slug,
                "name": auto.name,
                "trigger": auto.trigger,
                "object": auto.object,
                "condition": auto.condition,
                "actions": auto.actions,
            })
    return rules


@router.get("/runs")
async def list_runs(
    auth: AuthContext = Depends(require_member),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """Recent automation firings (audit trail)."""
    rows = (await db.execute(
        select(AutomationRun)
        .where(AutomationRun.tenant_id == auth.tenant_id)
        .order_by(AutomationRun.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "plugin_id": r.plugin_id,
            "automation_slug": r.automation_slug,
            "trigger_event": r.trigger_event,
            "status": r.status,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
