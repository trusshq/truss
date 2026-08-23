"""Loyalty routes (Phase AI): members, points ledger, rewards, redemptions."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.loyalty import (
    LoyaltyMember, LoyaltyPointEvent, LoyaltyRedemption, LoyaltyReward,
)

router = APIRouter(prefix="/api/loyalty", tags=["loyalty"])

VALID_MEMBER_STATUS = {"active", "inactive"}
VALID_REDEMPTION_STATUS = {"pending", "fulfilled", "cancelled"}

# tier thresholds (points)
TIER_THRESHOLDS = [("gold", 5000), ("silver", 1000)]


def _tier_for(points: int) -> str:
    for name, threshold in TIER_THRESHOLDS:
        if points >= threshold:
            return name
    return "bronze"


class MemberIn(BaseModel):
    name: str
    email: str = ""
    phone: str = ""


class MemberPatch(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None


class PointsIn(BaseModel):
    delta: int = Field(..., description="Positive to award, negative to deduct")
    reason: str = ""


class RewardIn(BaseModel):
    name: str
    description: str = ""
    points_cost: int = Field(default=100, ge=1)


class RewardPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    points_cost: int | None = Field(default=None, ge=1)
    active: bool | None = None


class RedeemIn(BaseModel):
    member_id: str
    reward_id: str


def _serialize_member(m: LoyaltyMember) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "email": m.email,
        "phone": m.phone,
        "points": m.points,
        "tier": _tier_for(m.points),
        "status": m.status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_event(e: LoyaltyPointEvent) -> dict:
    return {
        "id": str(e.id),
        "member_id": str(e.member_id),
        "delta": e.delta,
        "reason": e.reason,
        "balance_after": e.balance_after,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _serialize_reward(r: LoyaltyReward) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": r.description,
        "points_cost": r.points_cost,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_redemption(rd: LoyaltyRedemption) -> dict:
    return {
        "id": str(rd.id),
        "member_id": str(rd.member_id),
        "reward_id": str(rd.reward_id),
        "points_spent": rd.points_spent,
        "status": rd.status,
        "created_at": rd.created_at.isoformat() if rd.created_at else None,
    }


async def _get_member(db: AsyncSession, tenant_id, mid: uuid.UUID) -> LoyaltyMember:
    m = (await db.execute(select(LoyaltyMember).where(
        LoyaltyMember.tenant_id == tenant_id, LoyaltyMember.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Loyalty member not found")
    return m


async def _get_reward(db: AsyncSession, tenant_id, rid: uuid.UUID) -> LoyaltyReward:
    r = (await db.execute(select(LoyaltyReward).where(
        LoyaltyReward.tenant_id == tenant_id, LoyaltyReward.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Reward not found")
    return r


async def _get_redemption(db: AsyncSession, tenant_id, rid: uuid.UUID) -> LoyaltyRedemption:
    rd = (await db.execute(select(LoyaltyRedemption).where(
        LoyaltyRedemption.tenant_id == tenant_id, LoyaltyRedemption.id == rid))).scalar_one_or_none()
    if not rd:
        raise HTTPException(404, "Redemption not found")
    return rd


def _parse_uuid(raw: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"{label} must be a UUID")


# ---- members ----

@router.post("/members", status_code=201)
async def create_member(body: MemberIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    m = LoyaltyMember(
        tenant_id=auth.tenant_id, name=body.name, email=body.email, phone=body.phone,
        points=0, status="active", created_by=auth.user_id,
    )
    db.add(m)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.member_created",
                   payload={"member_id": str(m.id), "name": m.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(m)
    return _serialize_member(m)


@router.get("/members")
async def list_members(status: str | None = None, tier: str | None = None,
                       auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(LoyaltyMember).where(LoyaltyMember.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_MEMBER_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_MEMBER_STATUS))}")
        stmt = stmt.where(LoyaltyMember.status == status)
    rows = (await db.execute(stmt.order_by(LoyaltyMember.created_at.desc()))).scalars().all()
    items = [_serialize_member(m) for m in rows]
    if tier:
        items = [it for it in items if it["tier"] == tier]
    return {"items": items, "total": len(items)}


@router.get("/members/{member_id}")
async def get_member(member_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    m = await _get_member(db, auth.tenant_id, member_id)
    return _serialize_member(m)


@router.patch("/members/{member_id}")
async def update_member(member_id: uuid.UUID, body: MemberPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    m = await _get_member(db, auth.tenant_id, member_id)
    if body.name is not None:
        m.name = body.name
    if body.email is not None:
        m.email = body.email
    if body.phone is not None:
        m.phone = body.phone
    if body.status is not None:
        if body.status not in VALID_MEMBER_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_MEMBER_STATUS))}")
        m.status = body.status
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.member_updated",
                   payload={"member_id": str(m.id), "name": m.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(m)
    return _serialize_member(m)


@router.delete("/members/{member_id}", status_code=200)
async def delete_member(member_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    m = await _get_member(db, auth.tenant_id, member_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.member_deleted",
                   payload={"member_id": str(m.id), "name": m.name}, actor_id=auth.user_id)
    await db.delete(m)
    await db.commit()
    return {"deleted": True}


# ---- points ----

@router.post("/members/{member_id}/points", status_code=201)
async def adjust_points(member_id: uuid.UUID, body: PointsIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    m = await _get_member(db, auth.tenant_id, member_id)
    if m.status != "active":
        raise HTTPException(409, "Member is inactive; cannot adjust points")
    if body.delta == 0:
        raise HTTPException(400, "delta must be non-zero")
    new_balance = m.points + body.delta
    if new_balance < 0:
        raise HTTPException(400, f"Insufficient points: balance {m.points}, delta {body.delta}")
    m.points = new_balance
    ev = LoyaltyPointEvent(
        tenant_id=auth.tenant_id, member_id=member_id, delta=body.delta,
        reason=body.reason, balance_after=new_balance, actor_id=auth.user_id,
    )
    db.add(ev)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.points_adjusted",
                   payload={"member_id": str(member_id), "delta": body.delta, "balance": new_balance},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(ev)
    return _serialize_event(ev)


@router.get("/members/{member_id}/points")
async def list_point_events(member_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_member(db, auth.tenant_id, member_id)
    rows = (await db.execute(select(LoyaltyPointEvent).where(
        LoyaltyPointEvent.tenant_id == auth.tenant_id, LoyaltyPointEvent.member_id == member_id,
    ).order_by(LoyaltyPointEvent.created_at.desc()))).scalars().all()
    return {"items": [_serialize_event(e) for e in rows], "total": len(rows)}


# ---- rewards ----

@router.post("/rewards", status_code=201)
async def create_reward(body: RewardIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    r = LoyaltyReward(
        tenant_id=auth.tenant_id, name=body.name, description=body.description,
        points_cost=body.points_cost, active=True,
    )
    db.add(r)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.reward_created",
                   payload={"reward_id": str(r.id), "name": r.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_reward(r)


@router.get("/rewards")
async def list_rewards(active: bool | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(LoyaltyReward).where(LoyaltyReward.tenant_id == auth.tenant_id)
    if active is not None:
        stmt = stmt.where(LoyaltyReward.active == active)
    rows = (await db.execute(stmt.order_by(LoyaltyReward.points_cost.asc()))).scalars().all()
    return {"items": [_serialize_reward(r) for r in rows], "total": len(rows)}


@router.patch("/rewards/{reward_id}")
async def update_reward(reward_id: uuid.UUID, body: RewardPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    r = await _get_reward(db, auth.tenant_id, reward_id)
    if body.name is not None:
        r.name = body.name
    if body.description is not None:
        r.description = body.description
    if body.points_cost is not None:
        r.points_cost = body.points_cost
    if body.active is not None:
        r.active = body.active
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.reward_updated",
                   payload={"reward_id": str(r.id), "name": r.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_reward(r)


@router.delete("/rewards/{reward_id}", status_code=200)
async def delete_reward(reward_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await _get_reward(db, auth.tenant_id, reward_id)
    refs = (await db.execute(select(LoyaltyRedemption).where(
        LoyaltyRedemption.tenant_id == auth.tenant_id, LoyaltyRedemption.reward_id == reward_id))).scalars().all()
    if refs:
        raise HTTPException(409, "Reward has redemptions; cannot delete")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.reward_deleted",
                   payload={"reward_id": str(r.id), "name": r.name}, actor_id=auth.user_id)
    await db.delete(r)
    await db.commit()
    return {"deleted": True}


# ---- redemptions ----

@router.post("/redemptions", status_code=201)
async def redeem(body: RedeemIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    mid = _parse_uuid(body.member_id, "member_id")
    rid = _parse_uuid(body.reward_id, "reward_id")
    m = await _get_member(db, auth.tenant_id, mid)
    r = await _get_reward(db, auth.tenant_id, rid)
    if m.status != "active":
        raise HTTPException(409, "Member is inactive; cannot redeem")
    if not r.active:
        raise HTTPException(409, "Reward is inactive; cannot redeem")
    if m.points < r.points_cost:
        raise HTTPException(400, f"Insufficient points: balance {m.points}, cost {r.points_cost}")
    m.points -= r.points_cost
    rd = LoyaltyRedemption(
        tenant_id=auth.tenant_id, member_id=mid, reward_id=rid,
        points_spent=r.points_cost, status="pending",
    )
    db.add(rd)
    ev = LoyaltyPointEvent(
        tenant_id=auth.tenant_id, member_id=mid, delta=-r.points_cost,
        reason=f"Redeemed: {r.name}", balance_after=m.points, actor_id=auth.user_id,
    )
    db.add(ev)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.redeemed",
                   payload={"member_id": str(mid), "reward_id": str(rid), "redemption_id": str(rd.id),
                            "points_spent": r.points_cost}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(rd)
    return _serialize_redemption(rd)


@router.get("/redemptions")
async def list_redemptions(status: str | None = None, member_id: str | None = None,
                           auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(LoyaltyRedemption).where(LoyaltyRedemption.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_REDEMPTION_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_REDEMPTION_STATUS))}")
        stmt = stmt.where(LoyaltyRedemption.status == status)
    if member_id:
        stmt = stmt.where(LoyaltyRedemption.member_id == _parse_uuid(member_id, "member_id"))
    rows = (await db.execute(stmt.order_by(LoyaltyRedemption.created_at.desc()))).scalars().all()
    return {"items": [_serialize_redemption(rd) for rd in rows], "total": len(rows)}


@router.post("/redemptions/{redemption_id}/fulfill")
async def fulfill_redemption(redemption_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    rd = await _get_redemption(db, auth.tenant_id, redemption_id)
    if rd.status != "pending":
        raise HTTPException(409, f"Redemption is {rd.status}; only pending can be fulfilled")
    rd.status = "fulfilled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.redemption_fulfilled",
                   payload={"redemption_id": str(rd.id), "member_id": str(rd.member_id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(rd)
    return _serialize_redemption(rd)


@router.post("/redemptions/{redemption_id}/cancel")
async def cancel_redemption(redemption_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    rd = await _get_redemption(db, auth.tenant_id, redemption_id)
    if rd.status != "pending":
        raise HTTPException(409, f"Redemption is {rd.status}; only pending can be cancelled")
    rd.status = "cancelled"
    # refund the points
    m = await _get_member(db, auth.tenant_id, rd.member_id)
    m.points += rd.points_spent
    ev = LoyaltyPointEvent(
        tenant_id=auth.tenant_id, member_id=rd.member_id, delta=rd.points_spent,
        reason="Redemption cancelled (refund)", balance_after=m.points, actor_id=auth.user_id,
    )
    db.add(ev)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="loyalty.redemption_cancelled",
                   payload={"redemption_id": str(rd.id), "member_id": str(rd.member_id),
                            "points_refunded": rd.points_spent}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(rd)
    return _serialize_redemption(rd)
