"""Connectors routes: CRUD + test/introspect/query + delivery history."""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai.vault import decrypt_secret, encrypt_secret
from truss_kernel.connectors import postgres as pg_adapter
from truss_kernel.connectors.types import CONNECTOR_TYPES, mask_config, validate_config
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member
from truss_kernel.models.connector import Connector, WebhookDelivery

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorIn(BaseModel):
    name: str = Field(max_length=80)
    type: str
    config: dict = Field(default_factory=dict)
    description: str = Field(default="", max_length=300)
    enabled: bool = True


class QueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=50, ge=1, le=200)


def connector_to_dict(c: Connector, config: dict | None = None) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "type": c.type,
        "enabled": c.enabled,
        "description": c.description,
        "config": mask_config(config) if config else {},
        "implemented": CONNECTOR_TYPES.get(c.type, {}).get("implemented", False),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _get_connector(db: AsyncSession, tenant_id: uuid.UUID, connector_id: uuid.UUID) -> Connector:
    c = (await db.execute(select(Connector).where(
        Connector.id == connector_id, Connector.tenant_id == tenant_id
    ))).scalar_one_or_none()
    if c is None:
        raise HTTPException(404, "connector not found")
    return c


def _load_config(c: Connector) -> dict:
    if not c.config_enc:
        return {}
    try:
        return json.loads(decrypt_secret(c.config_enc))
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(500, "cannot decrypt connector config") from e


# ---------- catalog ----------

@router.get("/types")
async def list_types():
    return [
        {"type": t, "label": spec["label"], "required": spec["required"],
         "optional": spec["optional"], "implemented": spec["implemented"], "help": spec["help"]}
        for t, spec in CONNECTOR_TYPES.items()
    ]


# ---------- CRUD (admin) ----------

@router.get("")
async def list_connectors(auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Connector).where(Connector.tenant_id == auth.tenant_id).order_by(Connector.created_at)
    )).scalars().all()
    return [connector_to_dict(c, _load_config(c)) for c in rows]


@router.post("", status_code=201)
async def create_connector(body: ConnectorIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    err = validate_config(body.type, body.config)
    if err:
        raise HTTPException(422, err)
    exists = (await db.execute(select(Connector).where(
        Connector.tenant_id == auth.tenant_id, Connector.name == body.name
    ))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"connector named '{body.name}' already exists")

    c = Connector(
        tenant_id=auth.tenant_id,
        name=body.name,
        type=body.type,
        enabled=body.enabled,
        config_enc=encrypt_secret(json.dumps(body.config)),
        description=body.description,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return connector_to_dict(c, body.config)


@router.patch("/{connector_id}")
async def update_connector(connector_id: uuid.UUID, body: ConnectorIn,
                           auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_connector(db, auth.tenant_id, connector_id)
    err = validate_config(body.type, body.config)
    if err:
        raise HTTPException(422, err)
    # name uniqueness on rename
    if body.name != c.name:
        clash = (await db.execute(select(Connector).where(
            Connector.tenant_id == auth.tenant_id, Connector.name == body.name
        ))).scalar_one_or_none()
        if clash:
            raise HTTPException(409, f"connector named '{body.name}' already exists")
    c.name = body.name
    c.type = body.type
    c.enabled = body.enabled
    c.description = body.description
    c.config_enc = encrypt_secret(json.dumps(body.config))
    await db.commit()
    await db.refresh(c)
    return connector_to_dict(c, body.config)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_connector(db, auth.tenant_id, connector_id)
    await db.delete(c)
    await db.commit()


# ---------- actions ----------

@router.post("/{connector_id}/test")
async def test_connector(connector_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_connector(db, auth.tenant_id, connector_id)
    config = _load_config(c)
    if c.type == "postgres":
        return await pg_adapter.test_connection(config)
    if c.type == "webhook":
        return {"ok": True, "note": "webhook config valid; deliveries happen on events"}
    raise HTTPException(400, f"no test available for type '{c.type}' yet")


@router.get("/{connector_id}/tables")
async def list_tables(connector_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_connector(db, auth.tenant_id, connector_id)
    if c.type != "postgres":
        raise HTTPException(400, "tables only available for postgres connectors")
    return await pg_adapter.introspect(_load_config(c))


@router.post("/{connector_id}/query")
async def query(connector_id: uuid.UUID, body: QueryIn,
                auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_connector(db, auth.tenant_id, connector_id)
    if c.type != "postgres":
        raise HTTPException(400, "query only available for postgres connectors")
    return await pg_adapter.run_query(_load_config(c), body.sql, body.limit)


# ---------- webhook delivery history + retry ----------

@router.get("/{connector_id}/deliveries")
async def list_deliveries(connector_id: uuid.UUID, auth: AuthContext = Depends(require_member),
                          db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200)):
    await _get_connector(db, auth.tenant_id, connector_id)
    rows = (await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.tenant_id == auth.tenant_id, WebhookDelivery.connector_id == connector_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "status": r.status,
            "attempts": r.attempts,
            "last_http_status": r.last_http_status,
            "last_error": r.last_error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/{connector_id}/deliveries/{delivery_id}/retry")
async def retry_delivery(connector_id: uuid.UUID, delivery_id: uuid.UUID,
                         auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Manually re-attempt a failed/pending webhook delivery."""
    from truss_kernel.connectors import webhook as webhook_adapter

    c = await _get_connector(db, auth.tenant_id, connector_id)
    if c.type != "webhook":
        raise HTTPException(400, "retry only available for webhook connectors")
    row = (await db.execute(select(WebhookDelivery).where(
        WebhookDelivery.id == delivery_id,
        WebhookDelivery.tenant_id == auth.tenant_id,
        WebhookDelivery.connector_id == connector_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "delivery not found")

    config = _load_config(c)
    # reconstruct the original event payload from the event log
    from truss_kernel.models.plugin import EventLog
    event = await db.get(EventLog, row.event_id)
    payload = {
        "event_id": str(row.event_id),
        "type": row.event_type,
        "tenant_id": str(auth.tenant_id),
        "plugin_id": event.plugin_id if event else "",
        "payload": event.payload if event else {},
    }
    item = {
        "delivery_id": str(row.id),
        "url": config.get("url", ""),
        "secret": config.get("secret", ""),
        "payload": payload,
    }
    result = await webhook_adapter.deliver_item(db, item)
    await db.commit()
    return {
        "id": str(result.id),
        "status": result.status,
        "attempts": result.attempts,
        "last_http_status": result.last_http_status,
        "last_error": result.last_error,
    }
