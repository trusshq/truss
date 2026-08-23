"""Bookings routes (Phase AF): services, appointments, lifecycle, overlap guard."""
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.bookings import Booking, BookingService

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

VALID_STATUS = {"pending", "confirmed", "completed", "cancelled", "no_show"}
# statuses that occupy a time slot (block overlaps)
ACTIVE_STATUSES = ("pending", "confirmed")


class ServiceIn(BaseModel):
    name: str
    description: str = ""
    duration_minutes: int = Field(default=30, ge=5, le=480)
    price_cents: int = Field(default=0, ge=0)
    currency: str = "USD"
    active: bool = True


class ServicePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    active: bool | None = None


class BookingIn(BaseModel):
    service_id: str
    customer_name: str
    customer_email: str = ""
    start_at: str  # ISO datetime
    notes: str = ""


class BookingPatch(BaseModel):
    customer_name: str | None = None
    customer_email: str | None = None
    start_at: str | None = None
    notes: str | None = None


def _serialize_service(s: BookingService) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "description": s.description,
        "duration_minutes": s.duration_minutes,
        "price_cents": s.price_cents,
        "currency": s.currency,
        "active": s.active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _serialize_booking(b: Booking) -> dict:
    return {
        "id": str(b.id),
        "service_id": str(b.service_id),
        "customer_name": b.customer_name,
        "customer_email": b.customer_email,
        "start_at": b.start_at,
        "end_at": b.end_at,
        "notes": b.notes,
        "status": b.status,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


async def _get_service(db: AsyncSession, tenant_id, sid: uuid.UUID) -> BookingService:
    s = (await db.execute(select(BookingService).where(
        BookingService.tenant_id == tenant_id, BookingService.id == sid))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Service not found")
    return s


async def _get_booking(db: AsyncSession, tenant_id, bid: uuid.UUID) -> Booking:
    b = (await db.execute(select(Booking).where(
        Booking.tenant_id == tenant_id, Booking.id == bid))).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "Booking not found")
    return b


def _parse_dt(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"{field} must be an ISO datetime")


async def _check_overlap(db: AsyncSession, tenant_id, start: datetime, end: datetime, exclude_id=None):
    """Reject if any active booking overlaps [start, end)."""
    stmt = select(Booking).where(
        Booking.tenant_id == tenant_id,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_at < end.isoformat(),
        Booking.end_at > start.isoformat(),
    )
    if exclude_id is not None:
        stmt = stmt.where(Booking.id != exclude_id)
    clash = (await db.execute(stmt)).scalars().first()
    if clash:
        raise HTTPException(409, f"Time slot overlaps booking {clash.id} ({clash.start_at} - {clash.end_at})")


# ---- services ----

@router.post("/services", status_code=201)
async def create_service(body: ServiceIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = BookingService(
        tenant_id=auth.tenant_id, name=body.name, description=body.description,
        duration_minutes=body.duration_minutes, price_cents=body.price_cents,
        currency=body.currency, active=body.active,
    )
    db.add(s)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking_service.created",
                   payload={"service_id": str(s.id), "name": s.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_service(s)


@router.get("/services")
async def list_services(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(BookingService).where(
        BookingService.tenant_id == auth.tenant_id).order_by(BookingService.created_at.desc()))).scalars().all()
    return {"items": [_serialize_service(s) for s in rows], "total": len(rows)}


@router.get("/services/{service_id}")
async def get_service(service_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_service(await _get_service(db, auth.tenant_id, service_id))


@router.patch("/services/{service_id}")
async def update_service(service_id: uuid.UUID, body: ServicePatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_service(db, auth.tenant_id, service_id)
    if body.name is not None:
        s.name = body.name
    if body.description is not None:
        s.description = body.description
    if body.duration_minutes is not None:
        s.duration_minutes = body.duration_minutes
    if body.price_cents is not None:
        s.price_cents = body.price_cents
    if body.currency is not None:
        s.currency = body.currency
    if body.active is not None:
        s.active = body.active
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking_service.updated",
                   payload={"service_id": str(s.id), "name": s.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_service(s)


@router.delete("/services/{service_id}", status_code=200)
async def delete_service(service_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = await _get_service(db, auth.tenant_id, service_id)
    refs = (await db.execute(select(Booking).where(
        Booking.tenant_id == auth.tenant_id, Booking.service_id == service_id))).scalars().all()
    if refs:
        raise HTTPException(409, f"Service has {len(refs)} booking(s); remove them first")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking_service.deleted",
                   payload={"service_id": str(s.id), "name": s.name}, actor_id=auth.user_id)
    await db.delete(s)
    await db.commit()
    return {"deleted": True}


# ---- bookings ----

@router.post("", status_code=201)
async def create_booking(body: BookingIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    try:
        sid = uuid.UUID(body.service_id)
    except ValueError:
        raise HTTPException(400, "service_id must be a UUID")
    service = await _get_service(db, auth.tenant_id, sid)
    if not service.active:
        raise HTTPException(409, "Service is inactive; activate it before booking")
    start = _parse_dt(body.start_at, "start_at")
    end = start + timedelta(minutes=service.duration_minutes)
    await _check_overlap(db, auth.tenant_id, start, end)
    b = Booking(
        tenant_id=auth.tenant_id, service_id=sid, customer_name=body.customer_name,
        customer_email=body.customer_email, start_at=start.isoformat(), end_at=end.isoformat(),
        notes=body.notes, status="pending", created_by=auth.user_id,
    )
    db.add(b)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.created",
                   payload={"booking_id": str(b.id), "customer": b.customer_name, "service": service.name},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)


@router.get("")
async def list_bookings(status: str | None = None, service_id: str | None = None,
                        auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Booking).where(Booking.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Booking.status == status)
    if service_id:
        try:
            stmt = stmt.where(Booking.service_id == uuid.UUID(service_id))
        except ValueError:
            raise HTTPException(400, "service_id must be a UUID")
    rows = (await db.execute(stmt.order_by(Booking.start_at.asc()))).scalars().all()
    return {"items": [_serialize_booking(b) for b in rows], "total": len(rows)}


@router.get("/{booking_id}")
async def get_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_booking(await _get_booking(db, auth.tenant_id, booking_id))


@router.patch("/{booking_id}")
async def update_booking(booking_id: uuid.UUID, body: BookingPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    if b.status in ("completed", "cancelled", "no_show"):
        raise HTTPException(409, f"Booking is {b.status}; only pending/confirmed bookings can be edited")
    service = await _get_service(db, auth.tenant_id, b.service_id)
    if body.customer_name is not None:
        b.customer_name = body.customer_name
    if body.customer_email is not None:
        b.customer_email = body.customer_email
    if body.notes is not None:
        b.notes = body.notes
    if body.start_at is not None:
        start = _parse_dt(body.start_at, "start_at")
        end = start + timedelta(minutes=service.duration_minutes)
        await _check_overlap(db, auth.tenant_id, start, end, exclude_id=b.id)
        b.start_at = start.isoformat()
        b.end_at = end.isoformat()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.updated",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)


@router.delete("/{booking_id}", status_code=200)
async def delete_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.deleted",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.delete(b)
    await db.commit()
    return {"deleted": True}


@router.post("/{booking_id}/confirm")
async def confirm_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    if b.status != "pending":
        raise HTTPException(409, f"Booking is {b.status}; only pending bookings can be confirmed")
    b.status = "confirmed"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.confirmed",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)


@router.post("/{booking_id}/complete")
async def complete_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    if b.status != "confirmed":
        raise HTTPException(409, f"Booking is {b.status}; only confirmed bookings can be completed")
    b.status = "completed"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.completed",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)


@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    if b.status not in ("pending", "confirmed"):
        raise HTTPException(409, f"Booking is {b.status}; only pending/confirmed bookings can be cancelled")
    b.status = "cancelled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.cancelled",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)


@router.post("/{booking_id}/no-show")
async def no_show_booking(booking_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    b = await _get_booking(db, auth.tenant_id, booking_id)
    if b.status != "confirmed":
        raise HTTPException(409, f"Booking is {b.status}; only confirmed bookings can be marked no-show")
    b.status = "no_show"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="booking.no_show",
                   payload={"booking_id": str(b.id), "customer": b.customer_name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(b)
    return _serialize_booking(b)
