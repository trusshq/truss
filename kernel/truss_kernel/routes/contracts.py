"""Contracts routes (Phase AA): CRUD, lifecycle, and renewal detection."""
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.contracts import Contract

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

VALID_STATUS = {"draft", "active", "expired", "cancelled"}


class ContractIn(BaseModel):
    name: str
    counterparty: str = ""
    object: str = ""
    record_id: str | None = None
    notes: str = ""
    currency: str = "USD"
    value_cents: int = Field(default=0, ge=0)
    start_date: str = ""
    end_date: str = ""
    auto_renew: bool = False
    renewal_notice_days: int = Field(default=30, ge=0)


def _serialize(c: Contract) -> dict:
    return {
        "id": str(c.id),
        "number": c.number,
        "name": c.name,
        "counterparty": c.counterparty,
        "object": c.object,
        "record_id": str(c.record_id) if c.record_id else None,
        "notes": c.notes,
        "currency": c.currency,
        "value_cents": c.value_cents,
        "status": c.status,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "auto_renew": c.auto_renew,
        "renewal_notice_days": c.renewal_notice_days,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _days_until_end(c: Contract) -> int | None:
    if not c.end_date:
        return None
    try:
        end = datetime.strptime(c.end_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (end - date.today()).days


async def _next_number(db: AsyncSession, tenant_id) -> str:
    n = (await db.execute(
        select(func.count()).select_from(Contract).where(Contract.tenant_id == tenant_id)
    )).scalar_one()
    return f"CT-{n + 1:04d}"


async def _get_contract(db: AsyncSession, tenant_id, cid: uuid.UUID) -> Contract:
    c = (await db.execute(select(Contract).where(
        Contract.tenant_id == tenant_id, Contract.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contract not found")
    return c


def _validate_dates(start: str, end: str) -> None:
    for label, v in (("start_date", start), ("end_date", end)):
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, f"{label} must be YYYY-MM-DD")
    if start and end and end < start:
        raise HTTPException(400, "end_date must be on or after start_date")


@router.post("", status_code=201)
async def create_contract(body: ContractIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    _validate_dates(body.start_date, body.end_date)
    record_id = None
    if body.record_id:
        try:
            record_id = uuid.UUID(body.record_id)
        except ValueError:
            raise HTTPException(400, "record_id must be a UUID")
    c = Contract(
        tenant_id=auth.tenant_id,
        number=await _next_number(db, auth.tenant_id),
        name=body.name,
        counterparty=body.counterparty,
        object=body.object,
        record_id=record_id,
        notes=body.notes,
        currency=body.currency,
        value_cents=body.value_cents,
        status="draft",
        start_date=body.start_date,
        end_date=body.end_date,
        auto_renew=body.auto_renew,
        renewal_notice_days=body.renewal_notice_days,
        created_by=auth.user_id,
    )
    db.add(c)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.created",
                   payload={"contract_id": str(c.id), "number": c.number,
                            "name": c.name, "value_cents": c.value_cents},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.get("")
async def list_contracts(status: str | None = None, counterparty: str | None = None,
                         auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Contract).where(Contract.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Contract.status == status)
    if counterparty:
        stmt = stmt.where(Contract.counterparty.ilike(f"%{counterparty}%"))
    rows = (await db.execute(stmt.order_by(Contract.created_at.desc()))).scalars().all()
    return {"items": [_serialize(c) for c in rows], "total": len(rows)}


@router.get("/renewals")
async def list_renewals(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Active contracts inside their renewal notice window (or already past end)."""
    rows = (await db.execute(select(Contract).where(
        Contract.tenant_id == auth.tenant_id, Contract.status == "active",
    ))).scalars().all()
    out = []
    for c in rows:
        days = _days_until_end(c)
        if days is None:
            continue
        if days <= c.renewal_notice_days:
            item = _serialize(c)
            item["days_until_end"] = days
            item["needs_renewal"] = True
            out.append(item)
    out.sort(key=lambda x: x["days_until_end"])
    return {"items": out, "total": len(out)}


@router.get("/{contract_id}")
async def get_contract(contract_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    out = _serialize(c)
    out["days_until_end"] = _days_until_end(c)
    return out


@router.patch("/{contract_id}")
async def update_contract(contract_id: uuid.UUID, body: ContractIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    if c.status not in ("draft", "active"):
        raise HTTPException(409, f"Contract is {c.status}; only draft/active contracts can be edited")
    _validate_dates(body.start_date, body.end_date)
    c.name = body.name
    c.counterparty = body.counterparty
    c.object = body.object
    c.record_id = uuid.UUID(body.record_id) if body.record_id else None
    c.notes = body.notes
    c.currency = body.currency
    c.value_cents = body.value_cents
    c.start_date = body.start_date
    c.end_date = body.end_date
    c.auto_renew = body.auto_renew
    c.renewal_notice_days = body.renewal_notice_days
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.updated",
                   payload={"contract_id": str(c.id), "number": c.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.delete("/{contract_id}", status_code=200)
async def delete_contract(contract_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.deleted",
                   payload={"contract_id": str(c.id), "number": c.number}, actor_id=auth.user_id)
    await db.delete(c)
    await db.commit()
    return {"deleted": True}


@router.post("/{contract_id}/activate")
async def activate_contract(contract_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    if c.status != "draft":
        raise HTTPException(409, f"Contract is {c.status}; only draft contracts can be activated")
    c.status = "active"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.activated",
                   payload={"contract_id": str(c.id), "number": c.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{contract_id}/cancel")
async def cancel_contract(contract_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    if c.status not in ("draft", "active"):
        raise HTTPException(409, f"Contract is {c.status}; only draft/active contracts can be cancelled")
    c.status = "cancelled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.cancelled",
                   payload={"contract_id": str(c.id), "number": c.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{contract_id}/expire")
async def expire_contract(contract_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_contract(db, auth.tenant_id, contract_id)
    if c.status != "active":
        raise HTTPException(409, f"Contract is {c.status}; only active contracts can be expired")
    c.status = "expired"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="contract.expired",
                   payload={"contract_id": str(c.id), "number": c.number}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)
