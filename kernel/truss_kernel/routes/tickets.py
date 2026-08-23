"""Support tickets routes (Phase AB): CRUD, lifecycle, assignment, comments, SLA."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.tickets import Ticket, TicketComment

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

VALID_STATUS = {"open", "in_progress", "resolved", "closed"}
VALID_PRIORITY = {"low", "medium", "high", "urgent"}
# SLA hours to first resolution by priority
SLA_HOURS = {"low": 72, "medium": 24, "high": 8, "urgent": 2}


class TicketIn(BaseModel):
    subject: str
    description: str = ""
    requester_email: str = ""
    category: str = "General"
    priority: str = "medium"
    assignee_id: str | None = None


class TicketPatch(BaseModel):
    subject: str | None = None
    description: str | None = None
    requester_email: str | None = None
    category: str | None = None
    priority: str | None = None
    assignee_id: str | None = None


class CommentIn(BaseModel):
    body: str
    internal: bool = False


def _sla_breached(t: Ticket) -> bool:
    """True if open/in_progress and past the SLA window from creation."""
    if t.status not in ("open", "in_progress"):
        return False
    if not t.created_at:
        return False
    due = t.created_at + timedelta(hours=t.sla_hours)
    return datetime.now(timezone.utc) > due


def _serialize(t: Ticket) -> dict:
    return {
        "id": str(t.id),
        "number": t.number,
        "subject": t.subject,
        "description": t.description,
        "requester_email": t.requester_email,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "assignee_id": str(t.assignee_id) if t.assignee_id else None,
        "sla_hours": t.sla_hours,
        "sla_breached": _sla_breached(t),
        "resolved_at": t.resolved_at,
        "closed_at": t.closed_at,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_comment(c: TicketComment) -> dict:
    return {
        "id": str(c.id),
        "ticket_id": str(c.ticket_id),
        "body": c.body,
        "internal": c.internal,
        "author_id": str(c.author_id) if c.author_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _next_number(db: AsyncSession, tenant_id) -> str:
    n = (await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.tenant_id == tenant_id)
    )).scalar_one()
    return f"TK-{n + 1:04d}"


async def _get_ticket(db: AsyncSession, tenant_id, tid: uuid.UUID) -> Ticket:
    t = (await db.execute(select(Ticket).where(
        Ticket.tenant_id == tenant_id, Ticket.id == tid))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t


def _parse_assignee(v: str | None) -> uuid.UUID | None:
    if not v:
        return None
    try:
        return uuid.UUID(v)
    except ValueError:
        raise HTTPException(400, "assignee_id must be a UUID")


@router.post("", status_code=201)
async def create_ticket(body: TicketIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.priority not in VALID_PRIORITY:
        raise HTTPException(400, f"Invalid priority. Valid: {', '.join(sorted(VALID_PRIORITY))}")
    t = Ticket(
        tenant_id=auth.tenant_id,
        number=await _next_number(db, auth.tenant_id),
        subject=body.subject,
        description=body.description,
        requester_email=body.requester_email,
        category=body.category,
        priority=body.priority,
        status="open",
        assignee_id=_parse_assignee(body.assignee_id),
        sla_hours=SLA_HOURS[body.priority],
        created_by=auth.user_id,
    )
    db.add(t)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="ticket.created",
                   payload={"ticket_id": str(t.id), "number": t.number,
                            "subject": t.subject, "priority": t.priority},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(t)
    return _serialize(t)


@router.get("")
async def list_tickets(status: str | None = None, priority: str | None = None,
                       category: str | None = None, assignee_id: str | None = None,
                       unassigned: bool = False, breached: bool = False,
                       auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Ticket).where(Ticket.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Ticket.status == status)
    if priority:
        if priority not in VALID_PRIORITY:
            raise HTTPException(400, f"Invalid priority. Valid: {', '.join(sorted(VALID_PRIORITY))}")
        stmt = stmt.where(Ticket.priority == priority)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if assignee_id:
        stmt = stmt.where(Ticket.assignee_id == _parse_assignee(assignee_id))
    if unassigned:
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    rows = (await db.execute(stmt.order_by(Ticket.created_at.desc()))).scalars().all()
    items = [_serialize(t) for t in rows]
    if breached:
        items = [i for i in items if i["sla_breached"]]
    return {"items": items, "total": len(items)}


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_ticket(db, auth.tenant_id, ticket_id))


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: uuid.UUID, body: TicketPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status == "closed":
        raise HTTPException(409, "Ticket is closed; reopen it before editing")
    if body.subject is not None:
        t.subject = body.subject
    if body.description is not None:
        t.description = body.description
    if body.requester_email is not None:
        t.requester_email = body.requester_email
    if body.category is not None:
        t.category = body.category
    if body.priority is not None:
        if body.priority not in VALID_PRIORITY:
            raise HTTPException(400, f"Invalid priority. Valid: {', '.join(sorted(VALID_PRIORITY))}")
        t.priority = body.priority
        t.sla_hours = SLA_HOURS[body.priority]
    if body.assignee_id is not None:
        t.assignee_id = _parse_assignee(body.assignee_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="ticket.updated",
                   payload={"ticket_id": str(t.id), "number": t.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(t)
    return _serialize(t)


@router.delete("/{ticket_id}", status_code=200)
async def delete_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="ticket.deleted",
                   payload={"ticket_id": str(t.id), "number": t.number}, actor_id=auth.user_id)
    await db.delete(t)
    await db.commit()
    return {"deleted": True}


async def _set_status(t: Ticket, db, auth, new_status: str, event: str, stamp: str | None = None):
    t.status = new_status
    now = datetime.now(timezone.utc).isoformat()
    if stamp == "resolved":
        t.resolved_at = now
    elif stamp == "closed":
        t.closed_at = now
    await bus.emit(db, tenant_id=auth.tenant_id, event_type=event,
                   payload={"ticket_id": str(t.id), "number": t.number, "status": new_status},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(t)
    return _serialize(t)


@router.post("/{ticket_id}/start")
async def start_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status != "open":
        raise HTTPException(409, f"Ticket is {t.status}; only open tickets can be started")
    return await _set_status(t, db, auth, "in_progress", "ticket.started")


@router.post("/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status not in ("open", "in_progress"):
        raise HTTPException(409, f"Ticket is {t.status}; only open/in_progress tickets can be resolved")
    return await _set_status(t, db, auth, "resolved", "ticket.resolved", stamp="resolved")


@router.post("/{ticket_id}/close")
async def close_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status != "resolved":
        raise HTTPException(409, f"Ticket is {t.status}; only resolved tickets can be closed")
    return await _set_status(t, db, auth, "closed", "ticket.closed", stamp="closed")


@router.post("/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status not in ("resolved", "closed"):
        raise HTTPException(409, f"Ticket is {t.status}; only resolved/closed tickets can be reopened")
    t.resolved_at = ""
    t.closed_at = ""
    return await _set_status(t, db, auth, "open", "ticket.reopened")


@router.post("/{ticket_id}/assign")
async def assign_ticket(ticket_id: uuid.UUID, body: dict, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if t.status == "closed":
        raise HTTPException(409, "Ticket is closed; reopen it before assigning")
    t.assignee_id = _parse_assignee(body.get("assignee_id"))
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="ticket.assigned",
                   payload={"ticket_id": str(t.id), "number": t.number,
                            "assignee_id": str(t.assignee_id) if t.assignee_id else None},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(t)
    return _serialize(t)


# ---------------- comments ----------------

@router.post("/{ticket_id}/comments", status_code=201)
async def add_comment(ticket_id: uuid.UUID, body: CommentIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    t = await _get_ticket(db, auth.tenant_id, ticket_id)
    if not body.body.strip():
        raise HTTPException(400, "Comment body cannot be empty")
    c = TicketComment(
        tenant_id=auth.tenant_id, ticket_id=t.id, body=body.body,
        internal=body.internal, author_id=auth.user_id,
    )
    db.add(c)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="ticket.commented",
                   payload={"ticket_id": str(t.id), "number": t.number,
                            "comment_id": str(c.id), "internal": c.internal},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize_comment(c)


@router.get("/{ticket_id}/comments")
async def list_comments(ticket_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_ticket(db, auth.tenant_id, ticket_id)
    rows = (await db.execute(select(TicketComment).where(
        TicketComment.tenant_id == auth.tenant_id, TicketComment.ticket_id == ticket_id,
    ).order_by(TicketComment.created_at.asc()))).scalars().all()
    return {"items": [_serialize_comment(c) for c in rows], "total": len(rows)}
