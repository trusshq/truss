"""Truss Kernel — FastAPI application entrypoint."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from truss_kernel.agents import orchestration as orchestration_engine
from truss_kernel.automations.engine import engine as automation_engine
from truss_kernel.config import settings
from truss_kernel.connectors import webhook as webhook_adapter
from truss_kernel.db import engine
from truss_kernel.events import bus
from truss_kernel.migrate import run_migrations
from truss_kernel.models.base import Base
from truss_kernel.plugins.registry import registry
from truss_kernel.routes import agents, ai, apikeys, audit, auth, automations, billing, calendar, connectors, dashboard, dev, events, expenses, files, forms, hr, insights, inventory, kb, marketplace, objects, orchestration, org, plugins, projects, records, reports, search, time, workspace
from truss_kernel.services import reports as reports_svc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("truss")


async def _report_scheduler_loop() -> None:
    """Fire due cron-scheduled reports on the same cadence as the orchestration tick."""
    while True:
        try:
            await reports_svc.tick_due_reports()
        except Exception:  # noqa: BLE001 - the loop must survive any single tick failure
            logger.exception("report scheduler tick failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # dev convenience: create tables on boot (Alembic takes over later)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)
    found = registry.discover()
    bus.subscribe("*", automation_engine.handle)
    bus.subscribe("*", webhook_adapter.on_event)
    bus.subscribe("*", orchestration_engine.handle_trigger_event)
    await orchestration_engine.scheduler.start()
    report_scheduler = asyncio.create_task(_report_scheduler_loop())
    logger.info("Truss kernel up. %d plugin(s) discovered: %s",
                len(found), ", ".join(sorted(found)))
    yield
    report_scheduler.cancel()
    try:
        await report_scheduler
    except asyncio.CancelledError:
        pass
    await orchestration_engine.scheduler.stop()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Open-source plugin-first business OS kernel. "
                "Metadata-driven objects, declarative plugins, BYOK AI, event seam.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(objects.router)
app.include_router(records.router)
app.include_router(plugins.router)
app.include_router(events.router)
app.include_router(ai.router)
app.include_router(apikeys.router)
app.include_router(org.router)
app.include_router(orchestration.router)
app.include_router(insights.router)
app.include_router(dev.router)
app.include_router(agents.router)
app.include_router(automations.router)
app.include_router(connectors.router)
app.include_router(marketplace.router)
app.include_router(workspace.router)
app.include_router(search.router)
app.include_router(audit.router)
app.include_router(billing.router)
app.include_router(reports.router)
app.include_router(forms.router)
app.include_router(forms.public_router)
app.include_router(files.router)
app.include_router(calendar.router)
app.include_router(kb.router)
app.include_router(kb.public_router)
app.include_router(time.router)
app.include_router(expenses.router)
app.include_router(projects.router)
app.include_router(inventory.router)
app.include_router(hr.router)
app.include_router(dashboard.router)


@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}
