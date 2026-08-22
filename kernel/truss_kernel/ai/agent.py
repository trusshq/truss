"""The Truss agent loop: BYOK models executing plugin-declared tools.

Security model:
- The agent inherits the INVOKING USER's tenant scope — every record op goes
  through truss_kernel.services.records, the same validated path as the API.
- Only tools from ENABLED plugin installs are offered to the model.
- Tool errors are fed back to the model (self-correction), never raised raw.
- Every tool execution is recorded in the response trace + event log.
"""
import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai import client as ai_client
from truss_kernel.ai.vault import decrypt_secret
from truss_kernel.models.ai import AiKey
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.registry import registry
from truss_kernel.services import records as svc

logger = logging.getLogger("truss.ai")

MAX_STEPS = 6

SYSTEM_PROMPT = """You are the Truss workspace agent. You help the user manage their
business data by calling the provided tools. Rules:
- Use tools whenever the user asks to create, update, or look up records.
- Prefer calling a tool over guessing; if a tool call fails, read the error and retry once with corrected arguments.
- Keep replies short and concrete. After tool calls, summarize what happened.
- Never invent record ids or data you did not retrieve."""


# ---------- tool collection ----------

async def collect_tools(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[list[dict], dict[str, dict]]:
    """Build OpenAI function schemas from enabled plugins.

    Returns (openai_tools, index) where index maps function name -> spec dict
    carrying the backing action/object for execution.
    """
    installs = (await db.execute(
        select(PluginInstall).where(
            PluginInstall.tenant_id == tenant_id,
            PluginInstall.enabled.is_(True),
        )
    )).scalars().all()

    openai_tools: list[dict] = []
    index: dict[str, dict] = {}

    for inst in installs:
        manifest = registry.get(inst.plugin_id)
        if manifest is None:
            continue
        for tool in manifest.tools:
            fn_name = f"{manifest.id}__{tool.slug}".replace("-", "_")
            properties: dict = {}
            required: list[str] = []
            for p in tool.params:
                properties[p.name] = {
                    "type": p.type if p.type in ("string", "number", "boolean", "integer", "array") else "string",
                    "description": p.description,
                }
                if p.required:
                    required.append(p.name)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": fn_name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
            index[fn_name] = {
                "plugin_id": manifest.id,
                "tool_slug": tool.slug,
                "action": tool.action,
                "object": tool.object,
            }
    return openai_tools, index


# ---------- tool execution ----------

async def _execute_tool(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID,
                        spec: dict, args: dict, actor_type: str = "user") -> dict:
    """Execute one tool under the invoking actor's tenant scope.

    actor_type is 'user' for chat and 'agent' for autonomous AI employees —
    it flows into record history + events for auditing.
    """
    action = spec["action"]
    object_slug = args.get("object") or spec.get("object")

    if action in ("create_record", "update_record", "query_records"):
        if not object_slug:
            return {"error": "tool has no target object"}
        try:
            obj = await svc.get_object(db, tenant_id, object_slug)
        except svc.ObjectNotFound as e:
            return {"error": str(e)}

        if action == "create_record":
            data = {k: v for k, v in args.items() if k != "object"}
            try:
                rec = await svc.create_record(db, tenant_id, user_id, obj, data, actor_type=actor_type)
                await db.commit()
                return {"created": svc.rec_to_dict(rec)}
            except svc.ValidationError as e:
                return {"error": f"validation failed: {e}"}

        if action == "update_record":
            record_id = args.get("record_id")
            if not record_id:
                return {"error": "record_id is required"}
            patch = {k: v for k, v in args.items() if k not in ("object", "record_id")}
            try:
                rec = await svc.update_record(db, tenant_id, user_id, obj, uuid.UUID(str(record_id)), patch, actor_type=actor_type)
                await db.commit()
                return {"updated": svc.rec_to_dict(rec)}
            except svc.RecordNotFound as e:
                return {"error": str(e)}
            except svc.ValidationError as e:
                return {"error": f"validation failed: {e}"}
            except ValueError:
                return {"error": "record_id is not a valid UUID"}

        # query_records
        total, rows = await svc.query_records(
            db, tenant_id, obj,
            search=args.get("search"),
            limit=int(args.get("limit", 10)),
        )
        return {"total": total, "items": [svc.rec_to_dict(r) for r in rows]}

    return {"error": f"unsupported action '{action}' in this kernel version"}


# ---------- agent loop ----------

async def run_agent(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID,
                    key: AiKey, user_message: str,
                    history: list[dict] | None = None) -> dict:
    """Run the BYOK agent loop. Returns {reply, trace, steps, model}."""
    api_key = decrypt_secret(key.api_key_enc) if key.api_key_enc else ""
    openai_tools, index = await collect_tools(db, tenant_id)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or []):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:4000]})
    messages.append({"role": "user", "content": user_message})

    trace: list[dict] = []
    steps = 0

    for _ in range(MAX_STEPS):
        steps += 1
        msg = await ai_client.chat_completion(
            base_url=key.base_url,
            api_key=api_key,
            model=key.model,
            messages=messages,
            tools=openai_tools or None,
        )
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return {
                "reply": msg.get("content") or "",
                "trace": trace,
                "steps": steps,
                "model": key.model,
            }

        # assistant message with the tool calls (kept verbatim for the provider)
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
                logger.info("agent tool call: %s args=%s", fn_name, args)
                result = await _execute_tool(db, tenant_id, user_id, spec, args)
            trace.append({"tool": fn_name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or fn_name,
                "content": json.dumps(result, default=str)[:8000],
            })

    return {
        "reply": "(stopped: max tool steps reached)",
        "trace": trace,
        "steps": steps,
        "model": key.model,
    }
