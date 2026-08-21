"""Plugin registry: discovers manifests on disk, materializes them per tenant.

v1 = declarative plugins only. Installing a plugin for a tenant means:
1. create its ObjectDefs/FieldDefs (idempotent, keyed by plugin_id+slug)
2. record a PluginInstall row (enable/disable + settings)
Disabling hides objects/UI/tools without deleting data.
"""
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.config import settings
from truss_kernel.models.metadata import FieldDef, ObjectDef
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.manifest import PluginManifest

logger = logging.getLogger("truss.plugins")


class PluginRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, PluginManifest] = {}

    # ---------- discovery ----------

    def discover(self) -> dict[str, PluginManifest]:
        """Load plugin.json manifests from builtin + external plugin dirs."""
        self._manifests.clear()
        roots = [
            Path(settings.builtin_plugins_dir),
            Path(settings.external_plugins_dir),
        ]
        for root in roots:
            if not root.exists():
                continue
            for manifest_path in sorted(root.glob("*/plugin.json")):
                try:
                    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = PluginManifest.model_validate(raw)
                    if manifest.id in self._manifests:
                        logger.warning("duplicate plugin id %s at %s — skipped", manifest.id, manifest_path)
                        continue
                    self._manifests[manifest.id] = manifest
                    logger.info("discovered plugin %s v%s", manifest.id, manifest.version)
                except Exception:  # noqa: BLE001
                    logger.exception("failed to load plugin manifest %s", manifest_path)
        return self._manifests

    def all(self) -> list[PluginManifest]:
        if not self._manifests:
            self.discover()
        return list(self._manifests.values())

    def get(self, plugin_id: str) -> PluginManifest | None:
        if not self._manifests:
            self.discover()
        return self._manifests.get(plugin_id)

    # ---------- install / enable / disable ----------

    async def install(self, db: AsyncSession, tenant_id, plugin_id: str) -> PluginInstall:
        manifest = self.get(plugin_id)
        if manifest is None:
            raise KeyError(f"unknown plugin: {plugin_id}")

        # materialize objects + fields (idempotent)
        for obj in manifest.objects:
            stmt = (
                select(ObjectDef)
                .where(
                    ObjectDef.tenant_id == tenant_id,
                    ObjectDef.slug == obj.slug,
                    ObjectDef.plugin_id == manifest.id,
                )
                .options(selectinload(ObjectDef.fields))
            )
            obj_def = (await db.execute(stmt)).scalar_one_or_none()
            if obj_def is None:
                obj_def = ObjectDef(
                    tenant_id=tenant_id,
                    slug=obj.slug,
                    name=obj.name,
                    name_plural=obj.name_plural or obj.name + "s",
                    description=obj.description,
                    icon=obj.icon,
                    plugin_id=manifest.id,
                    is_builtin=True,
                    fields=[],  # initialize collection: avoids async lazy-load below
                )
                db.add(obj_def)
                await db.flush()

            existing = {f.slug: f for f in obj_def.fields}
            for f in obj.fields:
                if f.slug in existing:
                    continue
                db.add(
                    FieldDef(
                        object_id=obj_def.id,
                        slug=f.slug,
                        name=f.name,
                        type=f.type,
                        required=f.required,
                        position=f.position,
                        options=f.options,
                    )
                )

        # upsert install row
        stmt = select(PluginInstall).where(
            PluginInstall.tenant_id == tenant_id,
            PluginInstall.plugin_id == plugin_id,
        )
        install = (await db.execute(stmt)).scalar_one_or_none()
        if install is None:
            install = PluginInstall(
                tenant_id=tenant_id,
                plugin_id=plugin_id,
                version=manifest.version,
                enabled=True,
            )
            db.add(install)
            await db.flush()
        return install

    async def set_enabled(self, db: AsyncSession, tenant_id, plugin_id: str, enabled: bool) -> PluginInstall | None:
        stmt = select(PluginInstall).where(
            PluginInstall.tenant_id == tenant_id,
            PluginInstall.plugin_id == plugin_id,
        )
        install = (await db.execute(stmt)).scalar_one_or_none()
        if install:
            install.enabled = enabled
            await db.flush()
        return install


registry = PluginRegistry()
