"""Subscriptions routes (Phase AE): plans, subscriptions, lifecycle, and MRR."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.subscriptions import CustomerSubscription, SubscriptionPlan

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

VALID_STATUS = {"active", "paused", "cancelled"}
VALID_INTERVAL = {"monthly", "yearly"}


class PlanIn(BaseModel):
    name: str
    description: str = ""
    interval: str = "monthly"
    price_cents: int = Field(default=0, ge=0)
    currency: str = "USD"
    active: bool = True


class PlanPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    interval: str | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    active: bool | None = None


class SubIn(BaseModel):
    plan_id: str
    customer: str
    current_period_end: str = ""


class SubPatch(BaseModel):
    customer: str | None = None
    current_period_end: str | None = None


def _serialize_plan(p: SubscriptionPlan) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "interval": p.interval,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "active": p.active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_sub(s: CustomerSubscription) -> dict:
    return {
        "id": str(s.id),
        "plan_id": str(s.plan_id),
        "customer": s.customer,
        "status": s.status,
        "current_period_end": s.current_period_end,
        "cancelled_at": s.cancelled_at,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _get_plan(db: AsyncSession, tenant_id, pid: uuid.UUID) -> SubscriptionPlan:
    p = (await db.execute(select(SubscriptionPlan).where(
        SubscriptionPlan.tenant_id == tenant_id, SubscriptionPlan.id == pid))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Plan not found")
    return p


async def _get_sub(db: AsyncSession, tenant_id, sid: uuid.UUID) -> CustomerSubscription:
    s = (await db.execute(select(CustomerSubscription).where(
        CustomerSubscription.tenant_id == tenant_id, CustomerSubscription.id == sid))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Subscription not found")
    return s


# ---- plans ----

@router.post("/plans", status_code=201)
async def create_plan(body: PlanIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.interval not in VALID_INTERVAL:
        raise HTTPException(400, f"Invalid interval. Valid: {', '.join(sorted(VALID_INTERVAL))}")
    p = SubscriptionPlan(
        tenant_id=auth.tenant_id, name=body.name, description=body.description,
        interval=body.interval, price_cents=body.price_cents, currency=body.currency,
        active=body.active,
    )
    db.add(p)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plan.created",
                   payload={"plan_id": str(p.id), "name": p.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(p)
    return _serialize_plan(p)


@router.get("/plans")
async def list_plans(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SubscriptionPlan).where(
        SubscriptionPlan.tenant_id == auth.tenant_id).order_by(SubscriptionPlan.created_at.desc()))).scalars().all()
    return {"items": [_serialize_plan(p) for p in rows], "total": len(rows)}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_plan(await _get_plan(db, auth.tenant_id, plan_id))


@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: uuid.UUID, body: PlanPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    p = await _get_plan(db, auth.tenant_id, plan_id)
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    if body.interval is not None:
        if body.interval not in VALID_INTERVAL:
            raise HTTPException(400, f"Invalid interval. Valid: {', '.join(sorted(VALID_INTERVAL))}")
        p.interval = body.interval
    if body.price_cents is not None:
        p.price_cents = body.price_cents
    if body.currency is not None:
        p.currency = body.currency
    if body.active is not None:
        p.active = body.active
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plan.updated",
                   payload={"plan_id": str(p.id), "name": p.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(p)
    return _serialize_plan(p)


@router.delete("/plans/{plan_id}", status_code=200)
async def delete_plan(plan_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = await _get_plan(db, auth.tenant_id, plan_id)
    # block delete if subscriptions reference it
    refs = (await db.execute(select(CustomerSubscription).where(
        CustomerSubscription.tenant_id == auth.tenant_id, CustomerSubscription.plan_id == plan_id))).scalars().all()
    if refs:
        raise HTTPException(409, f"Plan has {len(refs)} subscription(s); cancel them first")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="plan.deleted",
                   payload={"plan_id": str(p.id), "name": p.name}, actor_id=auth.user_id)
    await db.delete(p)
    await db.commit()
    return {"deleted": True}


# ---- subscriptions ----

@router.post("", status_code=201)
async def create_subscription(body: SubIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    try:
        pid = uuid.UUID(body.plan_id)
    except ValueError:
        raise HTTPException(400, "plan_id must be a UUID")
    plan = await _get_plan(db, auth.tenant_id, pid)
    if not plan.active:
        raise HTTPException(409, "Plan is inactive; activate it before subscribing")
    s = CustomerSubscription(
        tenant_id=auth.tenant_id, plan_id=pid, customer=body.customer,
        status="active", current_period_end=body.current_period_end,
        created_by=auth.user_id,
    )
    db.add(s)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.created",
                   payload={"subscription_id": str(s.id), "customer": s.customer, "plan": plan.name},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)


@router.get("")
async def list_subscriptions(status: str | None = None, plan_id: str | None = None,
                             auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(CustomerSubscription).where(CustomerSubscription.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(CustomerSubscription.status == status)
    if plan_id:
        try:
            stmt = stmt.where(CustomerSubscription.plan_id == uuid.UUID(plan_id))
        except ValueError:
            raise HTTPException(400, "plan_id must be a UUID")
    rows = (await db.execute(stmt.order_by(CustomerSubscription.created_at.desc()))).scalars().all()
    return {"items": [_serialize_sub(s) for s in rows], "total": len(rows)}


@router.get("/mrr")
async def mrr(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Monthly recurring revenue: sum of active subscription prices, normalized
    to monthly (yearly plans contribute price/12)."""
    subs = (await db.execute(select(CustomerSubscription).where(
        CustomerSubscription.tenant_id == auth.tenant_id, CustomerSubscription.status == "active"))).scalars().all()
    total = 0.0
    for s in subs:
        plan = await db.get(SubscriptionPlan, s.plan_id)
        if not plan:
            continue
        monthly = plan.price_cents if plan.interval == "monthly" else plan.price_cents / 12.0
        total += monthly
    return {"mrr_cents": round(total), "active_subscriptions": len(subs)}


@router.get("/{subscription_id}")
async def get_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_sub(await _get_sub(db, auth.tenant_id, subscription_id))


@router.patch("/{subscription_id}")
async def update_subscription(subscription_id: uuid.UUID, body: SubPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    if s.status == "cancelled":
        raise HTTPException(409, "Subscription is cancelled; reactivate before editing")
    if body.customer is not None:
        s.customer = body.customer
    if body.current_period_end is not None:
        s.current_period_end = body.current_period_end
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.updated",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)


@router.delete("/{subscription_id}", status_code=200)
async def delete_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.deleted",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.delete(s)
    await db.commit()
    return {"deleted": True}


@router.post("/{subscription_id}/pause")
async def pause_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    if s.status != "active":
        raise HTTPException(409, f"Subscription is {s.status}; only active subscriptions can be paused")
    s.status = "paused"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.paused",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)


@router.post("/{subscription_id}/resume")
async def resume_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    if s.status != "paused":
        raise HTTPException(409, f"Subscription is {s.status}; only paused subscriptions can be resumed")
    s.status = "active"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.resumed",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)


@router.post("/{subscription_id}/cancel")
async def cancel_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    if s.status == "cancelled":
        raise HTTPException(409, "Subscription is already cancelled")
    s.status = "cancelled"
    s.cancelled_at = datetime.now(timezone.utc).isoformat()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.cancelled",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)


@router.post("/{subscription_id}/reactivate")
async def reactivate_subscription(subscription_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    s = await _get_sub(db, auth.tenant_id, subscription_id)
    if s.status != "cancelled":
        raise HTTPException(409, f"Subscription is {s.status}; only cancelled subscriptions can be reactivated")
    s.status = "active"
    s.cancelled_at = ""
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="subscription.reactivated",
                   payload={"subscription_id": str(s.id), "customer": s.customer}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(s)
    return _serialize_sub(s)
