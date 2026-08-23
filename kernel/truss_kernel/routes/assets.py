"""Assets routes (Phase AD): CRUD, lifecycle, assignment, and history."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.assets import Asset, AssetHistory

router = APIRouter(prefix="/api/assets", tags=["assets"])

VALID_STATUS = {"available", "assigned", "maintenance", "retired"}


class AssetIn(BaseModel):
    name: str
    category: str = "General"
    description: str = ""
    cost_cents: int = Field(default=0, ge=0)
    currency: str = "USD"
    purchase_date: str = ""
    location: str = ""


class AssetPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    cost_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    purchase_date: str | None = None
    location: str | None = None


def _serialize(a: Asset) -> dict:
    return {
        "id": str(a.id),
        "tag": a.tag,
        "name": a.name,
        "category": a.category,
        "description": a.description,
        "cost_cents": a.cost_cents,
        "currency": a.currency,
        "purchase_date": a.purchase_date,
        "status": a.status,
        "assignee_id": str(a.assignee_id) if a.assignee_id else None,
        "location": a.location,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_history(h: AssetHistory) -> dict:
    return {
        "id": str(h.id),
        "asset_id": str(h.asset_id),
        "action": h.action,
        "detail": h.detail,
        "actor_id": str(h.actor_id) if h.actor_id else None,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


async def _next_tag(db: AsyncSession, tenant_id) -> str:
    n = (await db.execute(
        select(func.count()).select_from(Asset).where(Asset.tenant_id == tenant_id)
    )).scalar_one()
    return f"AST-{n + 1:04d}"


async def _get_asset(db: AsyncSession, tenant_id, aid: uuid.UUID) -> Asset:
    a = (await db.execute(select(Asset).where(
        Asset.tenant_id == tenant_id, Asset.id == aid))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Asset not found")
    return a


async def _log(db, tenant_id, asset: Asset, action: str, detail: str, actor_id):
    db.add(AssetHistory(
        tenant_id=tenant_id, asset_id=asset.id, action=action,
        detail=detail, actor_id=actor_id,
    ))


@router.post("", status_code=201)
async def create_asset(body: AssetIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = Asset(
        tenant_id=auth.tenant_id,
        tag=await _next_tag(db, auth.tenant_id),
        name=body.name,
        category=body.category,
        description=body.description,
        cost_cents=body.cost_cents,
        currency=body.currency,
        purchase_date=body.purchase_date,
        status="available",
        location=body.location,
    )
    db.add(a)
    await db.flush()
    await _log(db, auth.tenant_id, a, "created", f"Asset {a.tag} created", auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.created",
                   payload={"asset_id": str(a.id), "tag": a.tag, "name": a.name},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.get("")
async def list_assets(status: str | None = None, category: str | None = None,
                      assignee_id: str | None = None, unassigned: bool = False,
                      auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Asset).where(Asset.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Asset.status == status)
    if category:
        stmt = stmt.where(Asset.category == category)
    if assignee_id:
        try:
            stmt = stmt.where(Asset.assignee_id == uuid.UUID(assignee_id))
        except ValueError:
            raise HTTPException(400, "assignee_id must be a UUID")
    if unassigned:
        stmt = stmt.where(Asset.assignee_id.is_(None))
    rows = (await db.execute(stmt.order_by(Asset.created_at.desc()))).scalars().all()
    return {"items": [_serialize(a) for a in rows], "total": len(rows)}


@router.get("/{asset_id}")
async def get_asset(asset_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_asset(db, auth.tenant_id, asset_id))


@router.patch("/{asset_id}")
async def update_asset(asset_id: uuid.UUID, body: AssetPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status == "retired":
        raise HTTPException(409, "Asset is retired; restore it before editing")
    if body.name is not None:
        a.name = body.name
    if body.category is not None:
        a.category = body.category
    if body.description is not None:
        a.description = body.description
    if body.cost_cents is not None:
        a.cost_cents = body.cost_cents
    if body.currency is not None:
        a.currency = body.currency
    if body.purchase_date is not None:
        a.purchase_date = body.purchase_date
    if body.location is not None:
        a.location = body.location
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.updated",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.delete("/{asset_id}", status_code=200)
async def delete_asset(asset_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.deleted",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.delete(a)
    await db.commit()
    return {"deleted": True}


@router.post("/{asset_id}/assign")
async def assign_asset(asset_id: uuid.UUID, body: dict, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status not in ("available", "maintenance"):
        raise HTTPException(409, f"Asset is {a.status}; only available/maintenance assets can be assigned")
    raw = body.get("assignee_id")
    if not raw:
        raise HTTPException(400, "assignee_id is required")
    try:
        uid = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(400, "assignee_id must be a UUID")
    a.assignee_id = uid
    a.status = "assigned"
    await _log(db, auth.tenant_id, a, "assigned", f"Assigned to {raw}", auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.assigned",
                   payload={"asset_id": str(a.id), "tag": a.tag, "assignee_id": raw},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.post("/{asset_id}/return")
async def return_asset(asset_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status != "assigned":
        raise HTTPException(409, f"Asset is {a.status}; only assigned assets can be returned")
    prev = str(a.assignee_id) if a.assignee_id else None
    a.assignee_id = None
    a.status = "available"
    await _log(db, auth.tenant_id, a, "returned", f"Returned by {prev}", auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.returned",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.post("/{asset_id}/maintenance")
async def maintenance_asset(asset_id: uuid.UUID, body: dict, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status not in ("available", "assigned"):
        raise HTTPException(409, f"Asset is {a.status}; only available/assigned assets can go to maintenance")
    if a.status == "assigned":
        a.assignee_id = None
    a.status = "maintenance"
    await _log(db, auth.tenant_id, a, "maintenance", body.get("reason", ""), auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.maintenance",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.post("/{asset_id}/retire")
async def retire_asset(asset_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status == "retired":
        raise HTTPException(409, "Asset is already retired")
    a.assignee_id = None
    a.status = "retired"
    await _log(db, auth.tenant_id, a, "retired", "Asset retired", auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.retired",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.post("/{asset_id}/restore")
async def restore_asset(asset_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_asset(db, auth.tenant_id, asset_id)
    if a.status not in ("retired", "maintenance"):
        raise HTTPException(409, f"Asset is {a.status}; only retired/maintenance assets can be restored")
    a.status = "available"
    await _log(db, auth.tenant_id, a, "restored", "Asset restored to available", auth.user_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="asset.restored",
                   payload={"asset_id": str(a.id), "tag": a.tag}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize(a)


@router.get("/{asset_id}/history")
async def asset_history(asset_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_asset(db, auth.tenant_id, asset_id)
    rows = (await db.execute(select(AssetHistory).where(
        AssetHistory.tenant_id == auth.tenant_id, AssetHistory.asset_id == asset_id,
    ).order_by(AssetHistory.created_at.asc()))).scalars().all()
    return {"items": [_serialize_history(h) for h in rows], "total": len(rows)}
