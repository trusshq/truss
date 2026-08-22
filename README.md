# 🏗️ Truss

**The open-source, plugin-first business OS.**

🌐 **Live:** [truss-nine.vercel.app](https://truss-nine.vercel.app) · **Repo:** [github.com/trusshq/truss](https://github.com/trusshq/truss)

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

One command brings up the full stack — Postgres, kernel, and frontend:

```bash
cp .env.example .env     # then set strong secrets!
docker compose up -d --build
```

| Service | URL |
|---|---|
| UI | http://localhost:3000 (proxies `/api/*` to the kernel) |
| API + docs | http://localhost:8000 · http://localhost:8000/docs |
| Postgres | localhost:5432 |

Create a workspace at http://localhost:3000 and you're running. All ports, credentials, and secrets are configurable via `.env` (see `.env.example`).

## Tests & CI

Every push runs the full suite in GitHub Actions (`.github/workflows/ci.yml`): kernel smoke suites on a real Postgres + frontend production build + compose validation + Docker image builds (kernel image is booted against Postgres and must serve `/api/health`).

```bash
cd kernel
uv run python run_all_tests.py   # 471 checks across 16 suites
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

- [x] Phase 0 — kernel: tenancy, metadata layer, plugin runtime, event seam
- [x] Phase 1 — BYOK AI: encrypted key vault, OpenAI-compatible client, tool-calling agent loop
- [x] Phase 2 — Automations: declarative trigger → condition → action engine
- [x] Phase 3 — Connectors: webhook forwarding, external Postgres/Neon, outbox + retry
- [x] Phase 4 — App suite: CRM, Invoices, Tasks, Helpdesk as pure plugins
- [x] Phase 5 — Marketplace: community plugin catalog + one-click workspace templates
- [x] Workspace & access control: namespace, profiles, invites, owner/admin/member/viewer RBAC
- [x] Phase A — AI employees: hire/fire agents, budgets, permission roles, safety rails (history, trash, validation), adoption (CSV, activity feed, API keys, webhooks-out)
- [x] Phase B — Org: org chart, goals, approvals, notifications
- [x] Phase C — Autonomous orchestration: scheduled agents, task queues, review inbox, autopilot
- [x] Phase D — Intelligence: analytics engine, scorecards, timeline, insight queries
- [x] Phase E — Developer platform: typed TS SDK, manifest validation, API reference, dev portal
- [x] Phase F — Chat control surface: one chatbox to run the whole workspace (role-gated kernel tools), 10-section sidebar, deep theming (font, scale, motion, accent, radius, density)
- [x] Phase G — CRM first-party app: activities, pipeline kanban, App Home dashboard surfaces
- [x] Self-hosting: Docker Compose full stack + CI pipeline (images built & smoke-tested in CI)
- [ ] Hosted tier: managed Truss, billing, plugin publishing pipeline
- [ ] AI depth: natural-language schema builder, RAG over workspace data
- [ ] Sandboxing, SSO/SAML, mobile apps

## License

Apache 2.0 — see [LICENSE](LICENSE).
