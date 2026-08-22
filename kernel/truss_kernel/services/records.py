"""Shared record operations used by both the REST routes and the AI agent.

Keeping this in one place guarantees the agent can never bypass the
validation/tenancy rules that the API enforces.

Safety rails (Phase A3):
- soft delete: every query filters deleted_at IS NULL; delete() moves to trash
- versioning: every create/update snapshots data into record_history
- field-level permissions: fields with options.hidden_roles are masked for
  those roles on read
- validation rules: options.rules = {min, max, pattern, unique} per field
"""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.events import bus
from truss_kernel.models.metadata import FieldType, ObjectDef, Record, RecordHistory


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


# ---------- validation rules ----------

def _check_rules(obj: ObjectDef, slug: str, value, rules: dict, errors: list) -> None:
    """Apply declarative field rules: min, max, pattern."""
    if value is None:
        return
    mn = rules.get("min")
    mx = rules.get("max")
    pattern = rules.get("pattern")
    try:
        if mn is not None and isinstance(value, (int, float)) and value < float(mn):
            errors.append(f"field '{slug}' is below minimum {mn}")
        if mx is not None and isinstance(value, (int, float)) and value > float(mx):
            errors.append(f"field '{slug}' is above maximum {mx}")
        if mn is not None and isinstance(value, str) and len(value) < int(mn):
            errors.append(f"field '{slug}' is shorter than {mn} characters")
        if mx is not None and isinstance(value, str) and len(value) > int(mx):
            errors.append(f"field '{slug}' is longer than {mx} characters")
        if pattern and isinstance(value, str) and not re.search(str(pattern), value):
            errors.append(f"field '{slug}' does not match pattern {pattern}")
    except (TypeError, ValueError, re.error):
        pass  # malformed rule never blocks a write


async def _check_unique(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef,
                        slug: str, value, exclude_record_id=None, errors: list | None = None) -> bool:
    """Return True if value is unique for this field across the object's records."""
    if value is None:
        return True
    stmt = select(Record).where(
        Record.tenant_id == tenant_id,
        Record.object_id == obj.id,
        Record.deleted_at.is_(None),
        Record.data[slug].astext == str(value),
    )
    if exclude_record_id is not None:
        stmt = stmt.where(Record.id != exclude_record_id)
    existing = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    return existing is None


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

    # declarative rules (min/max/pattern)
    for f in obj.fields:
        rules = (f.options or {}).get("rules") or {}
        if rules and f.slug in clean:
            _check_rules(obj, f.slug, clean[f.slug], rules, errors)

    if errors:
        raise ValidationError("; ".join(errors))
    return clean


async def validate_async(db: AsyncSession, tenant_id: uuid.UUID, obj: ObjectDef,
                         data: dict, partial: bool = False, exclude_record_id=None) -> dict:
    """Full validation including async checks (unique rules)."""
    clean = validate(obj, data, partial=partial)
    errors = []
    for f in obj.fields:
        rules = (f.options or {}).get("rules") or {}
        if rules.get("unique") and f.slug in clean:
            if not await _check_unique(db, tenant_id, obj, f.slug, clean[f.slug],
                                       exclude_record_id=exclude_record_id):
                errors.append(f"field '{f.slug}' value must be unique")
    if errors:
        raise ValidationError("; ".join(errors))
    return clean


# ---------- field-level permissions ----------

def mask_fields(obj: ObjectDef, data: dict, role: str) -> dict:
    """Remove fields whose options.hidden_roles includes the viewer's role."""
    out = dict(data)
    for f in obj.fields:
        hidden = (f.options or {}).get("hidden_roles") or []
        if role in hidden and f.slug in out:
            out[f.slug] = "•••••"
    return out


# ---------- history ----------

async def _snapshot(db: AsyncSession, tenant_id: uuid.UUID, rec: Record,
                    actor_id, actor_type: str = "user") -> None:
    last_version = await db.scalar(
        select(func.max(RecordHistory.version)).where(RecordHistory.record_id == rec.id)
    ) or 0
    db.add(RecordHistory(
        tenant_id=tenant_id,
        record_id=rec.id,
        object_id=rec.object_id,
        version=last_version + 1,
        data=dict(rec.data),
        changed_by=actor_id,
        actor_type=actor_type,
    ))


# ---------- serialization ----------

def rec_to_dict(r: Record) -> dict:
    return {
        "id": str(r.id),
        "object_id": str(r.object_id),
        "data": r.data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ---------- CRUD ----------

async def create_record(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, data: dict,
                        _event_depth: int = 0, actor_type: str = "user") -> Record:
    clean = await validate_async(db, tenant_id, obj, data)
    rec = Record(tenant_id=tenant_id, object_id=obj.id, data=clean, created_by=user_id)
    db.add(rec)
    await db.flush()
    await _snapshot(db, tenant_id, rec, user_id, actor_type)
    await bus.emit(db, tenant_id=tenant_id, event_type="record.created",
                   payload={"object": obj.slug, "record_id": str(rec.id), "data": clean,
                            "actor_type": actor_type},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def update_record(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, record_id, patch: dict,
                        _event_depth: int = 0, actor_type: str = "user") -> Record:
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == tenant_id, Record.object_id == obj.id,
        Record.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise RecordNotFound("record not found")
    clean = await validate_async(db, tenant_id, obj, patch, partial=True, exclude_record_id=record_id)
    rec.data = {**rec.data, **clean}
    await db.flush()
    await _snapshot(db, tenant_id, rec, user_id, actor_type)
    await bus.emit(db, tenant_id=tenant_id, event_type="record.updated",
                   payload={"object": obj.slug, "record_id": str(rec.id), "patch": clean,
                            "actor_type": actor_type},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def query_records(db: AsyncSession, tenant_id, obj: ObjectDef,
                        search: str | None = None, limit: int = 20, offset: int = 0) -> tuple[int, list[Record]]:
    stmt = select(Record).where(
        Record.tenant_id == tenant_id, Record.object_id == obj.id,
        Record.deleted_at.is_(None),
    )
    if search:
        stmt = stmt.where(Record.data.cast(String).ilike(f"%{search}%"))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(
        stmt.order_by(Record.created_at.desc()).limit(min(limit, 200)).offset(max(offset, 0))
    )).scalars().all()
    return total or 0, list(rows)


# ---------- trash ----------

async def soft_delete(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, record_id,
                      _event_depth: int = 0, actor_type: str = "user") -> Record:
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == tenant_id, Record.object_id == obj.id,
        Record.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise RecordNotFound("record not found")
    rec.deleted_at = datetime.now(timezone.utc)
    rec.deleted_by = user_id
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="record.trashed",
                   payload={"object": obj.slug, "record_id": str(rec.id), "actor_type": actor_type},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def restore(db: AsyncSession, tenant_id, user_id, obj: ObjectDef, record_id,
                  _event_depth: int = 0) -> Record:
    rec = (await db.execute(select(Record).where(
        Record.id == record_id, Record.tenant_id == tenant_id, Record.object_id == obj.id,
        Record.deleted_at.isnot(None),
    ))).scalar_one_or_none()
    if rec is None:
        raise RecordNotFound("record not in trash")
    rec.deleted_at = None
    rec.deleted_by = None
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="record.restored",
                   payload={"object": obj.slug, "record_id": str(rec.id)},
                   actor_id=user_id, plugin_id=obj.plugin_id, depth=_event_depth)
    return rec


async def list_trash(db: AsyncSession, tenant_id, obj: ObjectDef | None = None,
                     limit: int = 100) -> list[Record]:
    stmt = select(Record).where(
        Record.tenant_id == tenant_id, Record.deleted_at.isnot(None)
    )
    if obj is not None:
        stmt = stmt.where(Record.object_id == obj.id)
    rows = (await db.execute(
        stmt.order_by(Record.deleted_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    return list(rows)
