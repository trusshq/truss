"""Agent execution engine: AI employees running tasks autonomously.

An Agent executes a Task through the SAME validated record path as humans
(truss_kernel.services.records), using its own UUID as the actor. This means:
- schema validation, tenancy scoping, and event emission all apply unchanged
- every agent action is auditable (actor_id = agent.id, actor_type = 'agent')
- an agent can never bypass a rule a human couldn't bypass

Budget enforcement: each run accumulates token usage on the agent. When a
budget cap is set and exhausted, the agent auto-pauses (hard limit).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai import client as ai_client
from truss_kernel.ai.agent import _execute_tool, collect_tools
from truss_kernel.ai.vault import decrypt_secret
from truss_kernel.events import bus
from truss_kernel.models.agent import Agent, AgentStatus, AgentTask, TaskStatus
from truss_kernel.models.ai import AiKey

logger = logging.getLogger("truss.agents")

DEFAULT_MAX_STEPS = 8

BASE_PERSONA = """You are {name}, an AI employee with the role of {role} in this workspace.
You work autonomously: read the task, use the provided tools to inspect and update
business records, and complete the task fully. Rules:
- Use tools whenever you need to create, update, or look up records. Never invent ids or data.
- If a tool call fails, read the error and retry once with corrected arguments.
- Respect data quality: only write values that clearly belong in the field.
- When the task is complete, reply with a short summary of what you did.
- If you cannot complete the task, explain exactly what is missing."""


def _system_prompt(agent: Agent) -> str:
    persona = (agent.persona or "").strip()
    base = BASE_PERSONA.format(
        name=agent.name,
        role=agent.role or "general assistant",
    )
    return f"{base}\n\nAdditional persona instructions:\n{persona}" if persona else base


async def _resolve_key(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent) -> AiKey:
    """Pick the AI key for this agent: explicit key, else tenant default, else first."""
    if agent.ai_key_id:
        k = (await db.execute(select(AiKey).where(
            AiKey.id == agent.ai_key_id, AiKey.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if k is not None:
            return k
    k = (await db.execute(select(AiKey).where(
        AiKey.tenant_id == tenant_id, AiKey.is_default.is_(True)
    ))).scalars().first()
    if k is None:
        k = (await db.execute(select(AiKey).where(
            AiKey.tenant_id == tenant_id
        ).order_by(AiKey.created_at))).scalars().first()
    if k is None:
        raise LookupError("no AI key configured — add one in AI Keys before running agents")
    return k


async def _collect_agent_tools(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent):
    """Tools from enabled plugins, optionally restricted to agent.allowed_plugins."""
    openai_tools, index = await collect_tools(db, tenant_id)
    allowed = set(agent.allowed_plugins or [])
    if not allowed:
        return openai_tools, index
    filtered = [t for t in openai_tools if index[t["function"]["name"]]["plugin_id"] in allowed]
    findex = {t["function"]["name"]: index[t["function"]["name"]] for t in filtered}
    return filtered, findex


def _budget_exhausted(agent: Agent) -> bool:
    return agent.budget_tokens > 0 and agent.tokens_used >= agent.budget_tokens


async def run_task(db: AsyncSession, tenant_id: uuid.UUID, agent: Agent, task: AgentTask) -> dict:
    """Execute one task for one agent. Returns the result dict.

    State transitions handled here: approved -> running -> done|failed.
    Emits agent.* events with the agent as actor (actor_type='agent').
    """
    now = datetime.now(timezone.utc).isoformat()

    if agent.status != AgentStatus.active:
        task.status = TaskStatus.failed
        task.error = f"agent '{agent.name}' is {agent.status.value}"
        task.finished_at = now
        await db.commit()
        return {"ok": False, "error": task.error}

    if _budget_exhausted(agent):
        agent.status = AgentStatus.paused
        task.status = TaskStatus.failed
        task.error = "token budget exhausted — agent auto-paused"
        task.finished_at = now
        await bus.emit(db, tenant_id=tenant_id, event_type="agent.paused",
                       payload={"agent_id": str(agent.id), "agent": agent.name,
                                "reason": "budget_exhausted", "actor_type": "agent"},
                       actor_id=agent.id)
        await db.commit()
        return {"ok": False, "error": task.error}

    try:
        key = await _resolve_key(db, tenant_id, agent)
    except LookupError as e:
        task.status = TaskStatus.failed
        task.error = str(e)
        task.finished_at = now
        await db.commit()
        return {"ok": False, "error": task.error}

    task.status = TaskStatus.running
    task.started_at = now
    await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_started",
                   payload={"agent_id": str(agent.id), "agent": agent.name,
                            "task_id": str(task.id), "title": task.title,
                            "actor_type": "agent"},
                   actor_id=agent.id)
    await db.commit()

    api_key = decrypt_secret(key.api_key_enc) if key.api_key_enc else ""
    model = agent.model_override or key.model
    openai_tools, index = await _collect_agent_tools(db, tenant_id, agent)

    max_steps = int(agent.settings.get("max_steps") or DEFAULT_MAX_STEPS)
    temperature = float(agent.settings.get("temperature") or 0.2)

    messages: list[dict] = [{"role": "system", "content": _system_prompt(agent)}]
    user_msg = task.title
    if task.description:
        user_msg += f"\n\nDetails:\n{task.description}"
    messages.append({"role": "user", "content": user_msg})

    trace: list[dict] = []
    steps = 0
    total_tokens = 0
    reply = ""

    try:
        for _ in range(max_steps):
            steps += 1
            usage: dict = {}
            msg = await ai_client.chat_completion(
                base_url=key.base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                tools=openai_tools or None,
                temperature=temperature,
                usage_sink=usage,
            )
            total_tokens += int(usage.get("total_tokens") or 0)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                reply = msg.get("content") or ""
                break

            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc.get("function") or {}
                fn_name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                spec = index.get(fn_name)
                if spec is None:
                    result = {"error": f"unknown tool '{fn_name}'"}
                else:
                    logger.info("agent %s tool call: %s args=%s", agent.name, fn_name, args)
                    # The agent acts under its OWN id through the validated path,
                    # flagged actor_type='agent' in history + events.
                    result = await _execute_tool(db, tenant_id, agent.id, spec, args, actor_type="agent")
                trace.append({"tool": fn_name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or fn_name,
                    "content": json.dumps(result, default=str)[:8000],
                })
        else:
            reply = "(stopped: max steps reached)"
    except ai_client.ProviderError as e:
        task.status = TaskStatus.failed
        task.error = str(e)
        task.steps = steps
        task.tokens_used = total_tokens
        task.finished_at = datetime.now(timezone.utc).isoformat()
        agent.tokens_used += total_tokens
        agent.runs_count += 1
        await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_failed",
                       payload={"agent_id": str(agent.id), "agent": agent.name,
                                "task_id": str(task.id), "error": str(e),
                                "actor_type": "agent"},
                       actor_id=agent.id)
        await db.commit()
        return {"ok": False, "error": str(e), "steps": steps, "tokens": total_tokens}

    task.status = TaskStatus.done
    task.result = {"reply": reply, "trace": trace}
    task.steps = steps
    task.tokens_used = total_tokens
    task.finished_at = datetime.now(timezone.utc).isoformat()
    agent.tokens_used += total_tokens
    agent.runs_count += 1

    await bus.emit(db, tenant_id=tenant_id, event_type="agent.task_completed",
                   payload={"agent_id": str(agent.id), "agent": agent.name,
                            "task_id": str(task.id), "title": task.title,
                            "steps": steps, "tokens": total_tokens,
                            "actor_type": "agent"},
                   actor_id=agent.id)
    await db.commit()
    return {"ok": True, "reply": reply, "trace": trace, "steps": steps, "tokens": total_tokens}
