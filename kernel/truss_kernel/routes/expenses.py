"""Expenses routes (Phase S): CRUD + submit/approve/reject/reimburse workflow.

Lifecycle: draft -> submitted -> approved | rejected -> reimbursed.
- Anyone with member role can create their own draft expenses and submit them.
- Admin+ reviews (approve/reject) and marks reimbursed.
- Reviewers can attach a note; all transitions emit events.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.expenses import Expense

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

VALID_CATEGORIES = {"General", "Travel", "Meals", "Software", "Equipment", "Office", "Marketing", "Other"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExpenseIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "General"
    amount_cents: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    occurred_on: str = ""
    notes: str = ""
    receipt_file_id: str | None = None
    project_id: str | None = None


class ExpenseUpdateIn(BaseModel):
    title: str | None = None
    category: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    occurred_on: str | None = None
    notes: str | None = None
    receipt_file_id: str | None = None


class ReviewIn(BaseModel):
    note: str = ""


def _validate_category(category: str) -> None:
    if category not in VALID_CATEGORIES:
        raise HTTPException(422, f"category must be one of: {', '.join(sorted(VALID_CATEGORIES))}")


def _validate_file_id(file_id: str | None) -> uuid.UUID | None:
    if not file_id:
        return None
    try:
        return uuid.UUID(file_id)
    except ValueError as e:
        raise HTTPException(422, "receipt_file_id must be a UUID") from e


def _serialize(e: Expense) -> dict:
    return {
        "id": str(e.id),
        "title": e.title,
        "category": e.category,
        "amount_cents": e.amount_cents,
        "currency": e.currency,
        "occurred_on": e.occurred_on,
        "notes": e.notes,
        "status": e.status,
        "submitted_by": str(e.submitted_by) if e.submitted_by else None,
        "receipt_file_id": str(e.receipt_file_id) if e.receipt_file_id else None,
        "project_id": str(e.project_id) if e.project_id else None,
        "reviewed_by": str(e.reviewed_by) if e.reviewed_by else None,
        "review_note": e.review_note,
        "reviewed_at": e.reviewed_at or None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.post("", status_code=201)
async def create_expense(body: ExpenseIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    _validate_category(body.category)
    expense = Expense(
        tenant_id=auth.tenant_id,
        title=body.title,
        category=body.category,
        amount_cents=body.amount_cents,
        currency=body.currency.upper(),
        occurred_on=body.occurred_on,
        notes=body.notes,
        submitted_by=auth.user_id,
        receipt_file_id=_validate_file_id(body.receipt_file_id),
        project_id=_validate_file_id(body.project_id),
    )
    db.add(expense)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="expense.created",
        payload={"expense_id": str(expense.id), "title": expense.title, "amount_cents": expense.amount_cents},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(expense)


@router.get("")
async def list_expenses(
    status: str | None = None,
    category: str | None = None,
    mine: bool = False,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Expense).where(Expense.tenant_id == auth.tenant_id)
    if status:
        stmt = stmt.where(Expense.status == status)
    if category:
        stmt = stmt.where(Expense.category == category)
    if mine:
        stmt = stmt.where(Expense.submitted_by == auth.user_id)
    rows = (await db.execute(stmt.order_by(Expense.created_at.desc()))).scalars().all()
    return {"items": [_serialize(e) for e in rows], "total": len(rows)}


@router.get("/summary")
async def expense_summary(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Totals by status and by category (all statuses)."""
    rows = (await db.execute(select(Expense).where(Expense.tenant_id == auth.tenant_id))).scalars().all()
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    total = 0
    for e in rows:
        total += e.amount_cents
        by_status[e.status] = by_status.get(e.status, 0) + e.amount_cents
        by_category[e.category] = by_category.get(e.category, 0) + e.amount_cents
    return {
        "total_cents": total,
        "count": len(rows),
        "by_status": [{"label": k, "cents": v} for k, v in sorted(by_status.items(), key=lambda x: -x[1])],
        "by_category": [{"label": k, "cents": v} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
    }


async def _get_expense(db: AsyncSession, tenant_id, expense_id: uuid.UUID) -> Expense:
    expense = (await db.execute(select(Expense).where(
        Expense.id == expense_id, Expense.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if expense is None:
        raise HTTPException(404, "expense not found")
    return expense


@router.get("/{expense_id}")
async def get_expense(expense_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_expense(db, auth.tenant_id, expense_id))


@router.patch("/{expense_id}")
async def update_expense(expense_id: uuid.UUID, body: ExpenseUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    expense = await _get_expense(db, auth.tenant_id, expense_id)
    if expense.status not in ("draft", "rejected"):
        raise HTTPException(409, f"cannot edit an expense in '{expense.status}' status")
    if body.title is not None:
        expense.title = body.title
    if body.category is not None:
        _validate_category(body.category)
        expense.category = body.category
    if body.amount_cents is not None:
        expense.amount_cents = body.amount_cents
    if body.currency is not None:
        expense.currency = body.currency.upper()
    if body.occurred_on is not None:
        expense.occurred_on = body.occurred_on
    if body.notes is not None:
        expense.notes = body.notes
    if body.receipt_file_id is not None:
        expense.receipt_file_id = _validate_file_id(body.receipt_file_id)
    await db.commit()
    return _serialize(expense)


@router.delete("/{expense_id}")
async def delete_expense(expense_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    expense = await _get_expense(db, auth.tenant_id, expense_id)
    if expense.status not in ("draft", "rejected"):
        raise HTTPException(409, f"cannot delete an expense in '{expense.status}' status")
    await db.delete(expense)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="expense.deleted",
        payload={"expense_id": str(expense_id), "title": expense.title}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


# ---------------- workflow transitions ----------------

@router.post("/{expense_id}/submit")
async def submit_expense(expense_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    expense = await _get_expense(db, auth.tenant_id, expense_id)
    if expense.status not in ("draft", "rejected"):
        raise HTTPException(409, f"cannot submit an expense in '{expense.status}' status")
    if expense.amount_cents <= 0:
        raise HTTPException(422, "cannot submit a zero-amount expense")
    expense.status = "submitted"
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="expense.submitted",
        payload={"expense_id": str(expense.id), "title": expense.title, "amount_cents": expense.amount_cents},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(expense)


async def _review(db, auth, expense_id: uuid.UUID, note: str, decision: str) -> dict:
    expense = await _get_expense(db, auth.tenant_id, expense_id)
    if expense.status != "submitted":
        raise HTTPException(409, f"cannot review an expense in '{expense.status}' status")
    expense.status = decision
    expense.reviewed_by = auth.user_id
    expense.review_note = note
    expense.reviewed_at = _now_iso()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type=f"expense.{decision}",
        payload={"expense_id": str(expense.id), "title": expense.title, "note": note},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(expense)


@router.post("/{expense_id}/approve")
async def approve_expense(expense_id: uuid.UUID, body: ReviewIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _review(db, auth, expense_id, body.note, "approved")


@router.post("/{expense_id}/reject")
async def reject_expense(expense_id: uuid.UUID, body: ReviewIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _review(db, auth, expense_id, body.note, "rejected")


@router.post("/{expense_id}/reimburse")
async def reimburse_expense(expense_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    expense = await _get_expense(db, auth.tenant_id, expense_id)
    if expense.status != "approved":
        raise HTTPException(409, f"cannot reimburse an expense in '{expense.status}' status")
    expense.status = "reimbursed"
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="expense.reimbursed",
        payload={"expense_id": str(expense.id), "title": expense.title, "amount_cents": expense.amount_cents},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(expense)
