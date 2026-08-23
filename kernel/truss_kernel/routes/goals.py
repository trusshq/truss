"""Goals routes (Phase AG): CRUD, key results, progress rollup, lifecycle."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.goals import OKRGoal, OKRKeyResult

router = APIRouter(prefix="/api/goals", tags=["goals"])

VALID_STATUS = {"draft", "active", "achieved", "missed", "cancelled"}
FINISHED_STATUSES = {"achieved", "missed", "cancelled"}


class GoalIn(BaseModel):
    title: str
    description: str = ""
    period: str = ""
    owner_id: str | None = None


class GoalPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    period: str | None = None
    owner_id: str | None = None


class KRIn(BaseModel):
    title: str
    unit: str = ""
    target_value: float = Field(default=100.0, gt=0)
    current_value: float = Field(default=0.0, ge=0)
    weight: int = Field(default=1, ge=1)


class KRPatch(BaseModel):
    title: str | None = None
    unit: str | None = None
    target_value: float | None = Field(default=None, gt=0)
    current_value: float | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=1)


def _kr_completion(kr: OKRKeyResult) -> float:
    """Completion fraction for one key result, capped at 1.0."""
    if kr.target_value <= 0:
        return 0.0
    return min(kr.current_value / kr.target_value, 1.0)


def _goal_progress(krs: list[OKRKeyResult]) -> float:
    """Weighted average completion across key results, as a percentage."""
    total_weight = sum(kr.weight for kr in krs)
    if total_weight <= 0:
        return 0.0
    weighted = sum(_kr_completion(kr) * kr.weight for kr in krs)
    return round(weighted / total_weight * 100, 2)


def _serialize_kr(kr: OKRKeyResult) -> dict:
    return {
        "id": str(kr.id),
        "goal_id": str(kr.goal_id),
        "title": kr.title,
        "unit": kr.unit,
        "target_value": kr.target_value,
        "current_value": kr.current_value,
        "weight": kr.weight,
        "completion": round(_kr_completion(kr) * 100, 2),
        "created_at": kr.created_at.isoformat() if kr.created_at else None,
    }


def _serialize_goal(g: OKRGoal, krs: list[OKRKeyResult]) -> dict:
    return {
        "id": str(g.id),
        "title": g.title,
        "description": g.description,
        "period": g.period,
        "owner_id": str(g.owner_id) if g.owner_id else None,
        "status": g.status,
        "progress": _goal_progress(krs),
        "key_results": [_serialize_kr(kr) for kr in krs],
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


async def _get_goal(db: AsyncSession, tenant_id, gid: uuid.UUID) -> OKRGoal:
    g = (await db.execute(select(OKRGoal).where(
        OKRGoal.tenant_id == tenant_id, OKRGoal.id == gid))).scalar_one_or_none()
    if not g:
        raise HTTPException(404, "Goal not found")
    return g


async def _get_krs(db: AsyncSession, tenant_id, gid: uuid.UUID) -> list[OKRKeyResult]:
    return list((await db.execute(select(OKRKeyResult).where(
        OKRKeyResult.tenant_id == tenant_id, OKRKeyResult.goal_id == gid,
    ).order_by(OKRKeyResult.created_at.asc()))).scalars().all())


async def _get_kr(db: AsyncSession, tenant_id, kid: uuid.UUID) -> OKRKeyResult:
    kr = (await db.execute(select(OKRKeyResult).where(
        OKRKeyResult.tenant_id == tenant_id, OKRKeyResult.id == kid))).scalar_one_or_none()
    if not kr:
        raise HTTPException(404, "Key result not found")
    return kr


def _parse_owner(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(400, "owner_id must be a UUID")


@router.post("", status_code=201)
async def create_goal(body: GoalIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = OKRGoal(
        tenant_id=auth.tenant_id, title=body.title, description=body.description,
        period=body.period, owner_id=_parse_owner(body.owner_id),
        status="draft", created_by=auth.user_id,
    )
    db.add(g)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.created",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    return _serialize_goal(g, [])


@router.get("")
async def list_goals(status: str | None = None, period: str | None = None,
                     auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(OKRGoal).where(OKRGoal.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(OKRGoal.status == status)
    if period:
        stmt = stmt.where(OKRGoal.period == period)
    rows = (await db.execute(stmt.order_by(OKRGoal.created_at.desc()))).scalars().all()
    items = []
    for g in rows:
        krs = await _get_krs(db, auth.tenant_id, g.id)
        items.append(_serialize_goal(g, krs))
    return {"items": items, "total": len(items)}


@router.get("/{goal_id}")
async def get_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return _serialize_goal(g, krs)


@router.patch("/{goal_id}")
async def update_goal(goal_id: uuid.UUID, body: GoalPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status in FINISHED_STATUSES:
        raise HTTPException(409, f"Goal is {g.status}; only draft/active goals can be edited")
    if body.title is not None:
        g.title = body.title
    if body.description is not None:
        g.description = body.description
    if body.period is not None:
        g.period = body.period
    if body.owner_id is not None:
        g.owner_id = _parse_owner(body.owner_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.updated",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return _serialize_goal(g, krs)


@router.delete("/{goal_id}", status_code=200)
async def delete_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.deleted",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.delete(g)
    await db.commit()
    return {"deleted": True}


# ---- key results ----

@router.post("/{goal_id}/key-results", status_code=201)
async def create_key_result(goal_id: uuid.UUID, body: KRIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status in FINISHED_STATUSES:
        raise HTTPException(409, f"Goal is {g.status}; only draft/active goals can take key results")
    kr = OKRKeyResult(
        tenant_id=auth.tenant_id, goal_id=goal_id, title=body.title, unit=body.unit,
        target_value=body.target_value, current_value=body.current_value, weight=body.weight,
    )
    db.add(kr)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.key_result_created",
                   payload={"goal_id": str(goal_id), "key_result_id": str(kr.id), "title": kr.title},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(kr)
    return _serialize_kr(kr)


@router.get("/{goal_id}/key-results")
async def list_key_results(goal_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_goal(db, auth.tenant_id, goal_id)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return {"items": [_serialize_kr(kr) for kr in krs], "total": len(krs)}


@router.patch("/key-results/{kr_id}")
async def update_key_result(kr_id: uuid.UUID, body: KRPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    kr = await _get_kr(db, auth.tenant_id, kr_id)
    g = await _get_goal(db, auth.tenant_id, kr.goal_id)
    if g.status in FINISHED_STATUSES:
        raise HTTPException(409, f"Goal is {g.status}; its key results are locked")
    if body.title is not None:
        kr.title = body.title
    if body.unit is not None:
        kr.unit = body.unit
    if body.target_value is not None:
        kr.target_value = body.target_value
    if body.current_value is not None:
        kr.current_value = body.current_value
    if body.weight is not None:
        kr.weight = body.weight
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.key_result_updated",
                   payload={"goal_id": str(kr.goal_id), "key_result_id": str(kr.id), "title": kr.title},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(kr)
    return _serialize_kr(kr)


@router.delete("/key-results/{kr_id}", status_code=200)
async def delete_key_result(kr_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    kr = await _get_kr(db, auth.tenant_id, kr_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.key_result_deleted",
                   payload={"goal_id": str(kr.goal_id), "key_result_id": str(kr.id), "title": kr.title},
                   actor_id=auth.user_id)
    await db.delete(kr)
    await db.commit()
    return {"deleted": True}


# ---- lifecycle ----

@router.post("/{goal_id}/activate")
async def activate_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status != "draft":
        raise HTTPException(409, f"Goal is {g.status}; only draft goals can be activated")
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    if not krs:
        raise HTTPException(400, "Add at least one key result before activating")
    g.status = "active"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.activated",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    return _serialize_goal(g, krs)


@router.post("/{goal_id}/achieve")
async def achieve_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status != "active":
        raise HTTPException(409, f"Goal is {g.status}; only active goals can be achieved")
    g.status = "achieved"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.achieved",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return _serialize_goal(g, krs)


@router.post("/{goal_id}/miss")
async def miss_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status != "active":
        raise HTTPException(409, f"Goal is {g.status}; only active goals can be marked missed")
    g.status = "missed"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.missed",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return _serialize_goal(g, krs)


@router.post("/{goal_id}/cancel")
async def cancel_goal(goal_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    g = await _get_goal(db, auth.tenant_id, goal_id)
    if g.status in FINISHED_STATUSES:
        raise HTTPException(409, f"Goal is already {g.status}")
    g.status = "cancelled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="goal.cancelled",
                   payload={"goal_id": str(g.id), "title": g.title}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(g)
    krs = await _get_krs(db, auth.tenant_id, goal_id)
    return _serialize_goal(g, krs)
