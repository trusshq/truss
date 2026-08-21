# 🏗️ Truss

**The open-source, plugin-first business OS.**

A truss is a structural frame where every member carries load, so the whole holds far more than any single piece. Truss is that for your business: a small kernel where **every app is a plugin** — install what you need, disable what you don't, bring your own AI keys, connect your own databases.

> *The structure your business runs on.*

## Why Truss

- **Everything is a plugin.** CRM, invoicing, helpdesk — all declarative plugins on one kernel. Enable/disable with one click. No lock-in.
- **Metadata-driven core.** Business objects (leads, deals, invoices…) are data, not migrations. Plugins and users declare objects + fields; the kernel renders and validates them.
- **AI-agent native (BYOK).** Plugins register typed *tools* an AI agent can call. Bring your own model endpoint — anything OpenAI-compatible (DeepSeek, OpenRouter, Groq, Ollama, OpenAI…). Your keys, your data.
- **Event seam built in.** Every action emits an event. Forward them to your own analytics (PostHog, Mixpanel, GA), wire automations, feed AI context.
- **Multi-tenant from day one.** Workspaces, roles (owner/admin/member/viewer), JWT auth, tenant-scoped everything.
- **Self-host or cloud.** Docker Compose for your own infra; the frontend is a plain Next.js app you can put on Vercel.

## Stack

| Layer | Choice |
|---|---|
| Kernel | Python 3.11 · FastAPI · SQLAlchemy 2 (async) |
| Database | PostgreSQL 16 (JSONB metadata + records) |
| Frontend | Next.js 16 · React 19 · TypeScript · Tailwind v4 |
| Auth | JWT (HS256) · bcrypt |
| Events | In-process bus → durable `event_log` (NATS later) |

## Quickstart (local dev)

**1. Kernel** (needs Postgres on `127.0.0.1:5432` — adjust `kernel/.env`):

```bash
cd kernel
uv sync
uv run uvicorn truss_kernel.main:app --port 8000
```

**2. Frontend:**

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

**3. Use it:** open http://localhost:3000 → create a workspace → go to **Plugins** → install **Truss CRM** → Leads, Pipeline, Contacts, and Companies appear in the sidebar.

**4. Verify:** `cd kernel && uv run python smoke_test.py` — 23 end-to-end checks (auth, tenancy, plugin install, records CRUD, validation, isolation, events, enable/disable).

Interactive API docs: http://127.0.0.1:8000/docs

## Self-hosted (Docker)

```bash
docker compose up -d    # Postgres + Redis + kernel on :8000
```

## Repository layout

```
Truss/
├── kernel/                  # Python kernel (FastAPI)
│   ├── truss_kernel/
│   │   ├── main.py          # app entrypoint
│   │   ├── config.py        # settings (env-driven)
│   │   ├── db.py            # async engine/session
│   │   ├── security.py      # bcrypt + JWT
│   │   ├── deps.py          # auth context + RBAC
│   │   ├── events.py        # event bus + persistence
│   │   ├── models/          # tenants, users, metadata, plugins, events
│   │   ├── plugins/         # manifest schema + registry
│   │   └── routes/          # auth, objects, records, plugins, events
│   ├── plugins_builtin/     # first-party plugins (truss-crm)
│   └── smoke_test.py        # end-to-end verification
├── frontend/                # Next.js shell (plugin-driven UI)
├── plugins/                 # YOUR external plugins go here
├── docs/                    # architecture + plugin authoring guide
└── docker-compose.yml
```

## Writing a plugin

A plugin is a folder with a `plugin.json` manifest — objects, AI tools, automations, UI surfaces, and the permissions it requests. No code executes; the kernel interprets your declaration. See [docs/PLUGIN_MANIFEST.md](docs/PLUGIN_MANIFEST.md).

## Roadmap

- [x] Phase 0 — kernel: tenancy, metadata layer, plugin runtime, event seam, CRM plugin, frontend shell
- [ ] BYOK AI runtime: key vault + OpenAI-compatible client + tool-calling agents
- [ ] Automation engine: trigger → condition → action interpreter
- [ ] Connectors: external Postgres/Neon, S3/R2, SMTP, webhook event forwarding
- [ ] More first-party apps: invoicing, tasks, helpdesk-lite
- [ ] Plugin SDK + CLI for external developers
- [ ] Marketplace (templates + plugins, rev-share)

## License

Apache 2.0 — see [LICENSE](LICENSE).
