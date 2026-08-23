"""Saved reports routes (Phase M): CRUD, run, runs history, schedule management."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.reports import ReportRun, SavedReport
from truss_kernel.services import reports as svc

router = APIRouter(prefix="/api/reports", tags=["reports"])

VALID_METRICS = {"count", "group_by", "sum", "avg", "min", "max", "summary", "time_series"}


class ReportIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    query: dict
    cron: str = ""


class ReportUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    query: dict | None = None
    cron: str | None = None


def _serialize(r: SavedReport) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": r.description,
        "query": r.query,
        "cron": r.cron,
        "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _validate_query(query: dict) -> None:
    if not query.get("object"):
        raise HTTPException(422, "query.object is required")
    metric = query.get("metric", "count")
    if metric not in VALID_METRICS:
        raise HTTPException(422, f"query.metric must be one of: {', '.join(sorted(VALID_METRICS))}")


def _validate_cron(cron: str) -> None:
    if cron and len(cron.split()) != 5:
        raise HTTPException(422, "cron must be a 5-field expression (minute hour dom month dow)")


@router.post("", status_code=201)
async def create_report(body: ReportIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    _validate_query(body.query)
    _validate_cron(body.cron)
    report = SavedReport(
        tenant_id=auth.tenant_id,
        name=body.name,
        description=body.description,
        query=body.query,
        cron=body.cron,
        created_by=auth.user_id,
    )
    report.next_run_at = svc.schedule_next(report, svc._now())
    db.add(report)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="report.created",
        payload={"report_id": str(report.id), "name": report.name},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(report)


@router.get("")
async def list_reports(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(SavedReport).where(SavedReport.tenant_id == auth.tenant_id)
        .order_by(SavedReport.created_at.desc())
    )).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def _get_report(db: AsyncSession, tenant_id, report_id: uuid.UUID) -> SavedReport:
    report = (await db.execute(select(SavedReport).where(
        SavedReport.id == report_id, SavedReport.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if report is None:
        raise HTTPException(404, "report not found")
    return report


@router.get("/{report_id}")
async def get_report(report_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_report(db, auth.tenant_id, report_id))


@router.patch("/{report_id}")
async def update_report(report_id: uuid.UUID, body: ReportUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    report = await _get_report(db, auth.tenant_id, report_id)
    if body.name is not None:
        report.name = body.name
    if body.description is not None:
        report.description = body.description
    if body.query is not None:
        _validate_query(body.query)
        report.query = body.query
    if body.cron is not None:
        _validate_cron(body.cron)
        report.cron = body.cron
        report.next_run_at = svc.schedule_next(report, svc._now())
    await db.commit()
    return _serialize(report)


@router.delete("/{report_id}")
async def delete_report(report_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    report = await _get_report(db, auth.tenant_id, report_id)
    await db.delete(report)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="report.deleted",
        payload={"report_id": str(report_id), "name": report.name},
        actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{report_id}/run", status_code=201)
async def run_report(report_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    """Run the report now and snapshot the result."""
    report = await _get_report(db, auth.tenant_id, report_id)
    run = await svc.run_report(db, auth.tenant_id, report, trigger="manual")
    await db.commit()
    return {
        "id": str(run.id),
        "status": run.status,
        "trigger": run.trigger,
        "result": run.result,
        "error": run.error or None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("/{report_id}/runs")
async def list_runs(report_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    await _get_report(db, auth.tenant_id, report_id)
    rows = (await db.execute(
        select(ReportRun).where(ReportRun.report_id == report_id)
        .order_by(ReportRun.created_at.desc()).limit(50)
    )).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "status": r.status,
                "trigger": r.trigger,
                "result": r.result,
                "error": r.error or None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }
