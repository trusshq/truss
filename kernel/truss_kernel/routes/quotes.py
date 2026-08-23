"""Quotes routes (Phase Y): CRUD, lifecycle, and convert-to-invoice."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.quotes import Quote
from truss_kernel.services import records as records_svc

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

VALID_STATUS = {"draft", "sent", "accepted", "declined", "converted"}


class LineItemIn(BaseModel):
    description: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_price_cents: int = Field(default=0, ge=0)


class QuoteIn(BaseModel):
    customer_name: str = ""
    object: str = ""
    record_id: str | None = None
    title: str = ""
    notes: str = ""
    currency: str = "USD"
    valid_until: str = ""
    line_items: list[LineItemIn] = Field(default_factory=list)


def _compute_totals(items: list[dict], tax_rate: float = 0.0) -> tuple[int, int, int]:
    subtotal = sum(int(i.get("quantity", 1)) * int(i.get("unit_price_cents", 0)) for i in items)
    tax = int(round(subtotal * tax_rate))
    return subtotal, tax, subtotal + tax


def _quote_to_dict(q: Quote) -> dict:
    return {
        "id": str(q.id),
        "number": q.number,
        "customer_name": q.customer_name,
        "object": q.object,
        "record_id": str(q.record_id) if q.record_id else None,
        "title": q.title,
        "notes": q.notes,
        "currency": q.currency,
        "status": q.status,
        "valid_until": q.valid_until,
        "line_items": q.line_items,
        "subtotal_cents": q.subtotal_cents,
        "tax_cents": q.tax_cents,
        "total_cents": q.total_cents,
        "invoice_record_id": str(q.invoice_record_id) if q.invoice_record_id else None,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


async def _next_number(db: AsyncSession, tenant_id) -> str:
    n = (await db.execute(
        select(func.count()).select_from(Quote).where(Quote.tenant_id == tenant_id)
    )).scalar_one()
    return f"QT-{n + 1:04d}"


@router.post("", status_code=201)
async def create_quote(body: QuoteIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    items = [i.model_dump() for i in body.line_items]
    subtotal, tax, total = _compute_totals(items)
    record_id = None
    if body.record_id:
        try:
            record_id = uuid.UUID(body.record_id)
        except ValueError:
            raise HTTPException(400, "record_id must be a UUID")
    q = Quote(
        tenant_id=auth.tenant_id,
        number=await _next_number(db, auth.tenant_id),
        customer_name=body.customer_name,
        object=body.object,
        record_id=record_id,
        title=body.title,
        notes=body.notes,
        currency=body.currency,
        status="draft",
        valid_until=body.valid_until,
        line_items=items,
        subtotal_cents=subtotal,
        tax_cents=tax,
        total_cents=total,
        created_by=auth.user_id,
    )
    db.add(q)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="quote.created",
                   payload={"quote_id": str(q.id), "number": q.number,
                            "customer": q.customer_name, "total_cents": q.total_cents},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    return _quote_to_dict(q)


@router.get("")
async def list_quotes(status: str | None = None, customer: str | None = None,
                      auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Quote).where(Quote.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Quote.status == status)
    if customer:
        stmt = stmt.where(Quote.customer_name.ilike(f"%{customer}%"))
    rows = (await db.execute(stmt.order_by(Quote.created_at.desc()))).scalars().all()
    return {"items": [_quote_to_dict(q) for q in rows], "total": len(rows)}


@router.get("/{quote_id}")
async def get_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    return _quote_to_dict(q)


@router.patch("/{quote_id}")
async def update_quote(quote_id: uuid.UUID, body: QuoteIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.status not in ("draft", "sent"):
        raise HTTPException(409, f"Quote is {q.status}; only draft/sent quotes can be edited")
    q.customer_name = body.customer_name
    q.object = body.object
    q.record_id = uuid.UUID(body.record_id) if body.record_id else None
    q.title = body.title
    q.notes = body.notes
    q.currency = body.currency
    q.valid_until = body.valid_until
    q.line_items = [i.model_dump() for i in body.line_items]
    q.subtotal_cents, q.tax_cents, q.total_cents = _compute_totals(q.line_items)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="quote.updated",
                   payload={"quote_id": str(q.id), "number": q.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    return _quote_to_dict(q)


@router.delete("/{quote_id}", status_code=200)
async def delete_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="quote.deleted",
                   payload={"quote_id": str(q.id), "number": q.number}, actor_id=auth.user_id)
    await db.delete(q)
    await db.commit()
    return {"deleted": True}


async def _set_status(q: Quote, db, auth, new_status: str, event: str):
    q.status = new_status
    await bus.emit(db, tenant_id=auth.tenant_id, event_type=event,
                   payload={"quote_id": str(q.id), "number": q.number, "status": new_status},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    return _quote_to_dict(q)


@router.post("/{quote_id}/send")
async def send_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.status != "draft":
        raise HTTPException(409, f"Quote is {q.status}; only draft quotes can be sent")
    return await _set_status(q, db, auth, "sent", "quote.sent")


@router.post("/{quote_id}/accept")
async def accept_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.status != "sent":
        raise HTTPException(409, f"Quote is {q.status}; only sent quotes can be accepted")
    return await _set_status(q, db, auth, "accepted", "quote.accepted")


@router.post("/{quote_id}/decline")
async def decline_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.status != "sent":
        raise HTTPException(409, f"Quote is {q.status}; only sent quotes can be declined")
    return await _set_status(q, db, auth, "declined", "quote.declined")


@router.post("/{quote_id}/convert")
async def convert_quote(quote_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Convert an accepted quote into an invoice record (truss-invoices plugin)."""
    q = (await db.execute(select(Quote).where(
        Quote.tenant_id == auth.tenant_id, Quote.id == quote_id))).scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Quote not found")
    if q.status != "accepted":
        raise HTTPException(409, f"Quote is {q.status}; only accepted quotes can be converted")
    if q.invoice_record_id:
        raise HTTPException(409, "Quote already converted")
    # ensure the invoice object exists (installed via truss-invoices plugin);
    # use the service helper so fields are eager-loaded (async-safe)
    try:
        obj = await records_svc.get_object(db, auth.tenant_id, "invoice")
    except records_svc.ObjectNotFound:
        raise HTTPException(409, "The 'invoice' object is not available. Install the Invoices plugin first.")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items_text = "\n".join(
        f"{i.get('description', '')} x{i.get('quantity', 1)} @ {i.get('unit_price_cents', 0) / 100:.2f}"
        for i in q.line_items
    )
    data = {
        "number": f"INV-{q.number}",
        "customer": q.customer_name or q.title,
        "amount": q.total_cents / 100,
        "status": "Draft",
        "issue_date": today,
        "due_date": q.valid_until or today,
        "items": items_text,
        "notes": q.notes,
    }
    rec = await records_svc.create_record(db, auth.tenant_id, auth.user_id, obj, data)
    q.status = "converted"
    q.invoice_record_id = rec.id
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="quote.converted",
                   payload={"quote_id": str(q.id), "number": q.number,
                            "invoice_record_id": str(rec.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(q)
    out = _quote_to_dict(q)
    out["invoice_record_id"] = str(rec.id)
    return out
