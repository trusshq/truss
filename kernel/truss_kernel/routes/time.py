"""Time tracking routes (Phase R): entries, live timers, and summaries."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.time import TimeEntry

router = APIRouter(prefix="/api/time", tags=["time"])


def _parse_iso(value: str, field: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(422, f"{field} must be ISO-8601") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_between(start_iso: str, end_iso: str) -> int:
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return max(0, int((end - start).total_seconds() // 60))


class EntryIn(BaseModel):
    description: str = ""
    started_at: str
    stopped_at: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    object: str | None = None
    record_id: str | None = None
    notes: str = ""


class EntryUpdateIn(BaseModel):
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    object: str | None = None
    record_id: str | None = None
    notes: str | None = None


class TimerStartIn(BaseModel):
    description: str = ""
    object: str | None = None
    record_id: str | None = None


def _validate_record_id(record_id: str | None) -> uuid.UUID | None:
    if not record_id:
        return None
    try:
        return uuid.UUID(record_id)
    except ValueError as e:
        raise HTTPException(422, "record_id must be a UUID") from e


def _serialize(e: TimeEntry, running_minutes: int | None = None) -> dict:
    running = e.stopped_at is None
    duration = e.duration_minutes
    if running:
        duration = running_minutes if running_minutes is not None else _minutes_between(e.started_at, _now_iso())
    return {
        "id": str(e.id),
        "description": e.description,
        "started_at": e.started_at,
        "stopped_at": e.stopped_at,
        "duration_minutes": duration,
        "running": running,
        "object": e.object_slug,
        "record_id": str(e.record_id) if e.record_id else None,
        "user_id": str(e.user_id) if e.user_id else None,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.post("", status_code=201)
async def create_entry(body: EntryIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Log a completed time entry (or start one with stopped_at omitted)."""
    started_at = _parse_iso(body.started_at, "started_at")
    stopped_at = _parse_iso(body.stopped_at, "stopped_at") if body.stopped_at else None
    if stopped_at is not None and stopped_at < started_at:
        raise HTTPException(422, "stopped_at must be after started_at")

    duration = body.duration_minutes
    if duration is None and stopped_at is not None:
        duration = _minutes_between(started_at, stopped_at)

    entry = TimeEntry(
        tenant_id=auth.tenant_id,
        description=body.description,
        started_at=started_at,
        stopped_at=stopped_at,
        duration_minutes=duration,
        object_slug=body.object,
        record_id=_validate_record_id(body.record_id),
        user_id=auth.user_id,
        notes=body.notes,
    )
    db.add(entry)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="time.entry_created",
        payload={"entry_id": str(entry.id), "duration_minutes": duration}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(entry)


@router.get("")
async def list_entries(
    object: str | None = None,
    record_id: str | None = None,
    user_id: str | None = None,
    running: bool | None = None,
    start: str | None = None,
    end: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TimeEntry).where(TimeEntry.tenant_id == auth.tenant_id)
    if object:
        stmt = stmt.where(TimeEntry.object_slug == object)
    if record_id:
        stmt = stmt.where(TimeEntry.record_id == _validate_record_id(record_id))
    if user_id:
        stmt = stmt.where(TimeEntry.user_id == _validate_record_id(user_id))
    if running is True:
        stmt = stmt.where(TimeEntry.stopped_at.is_(None))
    elif running is False:
        stmt = stmt.where(TimeEntry.stopped_at.is_not(None))
    if start:
        stmt = stmt.where(TimeEntry.started_at >= _parse_iso(start, "start"))
    if end:
        stmt = stmt.where(TimeEntry.started_at < _parse_iso(end, "end"))
    rows = (await db.execute(stmt.order_by(TimeEntry.started_at.desc()))).scalars().all()
    return {"items": [_serialize(e) for e in rows], "total": len(rows)}


@router.get("/summary")
async def time_summary(
    start: str | None = None,
    end: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate logged minutes: total, by object, by user (completed entries only)."""
    stmt = select(TimeEntry).where(
        TimeEntry.tenant_id == auth.tenant_id, TimeEntry.stopped_at.is_not(None),
    )
    if start:
        stmt = stmt.where(TimeEntry.started_at >= _parse_iso(start, "start"))
    if end:
        stmt = stmt.where(TimeEntry.started_at < _parse_iso(end, "end"))
    rows = (await db.execute(stmt)).scalars().all()

    total = 0
    by_object: dict[str, int] = {}
    by_user: dict[str, int] = {}
    for e in rows:
        mins = e.duration_minutes or 0
        total += mins
        key = e.object_slug or "(none)"
        by_object[key] = by_object.get(key, 0) + mins
        ukey = str(e.user_id) if e.user_id else "(unknown)"
        by_user[ukey] = by_user.get(ukey, 0) + mins

    return {
        "total_minutes": total,
        "entries": len(rows),
        "by_object": [{"label": k, "minutes": v} for k, v in sorted(by_object.items(), key=lambda x: -x[1])],
        "by_user": [{"label": k, "minutes": v} for k, v in sorted(by_user.items(), key=lambda x: -x[1])],
    }


async def _get_entry(db: AsyncSession, tenant_id, entry_id: uuid.UUID) -> TimeEntry:
    entry = (await db.execute(select(TimeEntry).where(
        TimeEntry.id == entry_id, TimeEntry.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "time entry not found")
    return entry


@router.get("/{entry_id}")
async def get_entry(entry_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_entry(db, auth.tenant_id, entry_id))


@router.post("/timer/start", status_code=201)
async def start_timer(body: TimerStartIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Start a live timer. Only one running timer per user — stops the previous."""
    existing = (await db.execute(select(TimeEntry).where(
        TimeEntry.tenant_id == auth.tenant_id,
        TimeEntry.user_id == auth.user_id,
        TimeEntry.stopped_at.is_(None),
    ))).scalars().all()
    now = _now_iso()
    for e in existing:
        e.stopped_at = now
        e.duration_minutes = _minutes_between(e.started_at, now)

    entry = TimeEntry(
        tenant_id=auth.tenant_id,
        description=body.description,
        started_at=now,
        object_slug=body.object,
        record_id=_validate_record_id(body.record_id),
        user_id=auth.user_id,
    )
    db.add(entry)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="time.timer_started",
        payload={"entry_id": str(entry.id)}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(entry, running_minutes=0)


@router.post("/{entry_id}/timer/stop")
async def stop_timer(entry_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    entry = await _get_entry(db, auth.tenant_id, entry_id)
    if entry.stopped_at is not None:
        raise HTTPException(409, "timer is not running")
    now = _now_iso()
    entry.stopped_at = now
    entry.duration_minutes = _minutes_between(entry.started_at, now)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="time.timer_stopped",
        payload={"entry_id": str(entry.id), "duration_minutes": entry.duration_minutes}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(entry)


@router.patch("/{entry_id}")
async def update_entry(entry_id: uuid.UUID, body: EntryUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    entry = await _get_entry(db, auth.tenant_id, entry_id)
    if body.description is not None:
        entry.description = body.description
    if body.duration_minutes is not None:
        entry.duration_minutes = body.duration_minutes
    if body.object is not None:
        entry.object_slug = body.object or None
    if body.record_id is not None:
        entry.record_id = _validate_record_id(body.record_id)
    if body.notes is not None:
        entry.notes = body.notes
    await db.commit()
    return _serialize(entry)


@router.delete("/{entry_id}")
async def delete_entry(entry_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    entry = await _get_entry(db, auth.tenant_id, entry_id)
    await db.delete(entry)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="time.entry_deleted",
        payload={"entry_id": str(entry_id)}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}
