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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai import client as ai_client
from truss_kernel.ai.vault import decrypt_secret
from truss_kernel.events import bus
from truss_kernel.models.ai import AiKey
from truss_kernel.models.agent import Agent, AgentStatus, AgentTask, TaskStatus
from truss_kernel.models.metadata import FieldDef, ObjectDef
from truss_kernel.models.plugin import PluginInstall
from truss_kernel.plugins.registry import registry
from truss_kernel.services import analytics
from truss_kernel.services import records as svc

logger = logging.getLogger("truss.ai")

MAX_STEPS = 6

# Roles allowed to use admin-gated control tools (hire agents, etc.)
ADMIN_ROLES = {"owner", "admin"}
# Roles allowed to mutate (create/update records, assign tasks, create goals)
MUTATE_ROLES = {"owner", "admin", "member"}

SYSTEM_PROMPT = """You are the Truss workspace agent. You help the user manage their
business data AND the workspace itself by calling the provided tools. Rules:
- Use tools whenever the user asks to create, update, or look up records.
- You can also manage the workspace: hire AI employees (kernel__hire_agent),
  assign them tasks (kernel__assign_task), create goals (kernel__create_goal),
  and create/update records in ANY object (kernel__create_record /
  kernel__update_record). Call kernel__list_objects first to learn valid
  object slugs and fields, and kernel__list_agents to find agent ids.
- Prefer calling a tool over guessing; if a tool call fails, read the error and retry once with corrected arguments.
- Keep replies short and concrete. After tool calls, summarize what happened.
- Never invent record ids or data you did not retrieve."""


# ---------- tool collection ----------

async def collect_tools(db: AsyncSession, tenant_id: uuid.UUID, role: str = "member") -> tuple[list[dict], dict[str, dict]]:
    """Build OpenAI function schemas from enabled plugins + kernel control tools.

    Returns (openai_tools, index) where index maps function name -> spec dict
    carrying the backing action/object for execution.

    `role` gates the control tools: admin-gated tools (hire agent) are only
    offered to owner/admin; mutation tools are offered to member+.
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

    # Kernel analytics tool (Phase D): always available, read-only. Lets the
    # agent answer natural-language data questions ("how many leads this week?")
    # by running structured aggregate queries over the record store.
    analytics_fn = "kernel__analytics"
    openai_tools.append({
        "type": "function",
        "function": {
            "name": analytics_fn,
            "description": (
                "Run a read-only analytics query over business records. Use this to "
                "answer questions like counts, totals, averages, breakdowns by field, "
                "or trends over time. Arguments: object (required, e.g. 'lead'); "
                "metric ('count'|'group_by'|'sum'|'avg'|'min'|'max'|'summary'|'time_series'); "
                "field (the field to group or aggregate); value_field (for group_by sum/avg); "
                "bucket ('day'|'week'|'month' for time_series); days (time_series window)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "object": {"type": "string", "description": "Object slug to query, e.g. 'lead'"},
                    "metric": {"type": "string", "description": "count|group_by|sum|avg|min|max|summary|time_series"},
                    "field": {"type": "string", "description": "Field to group or aggregate"},
                    "value_field": {"type": "string", "description": "Numeric field for group_by sum/avg"},
                    "bucket": {"type": "string", "description": "day|week|month for time_series"},
                    "days": {"type": "integer", "description": "time_series window in days"},
                    "limit": {"type": "integer", "description": "max group_by buckets"},
                },
                "required": ["object"],
            },
        },
    })
    index[analytics_fn] = {
        "plugin_id": "kernel",
        "tool_slug": "analytics",
        "action": "analytics",
        "object": None,
    }

    # ---- Kernel control tools (Phase F): let the chat agent manage the
    # workspace itself — hire agents, assign tasks, create goals, and CRUD
    # records on ANY object. Gated by the invoking user's role. ----

    def _add_control(fn_name: str, description: str, properties: dict,
                     required: list[str], action: str) -> None:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": fn_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
        index[fn_name] = {
            "plugin_id": "kernel",
            "tool_slug": fn_name,
            "action": action,
            "object": None,
        }

    # Read tools: available to everyone (viewer+)
    _add_control(
        "kernel__list_objects",
        "List all data objects (tables) available in this workspace, with their slugs and fields. "
        "Use this first to discover what objects exist before creating or querying records.",
        {}, [],
        "list_objects",
    )
    _add_control(
        "kernel__list_agents",
        "List all AI employees (agents) in this workspace with their id, name, role, and status.",
        {}, [],
        "list_agents",
    )
    _add_control(
        "kernel__search_records",
        "Search records across a specific object by free text. Arguments: object (required slug), "
        "search (optional text), limit (optional, default 10).",
        {
            "object": {"type": "string", "description": "Object slug, e.g. 'lead'"},
            "search": {"type": "string", "description": "Free-text search"},
            "limit": {"type": "integer", "description": "Max results (default 10)"},
        },
        ["object"],
        "search_records",
    )
    _add_control(
        "kernel__global_search",
        "Search the ENTIRE workspace at once — records in every object, plus AI employees and "
        "goals. Use this when the user asks to find something but you don't know which object "
        "it lives in. Arguments: q (required search text), limit (optional, default 5 per group).",
        {
            "q": {"type": "string", "description": "Search text"},
            "limit": {"type": "integer", "description": "Max results per group (default 5)"},
        },
        ["q"],
        "global_search",
    )

    # Mutation tools: member+
    if role in MUTATE_ROLES:
        _add_control(
            "kernel__create_record",
            "Create a new record in any object. Arguments: object (required slug), data (object of "
            "field slug -> value). Use kernel__list_objects first to learn valid fields.",
            {
                "object": {"type": "string", "description": "Object slug, e.g. 'lead'"},
                "data": {"type": "object", "description": "Field values keyed by field slug"},
            },
            ["object", "data"],
            "create_record_any",
        )
        _add_control(
            "kernel__update_record",
            "Update an existing record. Arguments: object (required slug), record_id (required UUID), "
            "data (object of field slug -> new value).",
            {
                "object": {"type": "string", "description": "Object slug"},
                "record_id": {"type": "string", "description": "Record UUID to update"},
                "data": {"type": "object", "description": "Field values to change"},
            },
            ["object", "record_id", "data"],
            "update_record_any",
        )
        _add_control(
            "kernel__assign_task",
            "Assign a task to an AI employee. Arguments: agent_id (required UUID), title (required), "
            "description (optional). The task will need human approval before running.",
            {
                "agent_id": {"type": "string", "description": "Agent UUID"},
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task details"},
            },
            ["agent_id", "title"],
            "assign_task",
        )
        _add_control(
            "kernel__create_goal",
            "Create a goal. Arguments: title (required), metric (optional), target_value (optional number), "
            "owner_agent_id (optional agent UUID; if omitted the goal is owned by the current user).",
            {
                "title": {"type": "string", "description": "Goal title"},
                "metric": {"type": "string", "description": "What is being measured"},
                "target_value": {"type": "number", "description": "Numeric target"},
                "owner_agent_id": {"type": "string", "description": "Optional owning agent UUID"},
            },
            ["title"],
            "create_goal",
        )

    # Admin tools: owner/admin only
    if role in ADMIN_ROLES:
        _add_control(
            "kernel__hire_agent",
            "Hire a new AI employee. Arguments: name (required), role (optional job title), "
            "icon (optional emoji), permission_role ('member' or 'viewer', default 'member').",
            {
                "name": {"type": "string", "description": "Agent name"},
                "role": {"type": "string", "description": "Job title / role description"},
                "icon": {"type": "string", "description": "Emoji icon"},
                "permission_role": {"type": "string", "description": "'member' or 'viewer'"},
            },
            ["name"],
            "hire_agent",
        )
        _add_control(
            "kernel__create_object",
            "Create a brand-new data object (table) from a natural-language description — the "
            "schema builder. Arguments: slug (required, lowercase_snake), name (required), "
            "fields (required array of {slug, name, type}), icon (optional emoji), "
            "description (optional). Field types: text, textarea, number, currency, boolean, "
            "date, datetime, email, phone, url, select, multiselect.",
            {
                "slug": {"type": "string", "description": "lowercase_snake slug, e.g. 'project'"},
                "name": {"type": "string", "description": "Display name, e.g. 'Project'"},
                "fields": {
                    "type": "array",
                    "description": "Field definitions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slug": {"type": "string"},
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "required": {"type": "boolean"},
                        },
                        "required": ["slug", "name", "type"],
                    },
                },
                "icon": {"type": "string", "description": "Emoji icon"},
                "description": {"type": "string"},
            },
            ["slug", "name", "fields"],
            "create_object",
        )
        _add_control(
            "kernel__add_field",
            "Add a new field to an existing object. Arguments: object (required slug), "
            "slug (required), name (required), type (required field type), required (optional bool).",
            {
                "object": {"type": "string", "description": "Object slug to extend"},
                "slug": {"type": "string", "description": "Field slug"},
                "name": {"type": "string", "description": "Field display name"},
                "type": {"type": "string", "description": "Field type"},
                "required": {"type": "boolean"},
            },
            ["object", "slug", "name", "type"],
            "add_field",
        )

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

    # Phase D: read-only analytics (never writes, safe for agents)
    if action == "analytics":
        try:
            return await analytics.run_query(db, tenant_id, dict(args))
        except analytics.AnalyticsError as e:
            return {"error": str(e)}

    # ---- Phase F kernel control actions ----
    if action == "list_objects":
        objs = (await db.execute(
            select(ObjectDef).where(ObjectDef.tenant_id == tenant_id).order_by(ObjectDef.slug)
        )).scalars().all()
        out = []
        for o in objs:
            fields = (await db.execute(
                select(FieldDef).where(FieldDef.object_id == o.id).order_by(FieldDef.position)
            )).scalars().all()
            out.append({
                "slug": o.slug, "name": o.name, "name_plural": o.name_plural,
                "fields": [{"slug": f.slug, "name": f.name, "type": f.type, "required": f.required} for f in fields],
            })
        return {"objects": out, "total": len(out)}

    if action == "list_agents":
        agents = (await db.execute(
            select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.created_at)
        )).scalars().all()
        return {"agents": [
            {"id": str(a.id), "name": a.name, "role": a.role, "icon": a.icon,
             "status": a.status.value, "permission_role": a.permission_role}
            for a in agents
        ], "total": len(agents)}

    if action == "search_records":
        if not object_slug:
            return {"error": "object is required"}
        try:
            obj = await svc.get_object(db, tenant_id, object_slug)
        except svc.ObjectNotFound as e:
            return {"error": str(e)}
        total, rows = await svc.query_records(
            db, tenant_id, obj, search=args.get("search"), limit=int(args.get("limit", 10)),
        )
        return {"total": total, "items": [svc.rec_to_dict(r) for r in rows]}

    if action == "create_record_any":
        if not object_slug:
            return {"error": "object is required"}
        try:
            obj = await svc.get_object(db, tenant_id, object_slug)
        except svc.ObjectNotFound as e:
            return {"error": str(e)}
        data = args.get("data") or {}
        if not isinstance(data, dict):
            return {"error": "data must be an object of field slug -> value"}
        try:
            rec = await svc.create_record(db, tenant_id, user_id, obj, data, actor_type=actor_type)
            await db.commit()
            return {"created": svc.rec_to_dict(rec)}
        except svc.ValidationError as e:
            return {"error": f"validation failed: {e}"}

    if action == "update_record_any":
        if not object_slug:
            return {"error": "object is required"}
        record_id = args.get("record_id")
        if not record_id:
            return {"error": "record_id is required"}
        try:
            obj = await svc.get_object(db, tenant_id, object_slug)
        except svc.ObjectNotFound as e:
            return {"error": str(e)}
        data = args.get("data") or {}
        if not isinstance(data, dict):
            return {"error": "data must be an object of field slug -> value"}
        try:
            rec = await svc.update_record(db, tenant_id, user_id, obj, uuid.UUID(str(record_id)), data, actor_type=actor_type)
            await db.commit()
            return {"updated": svc.rec_to_dict(rec)}
        except svc.RecordNotFound as e:
            return {"error": str(e)}
        except svc.ValidationError as e:
            return {"error": f"validation failed: {e}"}
        except ValueError:
            return {"error": "record_id is not a valid UUID"}

    if action == "assign_task":
        agent_id = args.get("agent_id")
        title = args.get("title")
        if not agent_id or not title:
            return {"error": "agent_id and title are required"}
        try:
            agent = (await db.execute(select(Agent).where(
                Agent.id == uuid.UUID(str(agent_id)), Agent.tenant_id == tenant_id
            ))).scalar_one_or_none()
        except ValueError:
            return {"error": "agent_id is not a valid UUID"}
        if agent is None:
            return {"error": "agent not found"}
        t = AgentTask(
            tenant_id=tenant_id, agent_id=agent.id, title=title,
            description=args.get("description") or "",
            needs_review=True, status=TaskStatus.proposed, created_by=user_id,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return {"assigned": {"task_id": str(t.id), "agent": agent.name, "title": title,
                             "status": "proposed (needs approval)"}}

    if action == "create_goal":
        from truss_kernel.agents import org as org_svc
        title = args.get("title")
        if not title:
            return {"error": "title is required"}
        owner_agent_id = None
        if args.get("owner_agent_id"):
            try:
                owner_agent_id = uuid.UUID(str(args["owner_agent_id"]))
            except ValueError:
                return {"error": "owner_agent_id is not a valid UUID"}
        try:
            g = await org_svc.create_goal(
                db, tenant_id, title=title, metric=args.get("metric") or "",
                target_value=float(args.get("target_value") or 0),
                owner_agent_id=owner_agent_id,
                owner_user_id=None if owner_agent_id else user_id,
                created_by=user_id,
            )
            await db.commit()
            return {"created_goal": {"id": str(g.id), "title": g.title}}
        except org_svc.OrgError as e:
            return {"error": str(e)}

    if action == "hire_agent":
        name = args.get("name")
        if not name:
            return {"error": "name is required"}
        clash = (await db.execute(select(Agent).where(
            Agent.tenant_id == tenant_id, Agent.name == name
        ))).scalar_one_or_none()
        if clash:
            return {"error": f"an agent named '{name}' already exists"}
        perm = args.get("permission_role") or "member"
        if perm not in ("member", "viewer"):
            perm = "member"
        a = Agent(
            tenant_id=tenant_id, name=name, role=args.get("role") or "",
            icon=args.get("icon") or "🤖", permission_role=perm,
            status=AgentStatus.active,
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return {"hired": {"id": str(a.id), "name": a.name, "role": a.role, "status": a.status.value}}

    # ---- Phase I: global search (RAG-lite retrieval) ----
    if action == "global_search":
        from truss_kernel.routes.search import run_global_search
        q = args.get("q")
        if not q or not str(q).strip():
            return {"error": "q is required"}
        return await run_global_search(db, tenant_id, str(q), int(args.get("limit", 5)))

    # ---- Phase I: natural-language schema builder ----
    if action == "create_object":
        from truss_kernel.models.metadata import FieldType
        slug = (args.get("slug") or "").strip().lower().replace("-", "_").replace(" ", "_")
        name = (args.get("name") or "").strip()
        fields = args.get("fields") or []
        if not slug or not name:
            return {"error": "slug and name are required"}
        if not slug.replace("_", "").isalnum():
            return {"error": "slug must be lowercase letters, digits, and underscores"}
        if not isinstance(fields, list) or not fields:
            return {"error": "fields must be a non-empty array of {slug, name, type}"}
        clash = (await db.execute(select(ObjectDef).where(
            ObjectDef.tenant_id == tenant_id, ObjectDef.slug == slug
        ))).scalar_one_or_none()
        if clash:
            return {"error": f"object '{slug}' already exists"}
        obj = ObjectDef(
            tenant_id=tenant_id, slug=slug, name=name,
            name_plural=name + "s", description=args.get("description") or "",
            icon=args.get("icon") or "📦", plugin_id="", is_builtin=False,
        )
        db.add(obj)
        await db.flush()
        valid_types = {t.value for t in FieldType}
        for i, f in enumerate(fields):
            if not isinstance(f, dict) or not f.get("slug") or not f.get("name"):
                return {"error": f"field #{i + 1} needs slug and name"}
            ftype = str(f.get("type", "text")).lower()
            if ftype not in valid_types:
                ftype = "text"
            fslug = str(f["slug"]).strip().lower().replace("-", "_").replace(" ", "_")
            db.add(FieldDef(
                object_id=obj.id, slug=fslug, name=str(f["name"]).strip(),
                type=FieldType(ftype), required=bool(f.get("required", False)),
                position=i, options={},
            ))
        await db.flush()
        await bus.emit(db, tenant_id=tenant_id, event_type="object.created",
                       payload={"object": slug, "actor_type": actor_type}, actor_id=user_id)
        await db.commit()
        return {"created_object": {"slug": slug, "name": name, "fields": len(fields)}}

    if action == "add_field":
        from truss_kernel.models.metadata import FieldType
        if not object_slug:
            return {"error": "object is required"}
        obj = (await db.execute(select(ObjectDef).where(
            ObjectDef.tenant_id == tenant_id, ObjectDef.slug == object_slug
        ))).scalar_one_or_none()
        if obj is None:
            return {"error": f"object '{object_slug}' not found"}
        fslug = (args.get("slug") or "").strip().lower().replace("-", "_").replace(" ", "_")
        fname = (args.get("name") or "").strip()
        ftype = str(args.get("type", "text")).lower()
        valid_types = {t.value for t in FieldType}
        if not fslug or not fname:
            return {"error": "slug and name are required"}
        if ftype not in valid_types:
            return {"error": f"unknown field type '{ftype}'; valid: {sorted(valid_types)}"}
        clash = (await db.execute(select(FieldDef).where(
            FieldDef.object_id == obj.id, FieldDef.slug == fslug
        ))).scalar_one_or_none()
        if clash:
            return {"error": f"field '{fslug}' already exists on '{object_slug}'"}
        max_pos = (await db.scalar(
            select(func.max(FieldDef.position)).where(FieldDef.object_id == obj.id)
        )) or 0
        db.add(FieldDef(
            object_id=obj.id, slug=fslug, name=fname, type=FieldType(ftype),
            required=bool(args.get("required", False)), position=max_pos + 1, options={},
        ))
        await db.flush()
        await bus.emit(db, tenant_id=tenant_id, event_type="object.field_added",
                       payload={"object": object_slug, "field": fslug, "actor_type": actor_type},
                       actor_id=user_id)
        await db.commit()
        return {"added_field": {"object": object_slug, "slug": fslug, "type": ftype}}

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
                    history: list[dict] | None = None,
                    role: str = "member") -> dict:
    """Run the BYOK agent loop. Returns {reply, trace, steps, model}.

    `role` gates which kernel control tools are offered to the model.
    """
    api_key = decrypt_secret(key.api_key_enc) if key.api_key_enc else ""
    openai_tools, index = await collect_tools(db, tenant_id, role=role)

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
