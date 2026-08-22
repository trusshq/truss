"""Phase C engine: autonomous orchestration (the Grok-bot / Hermes layer).

Three ways AI employees work without a human clicking Run:
1. Schedules — recurring tasks on an interval or cron expression. A background
   tick loop finds due schedules, creates a task, and executes it.
2. Triggers — reactive tasks fired by matching events on the bus (e.g. a new
   lead record). Subscribed as a wildcard handler, same pattern as automations.
3. Pipelines — an ordered chain of agent steps; each step's reply is handed to
   the next agent as context (multi-agent handoff).

Safety:
- depth guard: events emitted by agent runs carry depth+1; triggers ignore
  events at MAX_DEPTH so agent->event->agent loops can't run away
- self-loop guard: a trigger never fires on an event its OWN agent emitted
- cooldown: triggers can debounce event storms
- every schedule/trigger firing is recorded on the row (runs/fires_count,
  last_status, last_error)
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.agents import engine as agent_engine
from truss_kernel.db import SessionLocal
from truss_kernel.events import bus
from truss_kernel.models.agent import Agent, AgentStatus, AgentTask, TaskStatus
from truss_kernel.models.orchestration import (
    AgentPipeline,
    AgentSchedule,
    AgentTrigger,
    PipelineStatus,
    ScheduleKind,
)

logger = logging.getLogger("truss.orchestration")

MAX_DEPTH = 3
TICK_SECONDS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------- cron ----------

def _cron_field_matches(spec: str, value: int, max_val: int) -> bool:
    """Match one cron field: '*', '*/n', 'a', 'a-b', or comma lists thereof."""
    spec = spec.strip()
    if spec == "*":
        return True
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                return False
            if step > 0 and value % step == 0:
                return True
        elif "-" in part:
            lo, _, hi = part.partition("-")
            try:
                if int(lo) <= value <= int(hi):
                    return True
            except ValueError:
                return False
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                return False
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    """True if a 5-field cron expression matches the given minute."""
    fields = expr.split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    return (
        _cron_field_matches(minute, dt.minute, 59)
        and _cron_field_matches(hour, dt.hour, 23)
        and _cron_field_matches(dom, dt.day, 31)
        and _cron_field_matches(month, dt.month, 12)
        and _cron_field_matches(dow, dt.weekday(), 6)  # 0 = Monday
    )


def next_cron_run(expr: str, after: datetime) -> datetime:
    """Scan forward minute-by-minute (up to 366 days) for the next match."""
    cursor = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366):
        if cron_matches(expr, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    return after + timedelta(days=366)


def compute_next_run(s: AgentSchedule, after: datetime) -> datetime:
    if s.kind == ScheduleKind.cron and s.cron:
        return next_cron_run(s.cron, after)
    return after + timedelta(minutes=max(1, s.every_minutes))


def compute_next_run_raw(kind: str, every_minutes: int, cron: str, after: datetime) -> datetime:
    """Same as compute_next_run but from raw values (for creation before a row exists)."""
    if kind == ScheduleKind.cron.value and cron:
        return next_cron_run(cron, after)
    return after + timedelta(minutes=max(1, every_minutes))


# ---------- task creation + execution (shared) ----------

async def _spawn_task(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent, *,
                      title: str, prompt: str, needs_review: bool,
                      source: str, source_id: str) -> AgentTask:
    """Create a task for an autonomous source (schedule/trigger/pipeline)."""
    t = AgentTask(
        tenant_id=tenant_id,
        agent_id=agent.id,
        title=title,
        description=prompt,
        needs_review=needs_review,
        created_by=None,  # autonomous — no human creator
        status=TaskStatus.proposed if needs_review else TaskStatus.approved,
        approved_by=None if needs_review else agent.id,
    )
    db.add(t)
    await db.flush()
    await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_created",
                   payload={"agent_id": str(agent.id), "agent": agent.name,
                            "task_id": str(t.id), "title": title,
                            "needs_review": needs_review,
                            "source": source, "source_id": source_id,
                            "actor_type": "system"},
                   actor_id=agent.id)
    return t


async def _execute_task(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent,
                        task: AgentTask) -> dict:
    """Run an approved task; returns the engine result dict."""
    if task.status == TaskStatus.proposed:
        return {"ok": False, "skipped": "needs_review"}
    return await agent_engine.run_task(db, tenant_id, agent, task)


# ---------- scheduler ----------

class Scheduler:
    """Background loop that fires due AgentSchedules."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("orchestration scheduler started (tick=%ss)", TICK_SECONDS)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - the loop must survive any single tick failure
                logger.exception("scheduler tick failed")
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self, now: datetime | None = None) -> int:
        """Fire every due schedule once. Returns the number fired."""
        now = now or _now()
        fired = 0
        async with SessionLocal() as db:
            due = (await db.execute(select(AgentSchedule).where(
                AgentSchedule.enabled.is_(True),
                AgentSchedule.next_run_at != "",
                AgentSchedule.next_run_at <= _iso(now),
            ))).scalars().all()

            for s in due:
                agent = (await db.execute(select(Agent).where(
                    Agent.id == s.agent_id, Agent.tenant_id == s.tenant_id
                ))).scalar_one_or_none()
                # advance next_run BEFORE executing so a slow run can't double-fire
                s.next_run_at = _iso(compute_next_run(s, now))
                s.last_run_at = _iso(now)
                s.runs_count += 1
                if agent is None or agent.status == AgentStatus.terminated:
                    s.last_status = "skipped"
                    s.last_error = "agent missing or terminated"
                    await db.commit()
                    continue
                try:
                    task = await _spawn_task(
                        db, s.tenant_id, agent, title=s.title, prompt=s.prompt,
                        needs_review=s.needs_review, source="schedule", source_id=str(s.id),
                    )
                    result = await _execute_task(db, s.tenant_id, agent, task)
                    s.last_status = "done" if result.get("ok") else (
                        "pending_review" if result.get("skipped") else "failed"
                    )
                    s.last_error = "" if result.get("ok") or result.get("skipped") else str(result.get("error", ""))
                    fired += 1
                    logger.info("schedule '%s' fired for agent '%s' -> %s",
                                s.name, agent.name, s.last_status)
                except Exception as e:  # noqa: BLE001
                    s.last_status = "failed"
                    s.last_error = str(e)[:500]
                    logger.exception("schedule '%s' failed", s.name)
                await db.commit()
        return fired


scheduler = Scheduler()


# ---------- triggers ----------

def _expand_placeholders(text: str, envelope: dict) -> str:
    payload = envelope.get("payload") or {}
    return (
        text.replace("{event}", envelope.get("type", ""))
        .replace("{object}", str(payload.get("object", "")))
        .replace("{record_id}", str(payload.get("record_id", "")))
    )


async def handle_trigger_event(envelope: dict) -> None:
    """Wildcard bus handler: fire matching AgentTriggers."""
    depth = int(envelope.get("_depth", 0))
    if depth >= MAX_DEPTH:
        return
    db: AsyncSession | None = envelope.get("_db")
    if db is None:
        return
    event_type = envelope.get("type", "")
    if not event_type or event_type.startswith("agent."):
        return  # don't react to our own orchestration events
    try:
        tenant_id = uuid.UUID(envelope["tenant_id"])
    except (KeyError, ValueError):
        return

    payload = envelope.get("payload") or {}
    # self-loop guard: skip events emitted by an agent acting as actor
    actor_type = payload.get("actor_type")
    actor_id = envelope.get("actor_id")

    object_slug = payload.get("object") or ""
    now = _now()

    triggers = (await db.execute(select(AgentTrigger).where(
        AgentTrigger.tenant_id == tenant_id,
        AgentTrigger.enabled.is_(True),
        AgentTrigger.event_type == event_type,
    ))).scalars().all()

    for tr in triggers:
        if tr.object_slug and tr.object_slug != object_slug:
            continue
        # don't fire on events the trigger's own agent produced
        if actor_type == "agent" and actor_id and actor_id == str(tr.agent_id):
            continue
        # cooldown debounce
        if tr.cooldown_seconds > 0 and tr.last_fired_at:
            try:
                last = datetime.fromisoformat(tr.last_fired_at)
                if (now - last).total_seconds() < tr.cooldown_seconds:
                    continue
            except ValueError:
                pass

        agent = (await db.execute(select(Agent).where(
            Agent.id == tr.agent_id, Agent.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if agent is None or agent.status == AgentStatus.terminated:
            continue

        title = _expand_placeholders(tr.title, envelope)
        prompt = _expand_placeholders(tr.prompt, envelope)
        tr.last_fired_at = _iso(now)
        tr.fires_count += 1
        try:
            task = await _spawn_task(
                db, tenant_id, agent, title=title, prompt=prompt,
                needs_review=tr.needs_review, source="trigger", source_id=str(tr.id),
            )
            await _execute_task(db, tenant_id, agent, task)
            logger.info("trigger '%s' fired for agent '%s' on %s", tr.name, agent.name, event_type)
        except Exception:  # noqa: BLE001
            logger.exception("trigger '%s' failed", tr.name)


# ---------- pipelines ----------

async def run_pipeline(db: AsyncSession, tenant_id: uuid.UUID,
                       pipeline: AgentPipeline, initial_input: str = "") -> dict:
    """Execute the pipeline's steps in order, handing each reply forward."""
    if pipeline.status != PipelineStatus.active:
        return {"ok": False, "error": "pipeline is paused"}
    steps = pipeline.steps or []
    if not steps:
        return {"ok": False, "error": "pipeline has no steps"}

    pipeline.last_run_at = _iso(_now())
    pipeline.runs_count += 1
    results: list[dict] = []
    carry = initial_input

    for i, step in enumerate(steps):
        agent_id = step.get("agent_id")
        try:
            agent_uuid = uuid.UUID(str(agent_id))
        except (ValueError, TypeError):
            pipeline.last_status = "failed"
            await db.commit()
            return {"ok": False, "error": f"step {i}: invalid agent_id", "steps": results}

        agent = (await db.execute(select(Agent).where(
            Agent.id == agent_uuid, Agent.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if agent is None:
            pipeline.last_status = "failed"
            await db.commit()
            return {"ok": False, "error": f"step {i}: agent not found", "steps": results}

        title = step.get("title") or f"{pipeline.name} — step {i + 1}"
        prompt = step.get("prompt") or ""
        if carry:
            prompt = (prompt + "\n\nOutput from the previous step:\n" + carry) if prompt else carry

        task = await _spawn_task(
            db, tenant_id, agent, title=title, prompt=prompt,
            needs_review=False, source="pipeline", source_id=str(pipeline.id),
        )
        result = await _execute_task(db, tenant_id, agent, task)
        results.append({
            "step": i,
            "agent_id": str(agent.id),
            "agent": agent.name,
            "task_id": str(task.id),
            "ok": bool(result.get("ok")),
            "reply": result.get("reply", ""),
            "error": result.get("error", ""),
        })
        if not result.get("ok"):
            pipeline.last_status = "failed"
            await db.commit()
            return {"ok": False, "error": f"step {i} failed: {result.get('error', '')}", "steps": results}
        carry = result.get("reply", "")

    pipeline.last_status = "done"
    await db.commit()
    return {"ok": True, "steps": results, "final_reply": carry}
