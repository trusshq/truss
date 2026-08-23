"""Projects routes (Phase T): CRUD, milestones, and budget-vs-actual rollups."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.expenses import Expense
from truss_kernel.models.projects import Milestone, Project
from truss_kernel.models.time import TimeEntry

router = APIRouter(prefix="/api/projects", tags=["projects"])

VALID_STATUSES = {"planning", "active", "on_hold", "completed", "cancelled"}
MILESTONE_STATUSES = {"pending", "done"}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "project"


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    description: str = ""
    status: str = "planning"
    budget_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: str = ""
    end_date: str = ""


class ProjectUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    budget_cents: int | None = Field(default=None, ge=0)
    currency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    owner_id: str | None = None


class MilestoneIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: str = ""
    notes: str = ""


class MilestoneUpdateIn(BaseModel):
    title: str | None = None
    due_date: str | None = None
    status: str | None = None
    notes: str | None = None


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")


def _serialize_project(p: Project) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "status": p.status,
        "budget_cents": p.budget_cents,
        "currency": p.currency,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "owner_id": str(p.owner_id) if p.owner_id else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_milestone(m: Milestone) -> dict:
    return {
        "id": str(m.id),
        "project_id": str(m.project_id),
        "title": m.title,
        "due_date": m.due_date,
        "status": m.status,
        "notes": m.notes,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _get_project(db: AsyncSession, tenant_id, project_id: uuid.UUID) -> Project:
    project = (await db.execute(select(Project).where(
        Project.id == project_id, Project.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.post("", status_code=201)
async def create_project(body: ProjectIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    _validate_status(body.status)
    slug = body.slug or _slugify(body.name)
    existing = (await db.execute(select(Project).where(
        Project.tenant_id == auth.tenant_id, Project.slug == slug,
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"project slug '{slug}' already exists")
    project = Project(
        tenant_id=auth.tenant_id,
        name=body.name,
        slug=slug,
        description=body.description,
        status=body.status,
        budget_cents=body.budget_cents,
        currency=body.currency.upper(),
        start_date=body.start_date,
        end_date=body.end_date,
        owner_id=auth.user_id,
    )
    db.add(project)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="project.created",
        payload={"project_id": str(project.id), "name": project.name}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_project(project)


@router.get("")
async def list_projects(
    status: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Project).where(Project.tenant_id == auth.tenant_id)
    if status:
        stmt = stmt.where(Project.status == status)
    rows = (await db.execute(stmt.order_by(Project.created_at.desc()))).scalars().all()
    return {"items": [_serialize_project(p) for p in rows], "total": len(rows)}


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_project(await _get_project(db, auth.tenant_id, project_id))


@router.get("/{project_id}/summary")
async def project_summary(project_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Roll up time + expenses against the project budget, plus milestone progress."""
    project = await _get_project(db, auth.tenant_id, project_id)

    time_rows = (await db.execute(select(TimeEntry).where(
        TimeEntry.tenant_id == auth.tenant_id, TimeEntry.project_id == project_id,
        TimeEntry.stopped_at.is_not(None),
    ))).scalars().all()
    time_minutes = sum((e.duration_minutes or 0) for e in time_rows)

    expense_rows = (await db.execute(select(Expense).where(
        Expense.tenant_id == auth.tenant_id, Expense.project_id == project_id,
    ))).scalars().all()
    expense_cents = sum(e.amount_cents for e in expense_rows)

    milestones = (await db.execute(select(Milestone).where(
        Milestone.tenant_id == auth.tenant_id, Milestone.project_id == project_id,
    ).order_by(Milestone.due_date))).scalars().all()
    done = sum(1 for m in milestones if m.status == "done")

    budget = project.budget_cents
    return {
        "project_id": str(project.id),
        "status": project.status,
        "budget_cents": budget,
        "spent_cents": expense_cents,
        "remaining_cents": max(0, budget - expense_cents),
        "budget_used_pct": round(expense_cents / budget * 100, 1) if budget else None,
        "time_minutes": time_minutes,
        "time_entries": len(time_rows),
        "expenses": len(expense_rows),
        "milestones_total": len(milestones),
        "milestones_done": done,
        "milestones": [_serialize_milestone(m) for m in milestones],
    }


@router.patch("/{project_id}")
async def update_project(project_id: uuid.UUID, body: ProjectUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    project = await _get_project(db, auth.tenant_id, project_id)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.status is not None:
        _validate_status(body.status)
        project.status = body.status
    if body.budget_cents is not None:
        project.budget_cents = body.budget_cents
    if body.currency is not None:
        project.currency = body.currency.upper()
    if body.start_date is not None:
        project.start_date = body.start_date
    if body.end_date is not None:
        project.end_date = body.end_date
    if body.owner_id is not None:
        try:
            project.owner_id = uuid.UUID(body.owner_id) if body.owner_id else None
        except ValueError as e:
            raise HTTPException(422, "owner_id must be a UUID") from e
    await db.commit()
    return _serialize_project(project)


@router.delete("/{project_id}")
async def delete_project(project_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    project = await _get_project(db, auth.tenant_id, project_id)
    await db.delete(project)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="project.deleted",
        payload={"project_id": str(project_id), "name": project.name}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


# ---------------- milestones ----------------

@router.post("/{project_id}/milestones", status_code=201)
async def create_milestone(project_id: uuid.UUID, body: MilestoneIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    await _get_project(db, auth.tenant_id, project_id)
    milestone = Milestone(
        tenant_id=auth.tenant_id,
        project_id=project_id,
        title=body.title,
        due_date=body.due_date,
        notes=body.notes,
    )
    db.add(milestone)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="project.milestone_created",
        payload={"project_id": str(project_id), "milestone_id": str(milestone.id), "title": milestone.title},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_milestone(milestone)


@router.get("/{project_id}/milestones")
async def list_milestones(project_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_project(db, auth.tenant_id, project_id)
    rows = (await db.execute(select(Milestone).where(
        Milestone.tenant_id == auth.tenant_id, Milestone.project_id == project_id,
    ).order_by(Milestone.due_date))).scalars().all()
    return {"items": [_serialize_milestone(m) for m in rows], "total": len(rows)}


async def _get_milestone(db: AsyncSession, tenant_id, project_id, milestone_id: uuid.UUID) -> Milestone:
    milestone = (await db.execute(select(Milestone).where(
        Milestone.id == milestone_id, Milestone.project_id == project_id, Milestone.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if milestone is None:
        raise HTTPException(404, "milestone not found")
    return milestone


@router.patch("/{project_id}/milestones/{milestone_id}")
async def update_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, body: MilestoneUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    milestone = await _get_milestone(db, auth.tenant_id, project_id, milestone_id)
    if body.title is not None:
        milestone.title = body.title
    if body.due_date is not None:
        milestone.due_date = body.due_date
    if body.status is not None:
        if body.status not in MILESTONE_STATUSES:
            raise HTTPException(422, f"status must be one of: {', '.join(sorted(MILESTONE_STATUSES))}")
        milestone.status = body.status
    if body.notes is not None:
        milestone.notes = body.notes
    await db.commit()
    return _serialize_milestone(milestone)


@router.delete("/{project_id}/milestones/{milestone_id}")
async def delete_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    milestone = await _get_milestone(db, auth.tenant_id, project_id, milestone_id)
    await db.delete(milestone)
    await db.commit()
    return {"ok": True}
