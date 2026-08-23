"""Purchase orders routes (Phase Z): CRUD, lifecycle, and receive-into-inventory."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.inventory import Product, StockAdjustment
from truss_kernel.models.purchase_orders import PurchaseOrder

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

VALID_STATUS = {"draft", "sent", "received", "cancelled"}


class POLineItemIn(BaseModel):
    product_id: str
    description: str = ""
    quantity: int = Field(default=1, ge=1)
    unit_cost_cents: int = Field(default=0, ge=0)


class POIn(BaseModel):
    vendor_name: str = ""
    notes: str = ""
    currency: str = "USD"
    expected_date: str = ""
    line_items: list[POLineItemIn] = Field(default_factory=list)


def _total(items: list[dict]) -> int:
    return sum(int(i.get("quantity", 1)) * int(i.get("unit_cost_cents", 0)) for i in items)


def _serialize(po: PurchaseOrder) -> dict:
    return {
        "id": str(po.id),
        "number": po.number,
        "vendor_name": po.vendor_name,
        "notes": po.notes,
        "currency": po.currency,
        "status": po.status,
        "expected_date": po.expected_date,
        "line_items": po.line_items,
        "total_cents": po.total_cents,
        "received_at": po.received_at,
        "created_at": po.created_at.isoformat() if po.created_at else None,
    }


async def _next_number(db: AsyncSession, tenant_id) -> str:
    n = (await db.execute(
        select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    )).scalar_one()
    return f"PO-{n + 1:04d}"


async def _get_po(db: AsyncSession, tenant_id, po_id: uuid.UUID) -> PurchaseOrder:
    po = (await db.execute(select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "Purchase order not found")
    return po


async def _validate_products(db: AsyncSession, tenant_id, items: list[POLineItemIn]) -> list[dict]:
    """Ensure every referenced product exists in this tenant; return serialized items."""
    out = []
    for it in items:
        try:
            pid = uuid.UUID(it.product_id)
        except ValueError:
            raise HTTPException(400, f"product_id must be a UUID: {it.product_id}")
        prod = (await db.execute(select(Product).where(
            Product.tenant_id == tenant_id, Product.id == pid))).scalar_one_or_none()
        if not prod:
            raise HTTPException(404, f"Product not found: {it.product_id}")
        out.append({
            "product_id": str(pid),
            "description": it.description or prod.name,
            "quantity": it.quantity,
            "unit_cost_cents": it.unit_cost_cents,
        })
    return out


@router.post("", status_code=201)
async def create_po(body: POIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    items = await _validate_products(db, auth.tenant_id, body.line_items)
    po = PurchaseOrder(
        tenant_id=auth.tenant_id,
        number=await _next_number(db, auth.tenant_id),
        vendor_name=body.vendor_name,
        notes=body.notes,
        currency=body.currency,
        status="draft",
        expected_date=body.expected_date,
        line_items=items,
        total_cents=_total(items),
        created_by=auth.user_id,
    )
    db.add(po)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.created",
                   payload={"po_id": str(po.id), "number": po.number,
                            "vendor": po.vendor_name, "total_cents": po.total_cents},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(po)
    return _serialize(po)


@router.get("")
async def list_pos(status: str | None = None, vendor: str | None = None,
                   auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(PurchaseOrder.status == status)
    if vendor:
        stmt = stmt.where(PurchaseOrder.vendor_name.ilike(f"%{vendor}%"))
    rows = (await db.execute(stmt.order_by(PurchaseOrder.created_at.desc()))).scalars().all()
    return {"items": [_serialize(po) for po in rows], "total": len(rows)}


@router.get("/{po_id}")
async def get_po(po_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_po(db, auth.tenant_id, po_id))


@router.patch("/{po_id}")
async def update_po(po_id: uuid.UUID, body: POIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    po = await _get_po(db, auth.tenant_id, po_id)
    if po.status != "draft":
        raise HTTPException(409, f"PO is {po.status}; only draft POs can be edited")
    items = await _validate_products(db, auth.tenant_id, body.line_items)
    po.vendor_name = body.vendor_name
    po.notes = body.notes
    po.currency = body.currency
    po.expected_date = body.expected_date
    po.line_items = items
    po.total_cents = _total(items)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.updated",
                   payload={"po_id": str(po.id), "number": po.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(po)
    return _serialize(po)


@router.delete("/{po_id}", status_code=200)
async def delete_po(po_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    po = await _get_po(db, auth.tenant_id, po_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.deleted",
                   payload={"po_id": str(po.id), "number": po.number}, actor_id=auth.user_id)
    await db.delete(po)
    await db.commit()
    return {"deleted": True}


@router.post("/{po_id}/send")
async def send_po(po_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    po = await _get_po(db, auth.tenant_id, po_id)
    if po.status != "draft":
        raise HTTPException(409, f"PO is {po.status}; only draft POs can be sent")
    po.status = "sent"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.sent",
                   payload={"po_id": str(po.id), "number": po.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(po)
    return _serialize(po)


@router.post("/{po_id}/cancel")
async def cancel_po(po_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    po = await _get_po(db, auth.tenant_id, po_id)
    if po.status not in ("draft", "sent"):
        raise HTTPException(409, f"PO is {po.status}; only draft/sent POs can be cancelled")
    po.status = "cancelled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.cancelled",
                   payload={"po_id": str(po.id), "number": po.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(po)
    return _serialize(po)


@router.post("/{po_id}/receive")
async def receive_po(po_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Receive a sent PO: apply a stock 'in' adjustment to each line item's product."""
    po = await _get_po(db, auth.tenant_id, po_id)
    if po.status != "sent":
        raise HTTPException(409, f"PO is {po.status}; only sent POs can be received")
    received = []
    for item in po.line_items:
        pid = uuid.UUID(item["product_id"])
        prod = (await db.execute(select(Product).where(
            Product.tenant_id == auth.tenant_id, Product.id == pid))).scalar_one_or_none()
        if not prod:
            raise HTTPException(409, f"Product {item['product_id']} no longer exists; cannot receive")
        qty = int(item.get("quantity", 1))
        prod.quantity += qty
        db.add(StockAdjustment(
            tenant_id=auth.tenant_id, product_id=prod.id, kind="in",
            delta=qty, reason=f"received PO {po.number}", adjusted_by=auth.user_id,
            resulting_quantity=prod.quantity,
        ))
        received.append({"product_id": str(prod.id), "quantity": qty, "new_quantity": prod.quantity})
    po.status = "received"
    po.received_at = datetime.now(timezone.utc).isoformat()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="purchase_order.received",
                   payload={"po_id": str(po.id), "number": po.number, "received": received},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(po)
    out = _serialize(po)
    out["received"] = received
    return out
