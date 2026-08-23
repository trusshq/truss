"""Payroll routes (Major Phase 7): profiles, pay runs, payslips, lifecycle."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.hr import Employee
from truss_kernel.models.payroll import PayrollProfile, PayRun, Payslip

router = APIRouter(prefix="/api/payroll", tags=["payroll"])

VALID_FREQUENCIES = {"monthly", "biweekly", "weekly"}
# periods per year used to derive gross per run
PERIODS_PER_YEAR = {"monthly": 12, "biweekly": 26, "weekly": 52}
VALID_PROFILE_STATUS = {"active", "paused"}
VALID_RUN_STATUS = {"draft", "approved", "paid", "cancelled"}
VALID_SLIP_STATUS = {"pending", "paid"}


class ProfileIn(BaseModel):
    employee_id: str
    annual_salary_cents: int = Field(ge=1)
    frequency: str = "monthly"
    tax_rate_pct: int = Field(ge=0, le=100, default=0)
    currency: str = "USD"


class ProfilePatch(BaseModel):
    annual_salary_cents: int | None = Field(ge=1, default=None)
    frequency: str | None = None
    tax_rate_pct: int | None = Field(ge=0, le=100, default=None)
    currency: str | None = None
    status: str | None = None


class RunIn(BaseModel):
    period_start: str
    period_end: str


def _parse_uuid(raw: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"{label} must be a UUID")


def _serialize_profile(p: PayrollProfile) -> dict:
    return {
        "id": str(p.id),
        "employee_id": str(p.employee_id),
        "annual_salary_cents": p.annual_salary_cents,
        "frequency": p.frequency,
        "tax_rate_pct": p.tax_rate_pct,
        "currency": p.currency,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_run(r: PayRun) -> dict:
    return {
        "id": str(r.id),
        "period_start": r.period_start,
        "period_end": r.period_end,
        "status": r.status,
        "total_gross_cents": r.total_gross_cents,
        "total_tax_cents": r.total_tax_cents,
        "total_net_cents": r.total_net_cents,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_slip(s: Payslip) -> dict:
    return {
        "id": str(s.id),
        "pay_run_id": str(s.pay_run_id),
        "employee_id": str(s.employee_id),
        "gross_cents": s.gross_cents,
        "tax_cents": s.tax_cents,
        "net_cents": s.net_cents,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _get_profile(db: AsyncSession, tenant_id, pid: uuid.UUID) -> PayrollProfile:
    p = (await db.execute(select(PayrollProfile).where(
        PayrollProfile.tenant_id == tenant_id, PayrollProfile.id == pid))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Payroll profile not found")
    return p


async def _get_run(db: AsyncSession, tenant_id, rid: uuid.UUID) -> PayRun:
    r = (await db.execute(select(PayRun).where(
        PayRun.tenant_id == tenant_id, PayRun.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Pay run not found")
    return r


async def _get_slip(db: AsyncSession, tenant_id, sid: uuid.UUID) -> Payslip:
    s = (await db.execute(select(Payslip).where(
        Payslip.tenant_id == tenant_id, Payslip.id == sid))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Payslip not found")
    return s


# ---- profiles ----

@router.post("/profiles", status_code=201)
async def create_profile(body: ProfileIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.frequency not in VALID_FREQUENCIES:
        raise HTTPException(400, f"Invalid frequency. Valid: {', '.join(sorted(VALID_FREQUENCIES))}")
    eid = _parse_uuid(body.employee_id, "employee_id")
    emp = (await db.execute(select(Employee).where(
        Employee.tenant_id == auth.tenant_id, Employee.id == eid))).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.status != "active":
        raise HTTPException(409, f"Employee is {emp.status}; only active employees get payroll profiles")
    dup = (await db.execute(select(PayrollProfile).where(
        PayrollProfile.tenant_id == auth.tenant_id, PayrollProfile.employee_id == eid))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "Employee already has a payroll profile")
    p = PayrollProfile(
        tenant_id=auth.tenant_id, employee_id=eid,
        annual_salary_cents=body.annual_salary_cents, frequency=body.frequency,
        tax_rate_pct=body.tax_rate_pct, currency=body.currency, status="active",
    )
    db.add(p)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.profile_created",
                   payload={"profile_id": str(p.id), "employee_id": str(eid)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(p)
    return _serialize_profile(p)


@router.get("/profiles")
async def list_profiles(status: str | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(PayrollProfile).where(PayrollProfile.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_PROFILE_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_PROFILE_STATUS))}")
        stmt = stmt.where(PayrollProfile.status == status)
    rows = (await db.execute(stmt.order_by(PayrollProfile.created_at.desc()))).scalars().all()
    return {"items": [_serialize_profile(p) for p in rows], "total": len(rows)}


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    p = await _get_profile(db, auth.tenant_id, profile_id)
    return _serialize_profile(p)


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: uuid.UUID, body: ProfilePatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    p = await _get_profile(db, auth.tenant_id, profile_id)
    if body.annual_salary_cents is not None:
        p.annual_salary_cents = body.annual_salary_cents
    if body.frequency is not None:
        if body.frequency not in VALID_FREQUENCIES:
            raise HTTPException(400, f"Invalid frequency. Valid: {', '.join(sorted(VALID_FREQUENCIES))}")
        p.frequency = body.frequency
    if body.tax_rate_pct is not None:
        p.tax_rate_pct = body.tax_rate_pct
    if body.currency is not None:
        p.currency = body.currency
    if body.status is not None:
        if body.status not in VALID_PROFILE_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_PROFILE_STATUS))}")
        p.status = body.status
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.profile_updated",
                   payload={"profile_id": str(p.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(p)
    return _serialize_profile(p)


@router.delete("/profiles/{profile_id}", status_code=200)
async def delete_profile(profile_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = await _get_profile(db, auth.tenant_id, profile_id)
    refs = (await db.execute(select(Payslip).where(
        Payslip.tenant_id == auth.tenant_id, Payslip.employee_id == p.employee_id))).scalars().all()
    if refs:
        raise HTTPException(409, "Employee has payslips; cannot delete profile")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.profile_deleted",
                   payload={"profile_id": str(p.id)}, actor_id=auth.user_id)
    await db.delete(p)
    await db.commit()
    return {"deleted": True}


# ---- pay runs ----

@router.post("/runs", status_code=201)
async def create_run(body: RunIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if not body.period_start or not body.period_end:
        raise HTTPException(400, "period_start and period_end are required")
    if body.period_end < body.period_start:
        raise HTTPException(400, "period_end must be on or after period_start")
    run = PayRun(
        tenant_id=auth.tenant_id, period_start=body.period_start, period_end=body.period_end,
        status="draft", created_by=auth.user_id,
    )
    db.add(run)
    await db.flush()
    # generate one payslip per ACTIVE profile
    profiles = (await db.execute(select(PayrollProfile).where(
        PayrollProfile.tenant_id == auth.tenant_id, PayrollProfile.status == "active"))).scalars().all()
    total_gross = total_tax = total_net = 0
    for prof in profiles:
        periods = PERIODS_PER_YEAR[prof.frequency]
        gross = prof.annual_salary_cents // periods
        tax = gross * prof.tax_rate_pct // 100
        net = gross - tax
        total_gross += gross
        total_tax += tax
        total_net += net
        db.add(Payslip(
            tenant_id=auth.tenant_id, pay_run_id=run.id, employee_id=prof.employee_id,
            gross_cents=gross, tax_cents=tax, net_cents=net, status="pending",
        ))
    run.total_gross_cents = total_gross
    run.total_tax_cents = total_tax
    run.total_net_cents = total_net
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.run_created",
                   payload={"run_id": str(run.id), "period_start": run.period_start,
                            "period_end": run.period_end, "payslips": len(profiles)},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(run)
    return _serialize_run(run)


@router.get("/runs")
async def list_runs(status: str | None = None, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(PayRun).where(PayRun.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_RUN_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_RUN_STATUS))}")
        stmt = stmt.where(PayRun.status == status)
    rows = (await db.execute(stmt.order_by(PayRun.created_at.desc()))).scalars().all()
    return {"items": [_serialize_run(r) for r in rows], "total": len(rows)}


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    r = await _get_run(db, auth.tenant_id, run_id)
    return _serialize_run(r)


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await _get_run(db, auth.tenant_id, run_id)
    if r.status != "draft":
        raise HTTPException(409, f"Only draft runs can be approved; this run is {r.status}")
    r.status = "approved"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.run_approved",
                   payload={"run_id": str(r.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_run(r)


@router.post("/runs/{run_id}/pay")
async def pay_run(run_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await _get_run(db, auth.tenant_id, run_id)
    if r.status != "approved":
        raise HTTPException(409, f"Only approved runs can be paid; this run is {r.status}")
    slips = (await db.execute(select(Payslip).where(
        Payslip.tenant_id == auth.tenant_id, Payslip.pay_run_id == run_id))).scalars().all()
    for s in slips:
        s.status = "paid"
    r.status = "paid"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.run_paid",
                   payload={"run_id": str(r.id), "payslips": len(slips)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_run(r)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await _get_run(db, auth.tenant_id, run_id)
    if r.status not in ("draft", "approved"):
        raise HTTPException(409, f"Only draft/approved runs can be cancelled; this run is {r.status}")
    r.status = "cancelled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.run_cancelled",
                   payload={"run_id": str(r.id)}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(r)
    return _serialize_run(r)


@router.delete("/runs/{run_id}", status_code=200)
async def delete_run(run_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = await _get_run(db, auth.tenant_id, run_id)
    if r.status != "draft":
        raise HTTPException(409, f"Only draft runs can be deleted; this run is {r.status}")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="payroll.run_deleted",
                   payload={"run_id": str(r.id)}, actor_id=auth.user_id)
    await db.delete(r)
    await db.commit()
    return {"deleted": True}


# ---- payslips ----

@router.get("/payslips")
async def list_payslips(pay_run_id: str | None = None, employee_id: str | None = None,
                        status: str | None = None,
                        auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Payslip).where(Payslip.tenant_id == auth.tenant_id)
    if pay_run_id:
        stmt = stmt.where(Payslip.pay_run_id == _parse_uuid(pay_run_id, "pay_run_id"))
    if employee_id:
        stmt = stmt.where(Payslip.employee_id == _parse_uuid(employee_id, "employee_id"))
    if status:
        if status not in VALID_SLIP_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_SLIP_STATUS))}")
        stmt = stmt.where(Payslip.status == status)
    rows = (await db.execute(stmt.order_by(Payslip.created_at.desc()))).scalars().all()
    return {"items": [_serialize_slip(s) for s in rows], "total": len(rows)}


@router.get("/payslips/{slip_id}")
async def get_payslip(slip_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    s = await _get_slip(db, auth.tenant_id, slip_id)
    return _serialize_slip(s)
