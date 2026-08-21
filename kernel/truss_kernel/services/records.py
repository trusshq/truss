"""Shared record operations used by both the REST routes and the AI agent.

Keeping this in one place guarantees the agent can never bypass the
validation/tenancy rules that the API enforces.
"""
import uuid

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.events import bus
from truss_kernel.models.metadata import FieldType, ObjectDef, Record


class ObjectNotFound(LookupError):
    pass


class RecordNotFound(LookupError):
    pass


class ValidationError(ValueError):
    pass


async def get_object(db: AsyncSession, tenant_id: uuid.UUID, slug: str) -> ObjectDef:
    obj = (await db.execute(
        select(ObjectDef)
        .where(ObjectDef.tenant_id == tenant_id, ObjectDef.slug == slug)
        .options(selectinload(ObjectDef.fields))
    )).scalar_one_or_none()
    if obj is None:
        raise ObjectNotFound(f"object '{slug}' not found")
    return obj


def validate(obj: ObjectDef, data: dict, partial: bool = False) -> dict:
    """Validate + coerce incoming data against field defs. Unknown keys rejected."""
    known = {f.slug: f for f in obj.fields}
    errors = []
    clean: dict = {}

    if not partial:
        for f in obj.fields:
            if f.required and f.slug not in data:
                errors.append(f"missing required field '{f.slug}'")

    for key, value in data.items():
        f = known.get(key)
        if f is None:
            errors.append(f"unknown field '{key}'")
            continue
        if value is None:
            clean[key] = None
            continue
        t = f.type
        try:
            if t in (FieldType.number, FieldType.currency):
                clean[key] = float(value)
            elif t == FieldType.boolean:
                clean[key] = bool(value)
            elif t in (FieldType.select, FieldType.user, FieldType.relation):
                clean[key] = str(value)
            elif t == FieldType.multiselect:
                if not isinstance(value, list):
                    raise ValueError("expected a list")
                clean[key] = [str(v) for v in value]
            else:
                clean[key] = str(value)
        except (TypeError, ValueError):
            errors.append(f"field '{key}' has invalid value for type {t.value}")

    # select / multiselect option check
    for f in obj.fields:
        if f.slug not in clean or clean[f.slug] is None:
            continue
        opts = f.options.get("choices", [])
        if not opts:
            continue
        if f.type == FieldType.select and clean[f.slug] not in opts:
            errors.append(f"field '{f.slug}' value not in choices {opts}")
        if f.type == FieldType.multiselect:
            bad = [v for v in clean[f.slug] if v not in opts]
            if bad:
                errors.append(f"field '{f.slug}' values not in choices {opts}: {bad}")

    if errors:
        raise ValidationError("; ".join(errors))
    return clean


def rec_to_dict(r: Record) -> dict:
    return {
        "id": str(r.id),
        "object_id": str(r.object_id),
        "data": r.data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


async def create_record(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, data: dict, _event_depth: int = 0) -> Record:
    clean = validate(obj, data)
    rec = Record(tenant_id=tenant_id, object_id=obj.id, data=clean, created_by=user_id)
    db.add(rec)
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="record.created",
                   payload={"object": obj.slug, "record_id": str(rec.id), "data": clean},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def update_record(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, record_id, patch: dict, _event_depth: int = 0) -> Record:
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == tenant_id, Record.object_id == obj.id
    ))).scalar_one_or_none()
    if rec is None:
        raise RecordNotFound("record not found")
    clean = validate(obj, patch, partial=True)
    rec.data = {**rec.data, **clean}
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="record.updated",
                   payload={"object": obj.slug, "record_id": str(rec.id), "patch": clean},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def query_records(db: AsyncSession, tenant_id, obj: ObjectDef,
                        search: str | None = None, limit: int = 20, offset: int = 0) -> tuple[int, list[Record]]:
    stmt = select(Record).where(Record.tenant_id == tenant_id, Record.object_id == obj.id)
    if search:
        stmt = stmt.where(Record.data.cast(String).ilike(f"%{search}%"))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(
        stmt.order_by(Record.created_at.desc()).limit(min(limit, 200)).offset(max(offset, 0))
    )).scalars().all()
    return total or 0, list(rows)
