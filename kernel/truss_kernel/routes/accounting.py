"""Accounting routes (Major Phase 8): accounts, journal entries, trial balance."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.accounting import Account, JournalEntry, JournalLine

router = APIRouter(prefix="/api/accounting", tags=["accounting"])

VALID_ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
VALID_ACCOUNT_STATUS = {"active", "archived"}
VALID_ENTRY_STATUS = {"draft", "posted"}
VALID_SOURCES = {"manual", "invoice", "expense", "payroll", "import"}


class AccountIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    account_type: str
    description: str = ""


class AccountPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class LineIn(BaseModel):
    account_id: str
    debit_cents: int = Field(ge=0, default=0)
    credit_cents: int = Field(ge=0, default=0)
    memo: str = ""


class EntryIn(BaseModel):
    entry_date: str
    memo: str = ""
    source: str = "manual"
    lines: list[LineIn]


class EntryPatch(BaseModel):
    entry_date: str | None = None
    memo: str | None = None


def _parse_uuid(raw: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"{label} must be a UUID")


def _serialize_account(a: Account) -> dict:
    return {
        "id": str(a.id),
        "code": a.code,
        "name": a.name,
        "account_type": a.account_type,
        "description": a.description,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_line(l: JournalLine) -> dict:
    return {
        "id": str(l.id),
        "entry_id": str(l.entry_id),
        "account_id": str(l.account_id),
        "debit_cents": l.debit_cents,
        "credit_cents": l.credit_cents,
        "memo": l.memo,
    }


def _serialize_entry(e: JournalEntry, lines: list[JournalLine] | None = None) -> dict:
    out = {
        "id": str(e.id),
        "entry_date": e.entry_date,
        "memo": e.memo,
        "status": e.status,
        "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
    if lines is not None:
        out["lines"] = [_serialize_line(l) for l in lines]
        out["total_debit_cents"] = sum(l.debit_cents for l in lines)
        out["total_credit_cents"] = sum(l.credit_cents for l in lines)
    return out


async def _get_account(db: AsyncSession, tenant_id, aid: uuid.UUID) -> Account:
    a = (await db.execute(select(Account).where(
        Account.tenant_id == tenant_id, Account.id == aid))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Account not found")
    return a


async def _get_entry(db: AsyncSession, tenant_id, eid: uuid.UUID) -> JournalEntry:
    e = (await db.execute(select(JournalEntry).where(
        JournalEntry.tenant_id == tenant_id, JournalEntry.id == eid))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Journal entry not found")
    return e


async def _get_entry_lines(db: AsyncSession, tenant_id, eid: uuid.UUID) -> list[JournalLine]:
    return list((await db.execute(select(JournalLine).where(
        JournalLine.tenant_id == tenant_id, JournalLine.entry_id == eid))).scalars().all())


# ---- accounts ----

@router.post("/accounts", status_code=201)
async def create_account(body: AccountIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.account_type not in VALID_ACCOUNT_TYPES:
        raise HTTPException(400, f"Invalid account_type. Valid: {', '.join(sorted(VALID_ACCOUNT_TYPES))}")
    dup = (await db.execute(select(Account).where(
        Account.tenant_id == auth.tenant_id, Account.code == body.code))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, f"Account code {body.code} already exists")
    a = Account(
        tenant_id=auth.tenant_id, code=body.code, name=body.name,
        account_type=body.account_type, description=body.description, status="active",
    )
    db.add(a)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.account_created",
                   payload={"account_id": str(a.id), "code": a.code}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize_account(a)


@router.get("/accounts")
async def list_accounts(account_type: str | None = None, status: str | None = None,
                        auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Account).where(Account.tenant_id == auth.tenant_id)
    if account_type:
        if account_type not in VALID_ACCOUNT_TYPES:
            raise HTTPException(400, f"Invalid account_type. Valid: {', '.join(sorted(VALID_ACCOUNT_TYPES))}")
        stmt = stmt.where(Account.account_type == account_type)
    if status:
        if status not in VALID_ACCOUNT_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_ACCOUNT_STATUS))}")
        stmt = stmt.where(Account.status == status)
    rows = (await db.execute(stmt.order_by(Account.code))).scalars().all()
    return {"items": [_serialize_account(a) for a in rows], "total": len(rows)}


@router.get("/accounts/{account_id}")
async def get_account(account_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    a = await _get_account(db, auth.tenant_id, account_id)
    return _serialize_account(a)


@router.patch("/accounts/{account_id}")
async def update_account(account_id: uuid.UUID, body: AccountPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    a = await _get_account(db, auth.tenant_id, account_id)
    if body.name is not None:
        a.name = body.name
    if body.description is not None:
        a.description = body.description
    if body.status is not None:
        if body.status not in VALID_ACCOUNT_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_ACCOUNT_STATUS))}")
        a.status = body.status
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.account_updated",
                   payload={"account_id": str(a.id), "code": a.code}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(a)
    return _serialize_account(a)


@router.delete("/accounts/{account_id}", status_code=200)
async def delete_account(account_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get_account(db, auth.tenant_id, account_id)
    refs = (await db.execute(select(JournalLine).where(
        JournalLine.tenant_id == auth.tenant_id, JournalLine.account_id == account_id))).scalars().all()
    if refs:
        raise HTTPException(409, "Account has journal lines; cannot delete")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.account_deleted",
                   payload={"account_id": str(a.id), "code": a.code}, actor_id=auth.user_id)
    await db.delete(a)
    await db.commit()
    return {"deleted": True}


# ---- journal entries ----

@router.post("/entries", status_code=201)
async def create_entry(body: EntryIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if not body.entry_date:
        raise HTTPException(400, "entry_date is required")
    if body.source not in VALID_SOURCES:
        raise HTTPException(400, f"Invalid source. Valid: {', '.join(sorted(VALID_SOURCES))}")
    if len(body.lines) < 2:
        raise HTTPException(400, "A journal entry needs at least 2 lines")
    total_debit = total_credit = 0
    resolved: list[tuple[Account, LineIn]] = []
    for li in body.lines:
        if li.debit_cents == 0 and li.credit_cents == 0:
            raise HTTPException(400, "Each line needs a non-zero debit or credit")
        if li.debit_cents > 0 and li.credit_cents > 0:
            raise HTTPException(400, "A line cannot have both debit and credit")
        acc = await _get_account(db, auth.tenant_id, _parse_uuid(li.account_id, "account_id"))
        if acc.status != "active":
            raise HTTPException(409, f"Account {acc.code} is {acc.status}; only active accounts take lines")
        total_debit += li.debit_cents
        total_credit += li.credit_cents
        resolved.append((acc, li))
    if total_debit != total_credit:
        raise HTTPException(400, f"Entry does not balance: debits {total_debit} != credits {total_credit}")
    e = JournalEntry(
        tenant_id=auth.tenant_id, entry_date=body.entry_date, memo=body.memo,
        status="draft", source=body.source, created_by=auth.user_id,
    )
    db.add(e)
    await db.flush()
    for acc, li in resolved:
        db.add(JournalLine(
            tenant_id=auth.tenant_id, entry_id=e.id, account_id=acc.id,
            debit_cents=li.debit_cents, credit_cents=li.credit_cents, memo=li.memo,
        ))
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.entry_created",
                   payload={"entry_id": str(e.id), "entry_date": e.entry_date, "lines": len(resolved)},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(e)
    lines = await _get_entry_lines(db, auth.tenant_id, e.id)
    return _serialize_entry(e, lines)


@router.get("/entries")
async def list_entries(status: str | None = None, source: str | None = None,
                       auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(JournalEntry).where(JournalEntry.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_ENTRY_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_ENTRY_STATUS))}")
        stmt = stmt.where(JournalEntry.status == status)
    if source:
        if source not in VALID_SOURCES:
            raise HTTPException(400, f"Invalid source. Valid: {', '.join(sorted(VALID_SOURCES))}")
        stmt = stmt.where(JournalEntry.source == source)
    rows = (await db.execute(stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc()))).scalars().all()
    return {"items": [_serialize_entry(e) for e in rows], "total": len(rows)}


@router.get("/entries/{entry_id}")
async def get_entry(entry_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    e = await _get_entry(db, auth.tenant_id, entry_id)
    lines = await _get_entry_lines(db, auth.tenant_id, entry_id)
    return _serialize_entry(e, lines)


@router.patch("/entries/{entry_id}")
async def update_entry(entry_id: uuid.UUID, body: EntryPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    e = await _get_entry(db, auth.tenant_id, entry_id)
    if e.status != "draft":
        raise HTTPException(409, f"Only draft entries can be edited; this entry is {e.status}")
    if body.entry_date is not None:
        e.entry_date = body.entry_date
    if body.memo is not None:
        e.memo = body.memo
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.entry_updated",
                   payload={"entry_id": str(e.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(e)
    return _serialize_entry(e)


@router.post("/entries/{entry_id}/post")
async def post_entry(entry_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    e = await _get_entry(db, auth.tenant_id, entry_id)
    if e.status != "draft":
        raise HTTPException(409, f"Only draft entries can be posted; this entry is {e.status}")
    lines = await _get_entry_lines(db, auth.tenant_id, entry_id)
    total_debit = sum(l.debit_cents for l in lines)
    total_credit = sum(l.credit_cents for l in lines)
    if total_debit != total_credit:
        raise HTTPException(400, f"Entry does not balance: debits {total_debit} != credits {total_credit}")
    e.status = "posted"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.entry_posted",
                   payload={"entry_id": str(e.id), "total_cents": total_debit}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(e)
    return _serialize_entry(e, lines)


@router.delete("/entries/{entry_id}", status_code=200)
async def delete_entry(entry_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    e = await _get_entry(db, auth.tenant_id, entry_id)
    if e.status != "draft":
        raise HTTPException(409, f"Only draft entries can be deleted; this entry is {e.status}")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="accounting.entry_deleted",
                   payload={"entry_id": str(e.id)}, actor_id=auth.user_id)
    await db.delete(e)
    await db.commit()
    return {"deleted": True}


# ---- trial balance ----

@router.get("/trial-balance")
async def trial_balance(as_of: str | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Per-account debit/credit totals from POSTED entries only.

    as_of (YYYY-MM-DD) limits to entries on or before that date.
    """
    entries_stmt = select(JournalEntry.id).where(
        JournalEntry.tenant_id == auth.tenant_id, JournalEntry.status == "posted")
    if as_of:
        entries_stmt = entries_stmt.where(JournalEntry.entry_date <= as_of)
    posted_ids = [r[0] for r in (await db.execute(entries_stmt)).all()]
    accounts = (await db.execute(select(Account).where(
        Account.tenant_id == auth.tenant_id).order_by(Account.code))).scalars().all()
    rows = []
    total_debit = total_credit = 0
    if posted_ids:
        lines = (await db.execute(select(JournalLine).where(
            JournalLine.tenant_id == auth.tenant_id,
            JournalLine.entry_id.in_(posted_ids)))).scalars().all()
        by_account: dict[uuid.UUID, list[JournalLine]] = {}
        for l in lines:
            by_account.setdefault(l.account_id, []).append(l)
        for a in accounts:
            acc_lines = by_account.get(a.id, [])
            if not acc_lines:
                continue
            d = sum(l.debit_cents for l in acc_lines)
            c = sum(l.credit_cents for l in acc_lines)
            total_debit += d
            total_credit += c
            rows.append({
                "account_id": str(a.id), "code": a.code, "name": a.name,
                "account_type": a.account_type,
                "debit_cents": d, "credit_cents": c, "net_cents": d - c,
            })
    return {
        "as_of": as_of,
        "rows": rows,
        "total_debit_cents": total_debit,
        "total_credit_cents": total_credit,
        "balanced": total_debit == total_credit,
    }
