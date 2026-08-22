"""Marketplace routes: community plugin catalog + workspace templates.

Community plugins install by materializing their manifest into the external
plugins directory and re-running discovery, so they flow through the exact
same registry/install path as builtins. Templates install a set of plugins
and seed starter records in one transaction.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.config import settings
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.marketplace import catalog as mp
from truss_kernel.plugins import sdk as plugin_sdk
from truss_kernel.plugins.registry import registry
from truss_kernel.services import records as svc

logger = logging.getLogger("truss.marketplace")
router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class TemplateApplyIn(BaseModel):
    seed: bool = True


class PublishIn(BaseModel):
    manifest: dict
    install: bool = True  # also install into the publishing tenant


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse '1.2.3' into (1, 2, 3) for comparison. Non-numeric parts -> 0."""
    parts = []
    for p in str(v).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


# ---------------- publish (developer platform) ----------------

@router.post("/publish", status_code=201)
async def publish_plugin(
    body: PublishIn,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Publish a plugin manifest to the marketplace.

    Validates strictly via the Plugin SDK, materializes plugin.json into the
    external plugins dir, re-discovers, and (optionally) installs it into the
    publishing tenant.

    Versioning (Phase J): re-publishing an existing community plugin id is an
    UPDATE — the new version must be strictly greater. Shadowing a builtin
    plugin id is always rejected.
    """
    try:
        manifest = plugin_sdk.validate_manifest(body.manifest)
    except plugin_sdk.ManifestError as e:
        raise HTTPException(422, {"errors": e.errors}) from e

    builtin_dir = Path(settings.builtin_plugins_dir) / manifest.id
    if builtin_dir.exists():
        raise HTTPException(409, f"plugin id '{manifest.id}' is a builtin and cannot be shadowed")

    ext_root = Path(settings.external_plugins_dir)
    plugin_dir = ext_root / manifest.id
    manifest_path = plugin_dir / "plugin.json"

    is_update = False
    if manifest_path.exists():
        # version update: require strictly greater version
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_version = str(old.get("version", "0.0.0"))
        except Exception:  # noqa: BLE001
            old_version = "0.0.0"
        if _version_tuple(manifest.version) <= _version_tuple(old_version):
            raise HTTPException(
                409,
                f"version {manifest.version} is not greater than published {old_version}; bump the version to update",
            )
        is_update = True

    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(body.manifest, indent=2), encoding="utf-8")
    registry.discover()

    installed = False
    version = manifest.version
    if is_update:
        # bump the recorded version on every tenant install of this plugin
        from sqlalchemy import select as sa_select, update as sa_update
        from truss_kernel.models.plugin import PluginInstall
        await db.execute(
            sa_update(PluginInstall)
            .where(PluginInstall.plugin_id == manifest.id)
            .values(version=manifest.version)
        )
    elif body.install:
        inst = await registry.install(db, auth.tenant_id, manifest.id)
        installed = True
        version = inst.version

    await bus.emit(
        db, tenant_id=auth.tenant_id,
        event_type="plugin.version_updated" if is_update else "plugin.published",
        payload={"plugin_id": manifest.id, "version": manifest.version},
        actor_id=auth.user_id, plugin_id=manifest.id,
    )
    await db.commit()
    return {
        "ok": True,
        "plugin_id": manifest.id,
        "version": version,
        "installed": installed,
        "updated": is_update,
        "objects": len(manifest.objects),
        "tools": len(manifest.tools),
    }


@router.get("/published")
async def list_published(auth: AuthContext = Depends(require_viewer)):
    """Community plugins published on this instance (external plugins dir)."""
    ext_root = Path(settings.external_plugins_dir)
    items = []
    for manifest_path in sorted(ext_root.glob("*/plugin.json")) if ext_root.exists() else []:
        m = registry.get(manifest_path.parent.name)
        if m is None:
            continue
        items.append({
            "id": m.id,
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "objects": len(m.objects),
            "tools": len(m.tools),
        })
    return {"items": items, "total": len(items)}


@router.delete("/publish/{plugin_id}")
async def unpublish_plugin(
    plugin_id: str,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a community plugin from the marketplace.

    The manifest is deleted from the external dir and the plugin is disabled
    for all tenants — existing objects and DATA are preserved (disable, not
    delete). Builtin plugins cannot be unpublished.
    """
    import shutil

    builtin_dir = Path(settings.builtin_plugins_dir) / plugin_id
    if builtin_dir.exists():
        raise HTTPException(409, f"plugin '{plugin_id}' is a builtin and cannot be unpublished")

    ext_dir = Path(settings.external_plugins_dir) / plugin_id
    if not (ext_dir / "plugin.json").exists():
        raise HTTPException(404, f"plugin '{plugin_id}' is not published")

    shutil.rmtree(ext_dir, ignore_errors=True)
    registry.discover()

    # disable (not delete) installs everywhere — data is preserved
    from sqlalchemy import update as sa_update
    from truss_kernel.models.plugin import PluginInstall
    await db.execute(
        sa_update(PluginInstall)
        .where(PluginInstall.plugin_id == plugin_id)
        .values(enabled=False)
    )
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="plugin.unpublished",
        payload={"plugin_id": plugin_id}, actor_id=auth.user_id, plugin_id=plugin_id,
    )
    await db.commit()
    return {"ok": True, "plugin_id": plugin_id}


@router.post("/validate")
async def validate_manifest_route(
    body: dict,
    auth: AuthContext = Depends(require_viewer),
):
    """Dry-run manifest validation (no install). Returns errors or a summary."""
    try:
        m = plugin_sdk.validate_manifest(body)
        return {
            "ok": True,
            "plugin_id": m.id,
            "version": m.version,
            "objects": len(m.objects),
            "tools": len(m.tools),
            "automations": len(m.automations),
            "ui": len(m.ui),
        }
    except plugin_sdk.ManifestError as e:
        return {"ok": False, "errors": e.errors}


# ---------------- community plugins ----------------

@router.get("/plugins")
async def list_marketplace_plugins(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Community catalog with this tenant's install state overlaid."""
    from sqlalchemy import select
    from truss_kernel.models.plugin import PluginInstall

    installs = {
        i.plugin_id: i
        for i in (await db.execute(
            select(PluginInstall).where(PluginInstall.tenant_id == auth.tenant_id)
        )).scalars().all()
    }
    out = []
    for entry in mp.COMMUNITY_PLUGINS:
        e = mp.catalog_entry(entry)
        inst = installs.get(e["id"])
        e["installed"] = inst is not None
        e["enabled"] = inst.enabled if inst else False
        out.append(e)
    return {"items": out, "total": len(out)}


@router.post("/plugins/{plugin_id}/install", status_code=201)
async def install_marketplace_plugin(
    plugin_id: str,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    manifest = mp.get_manifest(plugin_id)
    if manifest is None:
        raise HTTPException(404, f"unknown marketplace plugin: {plugin_id}")

    # Materialize the manifest into the external plugins dir so discovery
    # treats it like any other plugin, then re-discover.
    ext_root = Path(settings.external_plugins_dir)
    plugin_dir = ext_root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plugin_dir / "plugin.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    registry.discover()

    try:
        inst = await registry.install(db, auth.tenant_id, plugin_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="plugin.installed",
        payload={"plugin_id": plugin_id, "source": "marketplace"},
        actor_id=auth.user_id, plugin_id=plugin_id,
    )
    await db.commit()
    return {"ok": True, "plugin_id": inst.plugin_id, "version": inst.version, "enabled": inst.enabled}


# ---------------- templates ----------------

@router.get("/templates")
async def list_templates(auth: AuthContext = Depends(require_viewer)):
    return {"items": [mp.template_summary(t) for t in mp.TEMPLATES], "total": len(mp.TEMPLATES)}


@router.post("/templates/{template_id}/apply", status_code=201)
async def apply_template(
    template_id: str,
    body: TemplateApplyIn,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    template = mp.get_template(template_id)
    if template is None:
        raise HTTPException(404, f"unknown template: {template_id}")

    # 1. install every plugin the template needs (idempotent)
    installed = []
    for pid in template["plugins"]:
        inst = await registry.install(db, auth.tenant_id, pid)
        installed.append(pid)
        await bus.emit(
            db, tenant_id=auth.tenant_id, event_type="plugin.installed",
            payload={"plugin_id": pid, "source": "template", "template": template_id},
            actor_id=auth.user_id, plugin_id=pid,
        )

    # 2. seed starter records (validated through the same path as the API)
    seeded = 0
    if body.seed:
        for seed in template["seeds"]:
            try:
                obj = await svc.get_object(db, auth.tenant_id, seed["object"])
            except svc.ObjectNotFound:
                logger.warning("template %s: object %s not found, skipping seed", template_id, seed["object"])
                continue
            await svc.create_record(db, auth.tenant_id, auth.user_id, obj, seed["data"])
            seeded += 1

    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="template.applied",
        payload={"template": template_id, "plugins": installed, "seeded": seeded},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True, "template": template_id, "plugins_installed": installed, "records_seeded": seeded}
