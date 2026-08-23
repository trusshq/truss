"""Calendar routes (Phase P): CRUD + range queries for month/week/day views."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.calendar import CalendarEvent

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


def _parse_iso(value: str, field: str) -> str:
    """Validate an ISO-8601 timestamp; return it normalized to UTC ISO."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(422, f"{field} must be ISO-8601") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    starts_at: str
    ends_at: str | None = None
    all_day: bool = False
    location: str = ""
    attendees: list[str] = []
    object: str | None = None
    record_id: str | None = None


class EventUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    all_day: bool | None = None
    location: str | None = None
    attendees: list[str] | None = None
    object: str | None = None
    record_id: str | None = None


def _serialize(e: CalendarEvent) -> dict:
    return {
        "id": str(e.id),
        "title": e.title,
        "description": e.description,
        "starts_at": e.starts_at,
        "ends_at": e.ends_at,
        "all_day": e.all_day,
        "location": e.location,
        "attendees": e.attendees,
        "object": e.object_slug,
        "record_id": str(e.record_id) if e.record_id else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _validate_times(starts_at: str, ends_at: str | None) -> tuple[str, str | None]:
    start = _parse_iso(starts_at, "starts_at")
    end = _parse_iso(ends_at, "ends_at") if ends_at else None
    if end is not None and end < start:
        raise HTTPException(422, "ends_at must be after starts_at")
    return start, end


def _validate_record_id(record_id: str | None) -> uuid.UUID | None:
    if not record_id:
        return None
    try:
        return uuid.UUID(record_id)
    except ValueError as e:
        raise HTTPException(422, "record_id must be a UUID") from e


@router.post("", status_code=201)
async def create_event(body: EventIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    starts_at, ends_at = _validate_times(body.starts_at, body.ends_at)
    event = CalendarEvent(
        tenant_id=auth.tenant_id,
        title=body.title,
        description=body.description,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=body.all_day,
        location=body.location,
        attendees=body.attendees,
        object_slug=body.object,
        record_id=_validate_record_id(body.record_id),
        created_by=auth.user_id,
    )
    db.add(event)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="calendar.event_created",
        payload={"event_id": str(event.id), "title": event.title, "starts_at": starts_at},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(event)


@router.get("")
async def list_events(
    start: str | None = Query(default=None, description="ISO-8601 lower bound (inclusive)"),
    end: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    object: str | None = None,
    record_id: str | None = None,
    upcoming: int | None = Query(default=None, ge=1, le=50, description="return next N events from now"),
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """List events. Either a [start, end) range, or `upcoming=N` from now."""
    stmt = select(CalendarEvent).where(CalendarEvent.tenant_id == auth.tenant_id)

    if upcoming:
        now = datetime.now(timezone.utc).isoformat()
        stmt = stmt.where(CalendarEvent.starts_at >= now).order_by(CalendarEvent.starts_at.asc()).limit(upcoming)
    else:
        if start:
            stmt = stmt.where(CalendarEvent.starts_at >= _parse_iso(start, "start"))
        if end:
            stmt = stmt.where(CalendarEvent.starts_at < _parse_iso(end, "end"))
        stmt = stmt.order_by(CalendarEvent.starts_at.asc())

    if object:
        stmt = stmt.where(CalendarEvent.object_slug == object)
    if record_id:
        stmt = stmt.where(CalendarEvent.record_id == _validate_record_id(record_id))

    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_serialize(e) for e in rows], "total": len(rows)}


async def _get_event(db: AsyncSession, tenant_id, event_id: uuid.UUID) -> CalendarEvent:
    event = (await db.execute(select(CalendarEvent).where(
        CalendarEvent.id == event_id, CalendarEvent.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "event not found")
    return event


@router.get("/{event_id}")
async def get_event(event_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_event(db, auth.tenant_id, event_id))


@router.patch("/{event_id}")
async def update_event(event_id: uuid.UUID, body: EventUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    event = await _get_event(db, auth.tenant_id, event_id)
    if body.title is not None:
        event.title = body.title
    if body.description is not None:
        event.description = body.description
    if body.starts_at is not None or body.ends_at is not None:
        starts = body.starts_at if body.starts_at is not None else event.starts_at
        if body.ends_at is not None:
            ends = body.ends_at
        elif body.starts_at is not None and event.ends_at:
            # moving only the start: preserve the event's duration
            old_start = datetime.fromisoformat(event.starts_at)
            old_end = datetime.fromisoformat(event.ends_at)
            new_start = datetime.fromisoformat(_parse_iso(body.starts_at, "starts_at"))
            ends = (new_start + (old_end - old_start)).isoformat()
        else:
            ends = event.ends_at
        event.starts_at, event.ends_at = _validate_times(starts, ends)
    if body.all_day is not None:
        event.all_day = body.all_day
    if body.location is not None:
        event.location = body.location
    if body.attendees is not None:
        event.attendees = body.attendees
    if body.object is not None:
        event.object_slug = body.object or None
    if body.record_id is not None:
        event.record_id = _validate_record_id(body.record_id)
    await db.commit()
    return _serialize(event)


@router.delete("/{event_id}")
async def delete_event(event_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    event = await _get_event(db, auth.tenant_id, event_id)
    await db.delete(event)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="calendar.event_deleted",
        payload={"event_id": str(event_id), "title": event.title}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}
