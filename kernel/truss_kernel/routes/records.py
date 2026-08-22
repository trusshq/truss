"""Records routes: CRUD over metadata-defined objects with field validation.

Thin HTTP layer — all logic lives in truss_kernel.services.records so the
AI agent and the API share one validated code path.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.metadata import Record
from truss_kernel.services import records as svc

router = APIRouter(prefix="/api/records", tags=["records"])


class RecordIn(BaseModel):
    data: dict = Field(default_factory=dict)


async def _get_object(db: AsyncSession, tenant_id: uuid.UUID, slug: str):
    try:
        return await svc.get_object(db, tenant_id, slug)
    except svc.ObjectNotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{object_slug}")
async def list_records(
    object_slug: str,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = None,
):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    total, rows = await svc.query_records(db, auth.tenant_id, obj, search=search, limit=limit, offset=offset)
    items = [svc.rec_to_dict(r) for r in rows]
    return {"object": object_slug, "total": total, "limit": limit, "offset": offset, "items": items}


@router.post("/{object_slug}", status_code=201)
async def create_record(object_slug: str, body: RecordIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    try:
        rec = await svc.create_record(db, auth.tenant_id, auth.user_id, obj, body.data)
    except svc.ValidationError as e:
        raise HTTPException(422, str(e)) from e
    await db.commit()
    return svc.rec_to_dict(rec)


@router.get("/{object_slug}/{record_id}")
async def get_record(object_slug: str, record_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == auth.tenant_id, Record.object_id == obj.id
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "record not found")
    return svc.rec_to_dict(rec)


@router.patch("/{object_slug}/{record_id}")
async def update_record(object_slug: str, record_id: uuid.UUID, body: RecordIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    try:
        rec = await svc.update_record(db, auth.tenant_id, auth.user_id, obj, record_id, body.data)
    except svc.RecordNotFound as e:
        raise HTTPException(404, str(e)) from e
    except svc.ValidationError as e:
        raise HTTPException(422, str(e)) from e
    await db.commit()
    return svc.rec_to_dict(rec)


@router.delete("/{object_slug}/{record_id}", status_code=204)
async def delete_record(object_slug: str, record_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == auth.tenant_id, Record.object_id == obj.id
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "record not found")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="record.deleted",
                   payload={"object": object_slug, "record_id": str(rec.id)},
                   actor_id=auth.user_id, plugin_id=obj.plugin_id)
    await db.delete(rec)
    await db.commit()
