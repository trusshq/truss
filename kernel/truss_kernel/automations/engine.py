"""Automation engine: interprets declarative trigger → condition → action rules.

Rules come from ENABLED plugin manifests (no user code). The engine subscribes
to the event bus as a wildcard handler; matching rules execute inside the same
DB transaction as the triggering change.

Safety:
- depth guard: events emitted BY automations carry depth+1; at MAX_DEPTH the
  engine stops, so self-retriggering rules can't loop forever
- tenant scope: only the emitting tenant's enabled plugins are consulted
- every firing (success or error) is recorded in automation_runs
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.events import bus
from truss_kernel.models.automation import AutomationRun
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.registry import registry
from truss_kernel.services import records as svc

logger = logging.getLogger("truss.automations")

MAX_DEPTH = 3


def _condition_matches(condition: dict, payload: dict, event_type: str) -> bool:
    """v1 conditions: {field, equals} / {field, not_equals} against the change."""
    if not condition:
        return True
    field = condition.get("field")
    if not field:
        return True
    if event_type == "record.updated":
        values = payload.get("patch") or {}
    elif event_type == "record.created":
        values = payload.get("data") or {}
    else:
        values = {}
    actual = values.get(field)
    if "equals" in condition and str(actual) != str(condition["equals"]):
        return False
    if "not_equals" in condition and str(actual) == str(condition["not_equals"]):
        return False
    return True


class AutomationEngine:
    async def handle(self, envelope: dict) -> None:
        depth = int(envelope.get("_depth", 0))
        if depth >= MAX_DEPTH:
            return
        db: AsyncSession | None = envelope.get("_db")
        if db is None:
            return
        event_type = envelope.get("type", "")
        if not event_type.startswith("record."):
            return  # v1 triggers are record lifecycle only
        try:
            tenant_id = uuid.UUID(envelope["tenant_id"])
        except (KeyError, ValueError):
            return

        payload = envelope.get("payload") or {}
        object_slug = payload.get("object")
        actor_id = uuid.UUID(envelope["actor_id"]) if envelope.get("actor_id") else None

        installs = (await db.execute(
            select(PluginInstall).where(
                PluginInstall.tenant_id == tenant_id,
                PluginInstall.enabled.is_(True),
            )
        )).scalars().all()

        for inst in installs:
            manifest = registry.get(inst.plugin_id)
            if manifest is None:
                continue
            for auto in manifest.automations:
                if auto.trigger != event_type:
                    continue
                if auto.object and auto.object != object_slug:
                    continue
                if not _condition_matches(auto.condition, payload, event_type):
                    continue
                status, detail = await self._run_actions(
                    db, tenant_id, actor_id, manifest.id, auto.actions, envelope, depth
                )
                db.add(AutomationRun(
                    tenant_id=tenant_id,
                    plugin_id=manifest.id,
                    automation_slug=auto.slug,
                    trigger_event=event_type,
                    status=status,
                    detail=detail,
                ))
                await db.flush()
                logger.info("automation %s/%s fired (%s)", manifest.id, auto.slug, status)

    async def _run_actions(self, db, tenant_id, actor_id, plugin_id,
                           actions: list[dict], envelope: dict, depth: int) -> tuple[str, dict]:
        payload = envelope.get("payload") or {}
        results: list[dict] = []
        for action in actions:
            kind = action.get("action")
            try:
                if kind == "emit_event":
                    event_type = action.get("type") or f"{plugin_id}.automation"
                    ctx = {
                        "source_event": envelope.get("type"),
                        "object": payload.get("object"),
                        "record_id": payload.get("record_id"),
                        "data": payload.get("data") or payload.get("patch"),
                    }
                    await bus.emit(
                        db, tenant_id=tenant_id, event_type=event_type, payload=ctx,
                        actor_id=actor_id, plugin_id=plugin_id, depth=depth + 1,
                    )
                    results.append({"action": kind, "emitted": event_type})

                elif kind == "update_record":
                    object_slug = action.get("object") or payload.get("object")
                    record_id = action.get("record_id") or payload.get("record_id")
                    patch = dict(action.get("patch") or {})
                    if not object_slug or not record_id or not patch:
                        raise ValueError("update_record needs object, record_id, patch")
                    obj = await svc.get_object(db, tenant_id, object_slug)
                    await svc.update_record(
                        db, tenant_id, actor_id, obj,
                        uuid.UUID(str(record_id)), patch,
                        _event_depth=depth + 1,
                    )
                    results.append({"action": kind, "record_id": str(record_id)})

                else:
                    raise ValueError(f"unsupported action '{kind}' in this kernel version")
            except Exception as e:  # noqa: BLE001 - one bad action fails the rule, not the kernel
                logger.exception("automation action %s failed", kind)
                results.append({"action": kind, "error": str(e)})
                return "error", {"results": results}
        return "success", {"results": results}


engine = AutomationEngine()
