"""Billing service (Phase L): plan catalog, usage metering, limit enforcement.

Plans are defined in code (self-hosted: no external billing provider). Usage
is computed live from the DB so it can never drift. Limits are enforced at the
kernel chokepoints (member invites, record creation) via ensure_within_limits.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.models.agent import Agent
from truss_kernel.models.billing import Invoice, Subscription
from truss_kernel.models.metadata import Record
from truss_kernel.models.tenant import Membership

# ---------------- plan catalog ----------------
# price_cents is per seat per month. limits use None = unlimited.
# The default (free) plan is generous: Truss is self-hosted-first, so limits
# only bite when an operator tightens them or a tenant picks a capped plan.
PLANS: dict[str, dict] = {
    "free": {
        "name": "Free",
        "price_cents": 0,
        "limits": {"members": 25, "records": 100000, "agents": 25},
        "description": "Self-hosted default. Generous caps, no charge.",
    },
    "trial": {
        "name": "Trial",
        "price_cents": 0,
        "limits": {"members": 2, "records": 5, "agents": 1},
        "description": "Evaluation plan with tight caps (used to exercise limit enforcement).",
    },
    "pro": {
        "name": "Pro",
        "price_cents": 1200,  # $12 / seat / month
        "limits": {"members": 10, "records": 50000, "agents": 10},
        "description": "For small teams. 10 members, 50k records, 10 AI employees.",
    },
    "business": {
        "name": "Business",
        "price_cents": 2900,  # $29 / seat / month
        "limits": {"members": None, "records": None, "agents": None},
        "description": "For growing orgs. Unlimited members, records, and AI employees.",
    },
}

# plans shown in the public catalog (trial is internal/test-only)
PUBLIC_PLANS = ["free", "pro", "business"]

DEFAULT_PLAN = "free"
PERIOD_DAYS = 30


def plan_limits(plan: str) -> dict:
    return PLANS.get(plan, PLANS[DEFAULT_PLAN])["limits"]


# ---------------- subscription lifecycle ----------------

async def get_or_create_subscription(db: AsyncSession, tenant_id) -> Subscription:
    """Every tenant gets a free subscription on first billing touch."""
    sub = (await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if sub is None:
        now = datetime.now(timezone.utc)
        sub = Subscription(
            tenant_id=tenant_id,
            plan=DEFAULT_PLAN,
            status="active",
            seats=1,
            current_period_start=now,
            current_period_end=now + timedelta(days=PERIOD_DAYS),
        )
        db.add(sub)
        await db.flush()
    return sub


async def change_plan(
    db: AsyncSession, tenant_id, plan: str, seats: int
) -> tuple[Subscription, Invoice]:
    """Switch plan (mock checkout). Creates a prorated-style invoice for the new period."""
    if plan not in PLANS:
        raise HTTPException(422, f"unknown plan: {plan}")
    if seats < 1:
        raise HTTPException(422, "seats must be >= 1")

    sub = await get_or_create_subscription(db, tenant_id)
    old_plan = sub.plan
    now = datetime.now(timezone.utc)

    sub.plan = plan
    sub.seats = seats
    sub.status = "active"
    sub.cancel_at_period_end = False
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=PERIOD_DAYS)
    await db.flush()

    # invoice for the new period (mock payment: instantly paid)
    unit = PLANS[plan]["price_cents"]
    amount = unit * seats
    count = (await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id)
    )).scalar_one()
    invoice = Invoice(
        tenant_id=tenant_id,
        subscription_id=sub.id,
        number=f"INV-{count + 1:04d}",
        amount_cents=amount,
        currency="USD",
        status="paid",
        period_start=now,
        period_end=sub.current_period_end,
        lines={
            "description": f"{PLANS[plan]['name']} plan — {seats} seat(s)",
            "qty": seats,
            "unit_cents": unit,
            "from_plan": old_plan,
        },
    )
    db.add(invoice)
    await db.flush()
    return sub, invoice


async def cancel(db: AsyncSession, tenant_id) -> Subscription:
    sub = await get_or_create_subscription(db, tenant_id)
    sub.cancel_at_period_end = True
    await db.flush()
    return sub


# ---------------- usage metering ----------------

async def usage(db: AsyncSession, tenant_id) -> dict:
    members = (await db.execute(
        select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant_id)
    )).scalar_one()
    records = (await db.execute(
        select(func.count()).select_from(Record).where(
            Record.tenant_id == tenant_id, Record.deleted_at.is_(None)
        )
    )).scalar_one()
    agents = (await db.execute(
        select(func.count()).select_from(Agent).where(Agent.tenant_id == tenant_id)
    )).scalar_one()
    return {"members": int(members), "records": int(records), "agents": int(agents)}


async def ensure_within_limits(db: AsyncSession, tenant_id, resource: str, add: int = 1) -> None:
    """Raise 402 if adding `add` units of `resource` would exceed the plan limit.

    No-op when settings.billing_enforce is False (self-hosted operators can
    switch limits off entirely).
    """
    from truss_kernel.config import settings
    if not settings.billing_enforce:
        return
    sub = await get_or_create_subscription(db, tenant_id)
    limits = plan_limits(sub.plan)
    cap = limits.get(resource)
    if cap is None:
        return  # unlimited
    current = (await usage(db, tenant_id)).get(resource, 0)
    if current + add > cap:
        raise HTTPException(
            402,
            f"Plan limit reached: {sub.plan} allows {cap} {resource}. "
            f"You have {current}. Upgrade at /api/billing/checkout.",
        )
