"""Inventory routes (Phase U): products, stock adjustments, low-stock alerts."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.inventory import Product, StockAdjustment

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=100)
    description: str = ""
    category: str = "General"
    price_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    quantity: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)


class ProductUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    reorder_point: int | None = Field(default=None, ge=0)
    active: bool | None = None


class AdjustIn(BaseModel):
    kind: str  # in | out | set
    delta: int
    reason: str = ""


def _serialize_product(p: Product) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "sku": p.sku,
        "description": p.description,
        "category": p.category,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "quantity": p.quantity,
        "reorder_point": p.reorder_point,
        "low_stock": p.quantity <= p.reorder_point,
        "active": p.active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_adjustment(a: StockAdjustment) -> dict:
    return {
        "id": str(a.id),
        "product_id": str(a.product_id),
        "kind": a.kind,
        "delta": a.delta,
        "reason": a.reason,
        "adjusted_by": str(a.adjusted_by) if a.adjusted_by else None,
        "resulting_quantity": a.resulting_quantity,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _get_product(db: AsyncSession, tenant_id, product_id: uuid.UUID) -> Product:
    product = (await db.execute(select(Product).where(
        Product.id == product_id, Product.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if product is None:
        raise HTTPException(404, "product not found")
    return product


@router.post("/products", status_code=201)
async def create_product(body: ProductIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(Product).where(
        Product.tenant_id == auth.tenant_id, Product.sku == body.sku,
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"SKU '{body.sku}' already exists")
    product = Product(
        tenant_id=auth.tenant_id,
        name=body.name,
        sku=body.sku,
        description=body.description,
        category=body.category,
        price_cents=body.price_cents,
        currency=body.currency.upper(),
        quantity=body.quantity,
        reorder_point=body.reorder_point,
    )
    db.add(product)
    await db.flush()
    # record the initial stock as an adjustment for a complete audit trail
    if body.quantity > 0:
        db.add(StockAdjustment(
            tenant_id=auth.tenant_id, product_id=product.id, kind="set",
            delta=body.quantity, reason="initial stock", adjusted_by=auth.user_id,
            resulting_quantity=body.quantity,
        ))
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="inventory.product_created",
        payload={"product_id": str(product.id), "name": product.name, "sku": product.sku},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_product(product)


@router.get("/products")
async def list_products(
    category: str | None = None,
    low_stock: bool | None = None,
    active: bool | None = None,
    q: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.tenant_id == auth.tenant_id)
    if category:
        stmt = stmt.where(Product.category == category)
    if active is not None:
        stmt = stmt.where(Product.active == active)
    rows = (await db.execute(stmt.order_by(Product.name))).scalars().all()
    if q:
        needle = q.lower()
        rows = [p for p in rows if needle in p.name.lower() or needle in p.sku.lower()]
    if low_stock is True:
        rows = [p for p in rows if p.quantity <= p.reorder_point]
    elif low_stock is False:
        rows = [p for p in rows if p.quantity > p.reorder_point]
    return {"items": [_serialize_product(p) for p in rows], "total": len(rows)}


@router.get("/products/{product_id}")
async def get_product(product_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_product(await _get_product(db, auth.tenant_id, product_id))


@router.patch("/products/{product_id}")
async def update_product(product_id: uuid.UUID, body: ProductUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    product = await _get_product(db, auth.tenant_id, product_id)
    if body.name is not None:
        product.name = body.name
    if body.description is not None:
        product.description = body.description
    if body.category is not None:
        product.category = body.category
    if body.price_cents is not None:
        product.price_cents = body.price_cents
    if body.currency is not None:
        product.currency = body.currency.upper()
    if body.reorder_point is not None:
        product.reorder_point = body.reorder_point
    if body.active is not None:
        product.active = body.active
    await db.commit()
    return _serialize_product(product)


@router.delete("/products/{product_id}")
async def delete_product(product_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    product = await _get_product(db, auth.tenant_id, product_id)
    await db.delete(product)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="inventory.product_deleted",
        payload={"product_id": str(product_id), "name": product.name, "sku": product.sku},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


# ---------------- stock adjustments ----------------

@router.post("/products/{product_id}/adjust", status_code=201)
async def adjust_stock(product_id: uuid.UUID, body: AdjustIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    product = await _get_product(db, auth.tenant_id, product_id)
    if body.kind not in ("in", "out", "set"):
        raise HTTPException(422, "kind must be one of: in, out, set")

    if body.kind == "in":
        if body.delta <= 0:
            raise HTTPException(422, "'in' adjustment requires a positive delta")
        product.quantity += body.delta
    elif body.kind == "out":
        if body.delta <= 0:
            raise HTTPException(422, "'out' adjustment requires a positive delta")
        if body.delta > product.quantity:
            raise HTTPException(409, f"cannot remove {body.delta}; only {product.quantity} in stock")
        product.quantity -= body.delta
    else:  # set
        if body.delta < 0:
            raise HTTPException(422, "'set' adjustment requires a non-negative delta")
        product.quantity = body.delta

    adjustment = StockAdjustment(
        tenant_id=auth.tenant_id,
        product_id=product.id,
        kind=body.kind,
        delta=body.delta,
        reason=body.reason,
        adjusted_by=auth.user_id,
        resulting_quantity=product.quantity,
    )
    db.add(adjustment)
    await db.flush()

    event_type = "inventory.stock_adjusted"
    if product.quantity <= product.reorder_point:
        event_type = "inventory.low_stock"
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type=event_type,
        payload={
            "product_id": str(product.id), "name": product.name, "sku": product.sku,
            "kind": body.kind, "delta": body.delta, "quantity": product.quantity,
            "reorder_point": product.reorder_point,
        },
        actor_id=auth.user_id,
    )
    await db.commit()
    return {
        "product": _serialize_product(product),
        "adjustment": _serialize_adjustment(adjustment),
    }


@router.get("/products/{product_id}/adjustments")
async def list_adjustments(product_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_product(db, auth.tenant_id, product_id)
    rows = (await db.execute(select(StockAdjustment).where(
        StockAdjustment.tenant_id == auth.tenant_id, StockAdjustment.product_id == product_id,
    ).order_by(StockAdjustment.created_at.desc()))).scalars().all()
    return {"items": [_serialize_adjustment(a) for a in rows], "total": len(rows)}
