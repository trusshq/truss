"""HR routes (Phase V): employee directory + leave request approvals."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.hr import Employee, LeaveRequest

router = APIRouter(prefix="/api/hr", tags=["hr"])

EMPLOYEE_STATUSES = ("active", "on_leave", "terminated")
LEAVE_TYPES = ("vacation", "sick", "personal", "other")


class EmployeeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    title: str = ""
    department: str = "General"
    hire_date: str = ""
    status: str = "active"
    notes: str = ""


class EmployeeUpdateIn(BaseModel):
    name: str | None = None
    title: str | None = None
    department: str | None = None
    hire_date: str | None = None
    status: str | None = None
    notes: str | None = None


class LeaveIn(BaseModel):
    employee_id: str
    leave_type: str = "vacation"
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    reason: str = ""


class LeaveReviewIn(BaseModel):
    note: str = ""


def _serialize_employee(e: Employee) -> dict:
    return {
        "id": str(e.id),
        "name": e.name,
        "email": e.email,
        "title": e.title,
        "department": e.department,
        "hire_date": e.hire_date,
        "status": e.status,
        "user_id": str(e.user_id) if e.user_id else None,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _serialize_leave(l: LeaveRequest) -> dict:
    return {
        "id": str(l.id),
        "employee_id": str(l.employee_id),
        "leave_type": l.leave_type,
        "start_date": l.start_date,
        "end_date": l.end_date,
        "reason": l.reason,
        "status": l.status,
        "reviewed_by": str(l.reviewed_by) if l.reviewed_by else None,
        "review_note": l.review_note,
        "reviewed_at": l.reviewed_at,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


async def _get_employee(db: AsyncSession, tenant_id, employee_id: uuid.UUID) -> Employee:
    emp = (await db.execute(select(Employee).where(
        Employee.id == employee_id, Employee.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if emp is None:
        raise HTTPException(404, "employee not found")
    return emp


# ---------------- employees ----------------

@router.post("/employees", status_code=201)
async def create_employee(body: EmployeeIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if body.status not in EMPLOYEE_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(EMPLOYEE_STATUSES)}")
    existing = (await db.execute(select(Employee).where(
        Employee.tenant_id == auth.tenant_id, Employee.email == body.email.lower(),
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"employee with email '{body.email}' already exists")
    emp = Employee(
        tenant_id=auth.tenant_id,
        name=body.name,
        email=body.email.lower(),
        title=body.title,
        department=body.department,
        hire_date=body.hire_date,
        status=body.status,
        notes=body.notes,
    )
    db.add(emp)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="hr.employee_created",
        payload={"employee_id": str(emp.id), "name": emp.name, "email": emp.email},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_employee(emp)


@router.get("/employees")
async def list_employees(
    department: str | None = None,
    status: str | None = None,
    q: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Employee).where(Employee.tenant_id == auth.tenant_id)
    if department:
        stmt = stmt.where(Employee.department == department)
    if status:
        stmt = stmt.where(Employee.status == status)
    rows = (await db.execute(stmt.order_by(Employee.name))).scalars().all()
    if q:
        needle = q.lower()
        rows = [e for e in rows if needle in e.name.lower() or needle in e.email.lower() or needle in e.title.lower()]
    return {"items": [_serialize_employee(e) for e in rows], "total": len(rows)}


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize_employee(await _get_employee(db, auth.tenant_id, employee_id))


@router.patch("/employees/{employee_id}")
async def update_employee(employee_id: uuid.UUID, body: EmployeeUpdateIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    emp = await _get_employee(db, auth.tenant_id, employee_id)
    if body.status is not None and body.status not in EMPLOYEE_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(EMPLOYEE_STATUSES)}")
    if body.name is not None:
        emp.name = body.name
    if body.title is not None:
        emp.title = body.title
    if body.department is not None:
        emp.department = body.department
    if body.hire_date is not None:
        emp.hire_date = body.hire_date
    if body.status is not None:
        emp.status = body.status
    if body.notes is not None:
        emp.notes = body.notes
    await db.commit()
    return _serialize_employee(emp)


@router.delete("/employees/{employee_id}")
async def delete_employee(employee_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    emp = await _get_employee(db, auth.tenant_id, employee_id)
    await db.delete(emp)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="hr.employee_deleted",
        payload={"employee_id": str(employee_id), "name": emp.name},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


# ---------------- leave requests ----------------

@router.post("/leave", status_code=201)
async def create_leave(body: LeaveIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.leave_type not in LEAVE_TYPES:
        raise HTTPException(422, f"leave_type must be one of: {', '.join(LEAVE_TYPES)}")
    if body.end_date < body.start_date:
        raise HTTPException(422, "end_date must be on or after start_date")
    emp = await _get_employee(db, auth.tenant_id, uuid.UUID(body.employee_id))
    leave = LeaveRequest(
        tenant_id=auth.tenant_id,
        employee_id=emp.id,
        leave_type=body.leave_type,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason,
    )
    db.add(leave)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="hr.leave_requested",
        payload={"leave_id": str(leave.id), "employee_id": str(emp.id), "employee": emp.name,
                 "leave_type": leave.leave_type, "start_date": leave.start_date, "end_date": leave.end_date},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_leave(leave)


@router.get("/leave")
async def list_leave(
    status: str | None = None,
    employee_id: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LeaveRequest).where(LeaveRequest.tenant_id == auth.tenant_id)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if employee_id:
        stmt = stmt.where(LeaveRequest.employee_id == uuid.UUID(employee_id))
    rows = (await db.execute(stmt.order_by(LeaveRequest.created_at.desc()))).scalars().all()
    return {"items": [_serialize_leave(l) for l in rows], "total": len(rows)}


@router.post("/leave/{leave_id}/approve")
async def approve_leave(leave_id: uuid.UUID, body: LeaveReviewIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    leave = (await db.execute(select(LeaveRequest).where(
        LeaveRequest.id == leave_id, LeaveRequest.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if leave is None:
        raise HTTPException(404, "leave request not found")
    if leave.status != "pending":
        raise HTTPException(409, f"leave request is already {leave.status}")
    leave.status = "approved"
    leave.reviewed_by = auth.user_id
    leave.review_note = body.note
    leave.reviewed_at = datetime.now(timezone.utc).isoformat()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="hr.leave_approved",
        payload={"leave_id": str(leave.id), "employee_id": str(leave.employee_id)},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_leave(leave)


@router.post("/leave/{leave_id}/reject")
async def reject_leave(leave_id: uuid.UUID, body: LeaveReviewIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    leave = (await db.execute(select(LeaveRequest).where(
        LeaveRequest.id == leave_id, LeaveRequest.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if leave is None:
        raise HTTPException(404, "leave request not found")
    if leave.status != "pending":
        raise HTTPException(409, f"leave request is already {leave.status}")
    leave.status = "rejected"
    leave.reviewed_by = auth.user_id
    leave.review_note = body.note
    leave.reviewed_at = datetime.now(timezone.utc).isoformat()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="hr.leave_rejected",
        payload={"leave_id": str(leave.id), "employee_id": str(leave.employee_id)},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize_leave(leave)
