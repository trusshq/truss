"""Plugin routes: catalog, install, enable/disable, per-tenant state."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member
from truss_kernel.events import bus
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.registry import registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginActionIn(BaseModel):
    plugin_id: str


class PluginSettingsIn(BaseModel):
    plugin_id: str
    settings: dict


def _manifest_dict(m) -> dict:
    return m.model_dump()


@router.get("/catalog")
async def catalog(auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """All discovered plugins + this tenant's install state."""
    installs = {
        i.plugin_id: i
        for i in (await db.execute(
            select(PluginInstall).where(PluginInstall.tenant_id == auth.tenant_id)
        )).scalars().all()
    }
    out = []
    for m in registry.all():
        inst = installs.get(m.id)
        out.append({
            **_manifest_dict(m),
            "installed": inst is not None,
            "enabled": inst.enabled if inst else False,
            "settings": inst.settings if inst else {},
        })
    return out


@router.post("/install", status_code=201)
async def install(body: PluginActionIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        inst = await registry.install(db, auth.tenant_id, body.plugin_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plugin.installed",
                   payload={"plugin_id": body.plugin_id}, actor_id=auth.user_id, plugin_id=body.plugin_id)
    await db.commit()
    return {"ok": True, "plugin_id": inst.plugin_id, "version": inst.version, "enabled": inst.enabled}


@router.post("/enable")
async def enable(body: PluginActionIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    inst = await registry.set_enabled(db, auth.tenant_id, body.plugin_id, True)
    if inst is None:
        raise HTTPException(404, "plugin not installed for this tenant")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plugin.enabled",
                   payload={"plugin_id": body.plugin_id}, actor_id=auth.user_id, plugin_id=body.plugin_id)
    await db.commit()
    return {"ok": True, "enabled": True}


@router.post("/disable")
async def disable(body: PluginActionIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    inst = await registry.set_enabled(db, auth.tenant_id, body.plugin_id, False)
    if inst is None:
        raise HTTPException(404, "plugin not installed for this tenant")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plugin.disabled",
                   payload={"plugin_id": body.plugin_id}, actor_id=auth.user_id, plugin_id=body.plugin_id)
    await db.commit()
    return {"ok": True, "enabled": False}


@router.post("/settings")
async def update_settings(body: PluginSettingsIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    inst = (await db.execute(select(PluginInstall).where(
        PluginInstall.tenant_id == auth.tenant_id, PluginInstall.plugin_id == body.plugin_id
    ))).scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "plugin not installed for this tenant")
    inst.settings = {**inst.settings, **body.settings}
    await db.flush()
    await db.commit()
    return {"ok": True, "settings": inst.settings}
