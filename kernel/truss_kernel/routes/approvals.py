"""Approvals center routes (Phase X): one inbox for all pending approvals.

Aggregates the three approval queues into a single list so reviewers have one
place to act:
- Expenses with status 'submitted'
- Leave requests with status 'pending'
- Agent tasks with needs_review=True and status 'proposed'

Read-only here — the actual approve/reject actions live in each module's
routes (expenses, hr, agents). This endpoint just surfaces what needs attention.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.models.agent import AgentTask, TaskStatus
from truss_kernel.models.expenses import Expense
from truss_kernel.models.hr import LeaveRequest

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
async def approvals_inbox(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    tid = auth.tenant_id
    items: list[dict] = []

    # submitted expenses
    expenses = (await db.execute(select(Expense).where(
        Expense.tenant_id == tid, Expense.status == "submitted",
    ).order_by(Expense.created_at.desc()))).scalars().all()
    for e in expenses:
        items.append({
            "kind": "expense",
            "id": str(e.id),
            "title": e.title,
            "detail": f"{e.category} · {e.amount_cents / 100:.2f} {e.currency}",
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    # pending leave
    leaves = (await db.execute(select(LeaveRequest).where(
        LeaveRequest.tenant_id == tid, LeaveRequest.status == "pending",
    ).order_by(LeaveRequest.created_at.desc()))).scalars().all()
    for l in leaves:
        items.append({
            "kind": "leave",
            "id": str(l.id),
            "title": f"{l.leave_type.capitalize()} leave",
            "detail": f"{l.start_date} → {l.end_date}",
            "created_at": l.created_at.isoformat() if l.created_at else None,
        })

    # agent tasks awaiting review
    tasks = (await db.execute(select(AgentTask).where(
        AgentTask.tenant_id == tid,
        AgentTask.needs_review.is_(True),
        AgentTask.status == TaskStatus.proposed,
    ).order_by(AgentTask.created_at.desc()))).scalars().all()
    for t in tasks:
        items.append({
            "kind": "agent_task",
            "id": str(t.id),
            "title": t.title,
            "detail": "AI employee task awaiting approval",
            "created_at": t.created_at.isoformat() if t.created_at else None,
            # needed to call /api/agents/{agent_id}/tasks/{task_id}/approve|reject
            "agent_id": str(t.agent_id),
        })

    # newest first across all kinds
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {
        "items": items,
        "total": len(items),
        "by_kind": {
            "expense": len(expenses),
            "leave": len(leaves),
            "agent_task": len(tasks),
        },
    }
