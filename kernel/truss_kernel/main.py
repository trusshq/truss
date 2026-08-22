"""Truss Kernel — FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from truss_kernel.automations.engine import engine as automation_engine
from truss_kernel.config import settings
from truss_kernel.connectors import webhook as webhook_adapter
from truss_kernel.db import engine
from truss_kernel.events import bus
from truss_kernel.migrate import run_migrations
from truss_kernel.models.base import Base
from truss_kernel.plugins.registry import registry
from truss_kernel.routes import agents, ai, auth, automations, connectors, events, marketplace, objects, plugins, records, workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("truss")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # dev convenience: create tables on boot (Alembic takes over later)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_migrations(conn)
    found = registry.discover()
    bus.subscribe("*", automation_engine.handle)
    bus.subscribe("*", webhook_adapter.on_event)
    logger.info("Truss kernel up. %d plugin(s) discovered: %s",
                len(found), ", ".join(sorted(found)))
    yield
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
app.include_router(agents.router)
app.include_router(automations.router)
app.include_router(connectors.router)
app.include_router(marketplace.router)
app.include_router(workspace.router)


@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}
