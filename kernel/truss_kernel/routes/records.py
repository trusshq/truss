"""Records routes: CRUD over metadata-defined objects with field validation.

Thin HTTP layer — all logic lives in truss_kernel.services.records so the
AI agent and the API share one validated code path.

Safety rails (Phase A3):
- DELETE moves records to the trash (soft delete); restore + purge endpoints
- GET /trash lists trashed records; POST /trash/{id}/restore brings them back
- GET /{object}/{id}/history returns the version timeline
- field-level permissions: fields with hidden_roles are masked per viewer role
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, ensure_scope, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.metadata import Record, RecordHistory
from truss_kernel.services import records as svc

router = APIRouter(prefix="/api/records", tags=["records"])


class RecordIn(BaseModel):
    data: dict = Field(default_factory=dict)


async def _get_object(db: AsyncSession, tenant_id: uuid.UUID, slug: str):
    try:
        return await svc.get_object(db, tenant_id, slug)
    except svc.ObjectNotFound as e:
        raise HTTPException(404, str(e)) from e


# NOTE: /trash routes are declared BEFORE /{object_slug} routes — FastAPI
# matches in definition order, so 'trash' must not be swallowed as an object slug.

@router.get("/trash")
async def list_trash(
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    object_slug: str | None = None,
    limit: int = Query(100, le=200),
):
    obj = None
    if object_slug:
        obj = await _get_object(db, auth.tenant_id, object_slug)
    rows = await svc.list_trash(db, auth.tenant_id, obj, limit=limit)
    # resolve object slugs for display
    from truss_kernel.models.metadata import ObjectDef
    obj_ids = {r.object_id for r in rows}
    objs = {}
    if obj_ids:
        found = (await db.execute(select(ObjectDef).where(ObjectDef.id.in_(obj_ids)))).scalars().all()
        objs = {o.id: o.slug for o in found}
    return [
        {
            **svc.rec_to_dict(r),
            "object": objs.get(r.object_id, ""),
            "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
        }
        for r in rows
    ]


@router.post("/trash/{record_id}/restore")
async def restore_record(record_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == auth.tenant_id,
        Record.deleted_at.isnot(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "record not in trash")
    from truss_kernel.models.metadata import ObjectDef
    obj = await db.get(ObjectDef, rec.object_id)
    if obj is None:
        raise HTTPException(404, "object no longer exists")
    await svc.restore(db, auth.tenant_id, auth.user_id, obj, record_id)
    await db.commit()
    return svc.rec_to_dict(rec)


@router.delete("/trash/{record_id}/purge", status_code=204)
async def purge_record(record_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Hard delete from the trash. Admin only — irreversible."""
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == auth.tenant_id,
        Record.deleted_at.isnot(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "record not in trash")
    await db.delete(rec)
    await db.commit()


@router.get("/{object_slug}/export.csv")
async def export_csv(object_slug: str, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Export all records of an object as CSV (field-per-column)."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    obj = await _get_object(db, auth.tenant_id, object_slug)
    ensure_scope(auth, "records:read")
    _, rows = await svc.query_records(db, auth.tenant_id, obj, limit=200, offset=0)

    buf = io.StringIO()
    field_slugs = [f.slug for f in obj.fields]
    writer = csv.writer(buf)
    writer.writerow(["id"] + field_slugs)
    for r in rows:
        masked = svc.mask_fields(obj, r.data, auth.role.value)
        writer.writerow([str(r.id)] + [masked.get(s, "") for s in field_slugs])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{object_slug}.csv"'},
    )


class CsvImportIn(BaseModel):
    csv_text: str = Field(min_length=1)
    # optional explicit header -> field_slug mapping; defaults to header == slug
    mapping: dict = Field(default_factory=dict)
    skip_errors: bool = True


@router.post("/{object_slug}/import")
async def import_csv(object_slug: str, body: CsvImportIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Import records from CSV text. Header row maps to field slugs."""
    import csv
    import io

    obj = await _get_object(db, auth.tenant_id, object_slug)
    ensure_scope(auth, "records:write")

    reader = csv.DictReader(io.StringIO(body.csv_text))
    if reader.fieldnames is None:
        raise HTTPException(422, "CSV has no header row")

    known = {f.slug for f in obj.fields}
    created, errors = 0, []
    for i, row in enumerate(reader, start=2):  # line 1 is the header
        data = {}
        for header, value in row.items():
            if header is None or value is None or value == "":
                continue
            slug = body.mapping.get(header, header)
            if slug in known:
                data[slug] = value
        if not data:
            continue
        try:
            await svc.create_record(db, auth.tenant_id, auth.user_id, obj, data)
            created += 1
        except svc.ValidationError as e:
            if not body.skip_errors:
                raise HTTPException(422, f"row {i}: {e}") from e
            errors.append({"row": i, "error": str(e)})
    await db.commit()
    return {"created": created, "skipped": len(errors), "errors": errors[:20]}


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
    ensure_scope(auth, "records:read")
    total, rows = await svc.query_records(db, auth.tenant_id, obj, search=search, limit=limit, offset=offset)
    items = []
    for r in rows:
        d = svc.rec_to_dict(r)
        d["data"] = svc.mask_fields(obj, d["data"], auth.role.value)
        items.append(d)
    return {"object": object_slug, "total": total, "limit": limit, "offset": offset, "items": items}


@router.post("/{object_slug}", status_code=201)
async def create_record(object_slug: str, body: RecordIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    ensure_scope(auth, "records:write")
    # Phase L: plan limit on records
    from truss_kernel.services import billing as billing_svc
    await billing_svc.ensure_within_limits(db, auth.tenant_id, "records")
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
        Record.id == record_id, Record.tenant_id == auth.tenant_id, Record.object_id == obj.id,
        Record.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(404, "record not found")
    d = svc.rec_to_dict(rec)
    d["data"] = svc.mask_fields(obj, d["data"], auth.role.value)
    return d


@router.get("/{object_slug}/{record_id}/history")
async def record_history(object_slug: str, record_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    rows = (await db.execute(
        select(RecordHistory).where(
            RecordHistory.record_id == record_id,
            RecordHistory.tenant_id == auth.tenant_id,
            RecordHistory.object_id == obj.id,
        ).order_by(RecordHistory.version.desc()).limit(50)
    )).scalars().all()
    return [
        {
            "version": h.version,
            "data": svc.mask_fields(obj, h.data, auth.role.value),
            "changed_by": str(h.changed_by) if h.changed_by else None,
            "actor_type": h.actor_type,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in rows
    ]


@router.patch("/{object_slug}/{record_id}")
async def update_record(object_slug: str, record_id: uuid.UUID, body: RecordIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = await _get_object(db, auth.tenant_id, object_slug)
    ensure_scope(auth, "records:write")
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
    """Soft delete: moves the record to the trash (restorable)."""
    obj = await _get_object(db, auth.tenant_id, object_slug)
    ensure_scope(auth, "records:write")
    try:
        await svc.soft_delete(db, auth.tenant_id, auth.user_id, obj, record_id)
    except svc.RecordNotFound as e:
        raise HTTPException(404, str(e)) from e
    await db.commit()
