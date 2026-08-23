"""Billing routes (Phase L): plans, subscription, usage, mock checkout, invoices."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.billing import Invoice
from truss_kernel.services import billing as svc

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan: str = Field(..., description="free | pro | business")
    seats: int = Field(1, ge=1, le=1000)


@router.get("/plans")
async def list_plans(auth: AuthContext = Depends(require_viewer)):
    """Public plan catalog with limits and pricing."""
    return {
        "items": [
            {"id": pid, **svc.PLANS[pid]}
            for pid in svc.PUBLIC_PLANS
        ]
    }


@router.get("/subscription")
async def get_subscription(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    sub = await svc.get_or_create_subscription(db, auth.tenant_id)
    await db.commit()
    return {
        "plan": sub.plan,
        "plan_name": svc.PLANS[sub.plan]["name"],
        "status": sub.status,
        "seats": sub.seats,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "current_period_start": sub.current_period_start.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "price_cents_per_seat": svc.PLANS[sub.plan]["price_cents"],
    }


@router.get("/usage")
async def get_usage(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Live usage vs plan limits (None = unlimited)."""
    sub = await svc.get_or_create_subscription(db, auth.tenant_id)
    await db.commit()
    used = await svc.usage(db, auth.tenant_id)
    limits = svc.plan_limits(sub.plan)
    return {
        "plan": sub.plan,
        "usage": used,
        "limits": limits,
        "headroom": {
            k: (None if limits.get(k) is None else max(0, limits[k] - used.get(k, 0)))
            for k in used
        },
    }


@router.post("/checkout", status_code=201)
async def checkout(body: CheckoutIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Mock checkout: switch plan + seats, issue an invoice (instantly 'paid')."""
    sub, invoice = await svc.change_plan(db, auth.tenant_id, body.plan, body.seats)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="billing.plan_changed",
        payload={"plan": body.plan, "seats": body.seats, "invoice": invoice.number},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {
        "ok": True,
        "plan": sub.plan,
        "seats": sub.seats,
        "invoice": invoice.number,
        "amount_cents": invoice.amount_cents,
        "period_end": sub.current_period_end.isoformat(),
    }


@router.post("/cancel", status_code=200)
async def cancel_subscription(auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Cancel at period end (downgrade to free when the period lapses)."""
    sub = await svc.cancel(db, auth.tenant_id)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="billing.canceled",
        payload={"plan": sub.plan, "at_period_end": sub.current_period_end.isoformat()},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True, "plan": sub.plan, "cancel_at_period_end": True,
            "period_end": sub.current_period_end.isoformat()}


@router.get("/invoices")
async def list_invoices(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Invoice).where(Invoice.tenant_id == auth.tenant_id)
        .order_by(Invoice.created_at.desc()).limit(100)
    )).scalars().all()
    return {
        "items": [
            {
                "id": str(i.id),
                "number": i.number,
                "amount_cents": i.amount_cents,
                "currency": i.currency,
                "status": i.status,
                "lines": i.lines,
                "period_start": i.period_start.isoformat(),
                "period_end": i.period_end.isoformat(),
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in rows
        ],
        "total": len(rows),
    }
