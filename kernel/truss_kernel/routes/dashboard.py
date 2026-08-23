"""Dashboard routes (Phase W): one aggregated KPI snapshot across all modules.

GET /api/dashboard returns counts and actionable signals from every module
(records, agents, projects, expenses, inventory, HR, calendar, time, forms,
KB) so the home view can render a unified overview without N parallel calls.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_viewer
from truss_kernel.models.agent import Agent
from truss_kernel.models.calendar import CalendarEvent
from truss_kernel.models.expenses import Expense
from truss_kernel.models.forms import PublicForm
from truss_kernel.models.hr import Employee, LeaveRequest
from truss_kernel.models.inventory import Product
from truss_kernel.models.kb import KBArticle
from truss_kernel.models.metadata import ObjectDef, Record
from truss_kernel.models.projects import Project
from truss_kernel.models.time import TimeEntry

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def _count(db: AsyncSession, model, tenant_id, extra=None) -> int:
    stmt = select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    if extra is not None:
        stmt = stmt.where(extra)
    return (await db.execute(stmt)).scalar_one()


@router.get("")
async def dashboard(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    tid = auth.tenant_id
    now = datetime.now(timezone.utc)

    # core data
    objects_total = await _count(db, ObjectDef, tid)
    records_total = await _count(db, Record, tid, Record.deleted_at.is_(None))

    # AI
    agents_total = await _count(db, Agent, tid)
    agents_active = await _count(db, Agent, tid, Agent.status == "active")

    # projects
    projects_total = await _count(db, Project, tid)
    projects_active = await _count(db, Project, tid, Project.status == "active")

    # expenses
    expenses_pending = await _count(db, Expense, tid, Expense.status == "draft")
    expenses_submitted = await _count(db, Expense, tid, Expense.status == "submitted")
    expenses_approved_sum = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
            Expense.tenant_id == tid, Expense.status.in_(["approved", "reimbursed"]),
        )
    )).scalar_one()

    # inventory
    products_total = await _count(db, Product, tid)
    products_low = (await db.execute(
        select(func.count()).select_from(Product).where(
            Product.tenant_id == tid, Product.quantity <= Product.reorder_point,
        )
    )).scalar_one()

    # HR
    employees_total = await _count(db, Employee, tid)
    leave_pending = await _count(db, LeaveRequest, tid, LeaveRequest.status == "pending")

    # calendar: upcoming events in the next 7 days
    lo = now.isoformat()
    hi = (now + timedelta(days=7)).isoformat()
    upcoming_events = (await db.execute(
        select(func.count()).select_from(CalendarEvent).where(
            CalendarEvent.tenant_id == tid,
            CalendarEvent.starts_at >= lo,
            CalendarEvent.starts_at < hi,
        )
    )).scalar_one()

    # time logged this week (last 7 days)
    week_lo = (now - timedelta(days=7)).isoformat()
    time_minutes_week = (await db.execute(
        select(func.coalesce(func.sum(TimeEntry.duration_minutes), 0)).where(
            TimeEntry.tenant_id == tid,
            TimeEntry.started_at >= week_lo,
            TimeEntry.stopped_at.is_not(None),
        )
    )).scalar_one()

    # forms + KB
    forms_total = await _count(db, PublicForm, tid)
    kb_published = await _count(db, KBArticle, tid, KBArticle.status == "published")

    return {
        "objects_total": objects_total,
        "records_total": records_total,
        "agents_total": agents_total,
        "agents_active": agents_active,
        "projects_total": projects_total,
        "projects_active": projects_active,
        "expenses_pending": expenses_pending,
        "expenses_submitted": expenses_submitted,
        "expenses_approved_cents": int(expenses_approved_sum),
        "products_total": products_total,
        "products_low_stock": int(products_low),
        "employees_total": employees_total,
        "leave_pending": leave_pending,
        "upcoming_events_7d": int(upcoming_events),
        "time_minutes_7d": int(time_minutes_week),
        "forms_total": forms_total,
        "kb_published": kb_published,
    }
