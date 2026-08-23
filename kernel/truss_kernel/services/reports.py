"""Saved reports service (Phase M): run, schedule, and snapshot analytics queries."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.agents.orchestration import cron_matches, next_cron_run
from truss_kernel.db import SessionLocal
from truss_kernel.models.reports import ReportRun, SavedReport
from truss_kernel.services import analytics

logger = logging.getLogger("truss.reports")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def run_report(
    db: AsyncSession, tenant_id, report: SavedReport, trigger: str = "manual"
) -> ReportRun:
    """Execute a saved report's query and snapshot the result into a ReportRun."""
    try:
        result = await analytics.run_query(db, tenant_id, dict(report.query))
        run = ReportRun(
            report_id=report.id, tenant_id=tenant_id,
            status="ok", trigger=trigger, result=result,
        )
    except Exception as e:  # noqa: BLE001 - snapshot the error, don't crash the caller
        run = ReportRun(
            report_id=report.id, tenant_id=tenant_id,
            status="error", trigger=trigger, result={}, error=str(e)[:500],
        )
    db.add(run)
    await db.flush()
    return run


def schedule_next(report: SavedReport, after: datetime) -> datetime | None:
    """Next run time for a cron-scheduled report (None if unscheduled)."""
    if not report.cron:
        return None
    return next_cron_run(report.cron, after)


async def tick_due_reports(now: datetime | None = None) -> int:
    """Fire every due cron-scheduled report once. Returns the number fired.

    Mirrors the orchestration scheduler: advance next_run_at BEFORE executing
    so a slow run can't double-fire.
    """
    now = now or _now()
    fired = 0
    async with SessionLocal() as db:
        due = (await db.execute(select(SavedReport).where(
            SavedReport.cron != "",
            SavedReport.next_run_at.is_not(None),
            SavedReport.next_run_at <= now,
        ))).scalars().all()

        for report in due:
            report.next_run_at = schedule_next(report, now)
            try:
                await run_report(db, report.tenant_id, report, trigger="schedule")
                fired += 1
                logger.info("scheduled report '%s' ran", report.name)
            except Exception:  # noqa: BLE001
                logger.exception("scheduled report '%s' failed", report.name)
            await db.commit()
    return fired
