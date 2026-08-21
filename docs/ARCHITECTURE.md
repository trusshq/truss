# Truss Architecture

## Design principles

1. **Kernel, not apps.** The kernel owns identity, tenancy, the metadata data layer,
   the plugin runtime, the event seam, and RBAC. Apps are plugins that prove the kernel.
2. **Declarative plugins only (v1).** A plugin is a JSON manifest interpreted by the
   kernel. No third-party code executes → no sandboxing, no review burden, no isolation
   risk. Code plugins (sandboxed) are a later phase.
3. **Metadata over migrations.** Business objects and fields are rows (`object_defs`,
   `field_defs`); records are JSONB rows keyed by object. Plugins materialize their
   objects per tenant on install (idempotent).
4. **BYO-everything.** Users bring their own AI keys/endpoints, their own databases,
   their own storage, their own analytics (via event forwarding). Truss owns the
   control plane; users supply the data plane.
5. **Modular monolith.** One deployable kernel with clean module boundaries. Split
   into services only when scaling demands it.

## Layers

```
┌────────────────────────────────────────────────────────┐
│  Next.js frontend (Vercel / self-host standalone)      │
│  shell · plugin-driven UI · plugin manager · events    │
├────────────────────────────────────────────────────────┤
│  Python kernel (FastAPI)                               │
│  ┌──────────┬───────────┬───────────┬───────────────┐  │
│  │ identity │ metadata  │ plugin    │ AI runtime    │  │
│  │ tenancy  │ objects/  │ registry  │ (BYOK, next   │  │
│  │ RBAC     │ fields    │ install/  │ phase)        │  │
│  │ (JWT)    │ (JSONB)   │ enable    │               │  │
│  ├──────────┼───────────┼───────────┼───────────────┤  │
│  │ light    │ webhooks  │ connector │ event bus     │  │
│  │ automation│ + cron   │ framework │ (in-proc +    │  │
│  │ (next)   │ (next)    │ (next)    │ durable log)  │  │
│  └──────────┴───────────┴───────────┴───────────────┘  │
├────────────────────────────────────────────────────────┤
│  Postgres (JSONB + RLS-ready) · Redis · S3/R2          │
└────────────────────────────────────────────────────────┘
```

## Data model

| Table | Purpose |
|---|---|
| `tenants` | Workspaces (slug-unique) |
| `users` | Accounts (email-unique, bcrypt hash) |
| `memberships` | user × tenant × role (owner/admin/member/viewer) |
| `object_defs` | Business objects per tenant (slug, icon, plugin_id) |
| `field_defs` | Typed fields per object (14 types incl. select/relation) |
| `records` | Rows of any object: `tenant_id + object_id + data JSONB` |
| `plugin_installs` | Per-tenant plugin state: version, enabled, settings |
| `event_log` | Durable event seam (type, actor, plugin, payload) |

### Multi-tenancy

Every query is scoped by `tenant_id` derived from the JWT (never from the client).
The JWT carries `sub` (user) + `tid` (tenant) + `role`; membership is re-verified
against the DB on every request. Next step: Postgres Row-Level Security as a
defense-in-depth layer.

### Validation

Records are validated against field defs on write: required fields, type coercion
(number/currency/boolean/multiselect), select-choice membership, unknown-field
rejection. This is what makes metadata-driven data safe.

## Plugin lifecycle

1. **Discovery** — at boot the registry scans `plugins_builtin/*/plugin.json` and
   `../plugins/*/plugin.json`, validating each against the Pydantic manifest schema.
2. **Install** — per tenant: materialize ObjectDefs/FieldDefs (idempotent), create a
   `plugin_installs` row, emit `plugin.installed`.
3. **Enable/disable** — flip the install row; UI/tools/automations gate on it. Data
   is never deleted on disable.
4. **Uninstall** (roadmap) — remove install row; optionally archive objects.

## Event seam

`bus.emit()` persists an `EventLog` row in the same transaction as the change, then
fans out to in-process subscribers (failures isolated). Event types today:
`tenant.created`, `object.created/deleted/field_added`, `record.created/updated/deleted`,
`plugin.installed/enabled/disabled`. Subscribers (automation engine, webhook
forwarding, AI context) register at startup.

## Security posture (current)

- bcrypt password hashing, HS256 JWT (24h expiry)
- RBAC: admin-only for schema/plugin changes; member for records; viewer read-only
- Tenant scoping enforced in every query via auth context
- Plugin permissions declared in manifests (surfaced at install; enforcement evolves)

## Phase status

- **Phase 0 — Kernel** ✅ multi-tenancy, auth/RBAC, metadata data layer, plugin
  runtime, event seam, CRM plugin, frontend shell
- **Phase 1 — BYOK AI** ✅ encrypted key vault, OpenAI-compatible client, agent
  loop executing plugin tools under user permissions
- **Phase 2 — Automations** ✅ declarative trigger→condition→action interpreter on
  the event bus, depth-guarded recursion, audited run history
- **Phase 3 — Connectors** ✅ webhook event forwarding (outbox + after-commit +
  HMAC signing, BYO-analytics), external Postgres/Neon read-only (test/introspect/
  query); s3 + smtp adapters stubbed
- **Phase 4 — More apps** ⏳ invoicing, tasks, helpdesk-lite (each a plugin.json)

## Connectors (Phase 3)

Tenant-scoped, admin-managed bridges to external systems. Config is encrypted
at rest (same Fernet vault as AI keys) and masked in all API responses.

**Webhook (event forwarding / BYO-analytics):**
- Outbox pattern: on every bus event, matching webhook connectors get a
  `webhook_deliveries` row in the SAME transaction as the event (atomic).
- Delivery happens via a `sync_session` `after_commit` hook (AsyncSession can't
  take ORM events directly) — never inside the write transaction.
- POSTs carry an `X-Truss-Signature` HMAC-SHA256 header (from the connector's
  `secret`) so receivers can verify authenticity.
- `events` filter: list of type prefixes (e.g. `["record."]`); empty = all.
- Point it at PostHog, a warehouse ingest, Zapier, or any HTTP endpoint.

**External Postgres / Neon (read-only):**
- Connections open with `default_transaction_read_only=on`; only SELECT
  statements pass (rejected up front + enforced server-side); queries are
  wrapped in `SELECT * FROM (...) LIMIT n` and timed out at 15s.
- Endpoints: `/test` (SELECT version()), `/tables` (information_schema
  introspection), `/query` (read-only SELECT).

**s3 / smtp:** type registry + config validation in place; adapters ship later.

## Automation engine (Phase 2)

The engine subscribes to the event bus as a wildcard handler. For every
`record.*` event it consults the tenant's ENABLED plugins, matches
`trigger + object + condition`, and executes the declared actions inside the
SAME database transaction as the triggering change (atomic: the automation's
effects commit or roll back with the original write).

Safety rails:
- **Depth guard**: events emitted by automations carry `depth+1` in the
  envelope (never persisted); at `MAX_DEPTH=3` the engine stops — self-triggering
  rules cannot loop forever.
- **Tenant scope**: only the emitting tenant's plugins are consulted.
- **Audit**: every firing writes an `automation_runs` row (success/error + detail).
- **Isolation**: one failing action marks the rule `error` but never breaks the
  emitter or the kernel.

Supported actions (v1): `emit_event`, `update_record`. Conditions: `field` +
`equals` / `not_equals` against the change payload.

## Known next steps (in order)

1. **More first-party apps** — invoicing, tasks, helpdesk-lite as plugin.json
   bundles proving the platform.
2. **Alembic migrations** — replace boot-time `create_all`.
3. **RLS policies** — defense-in-depth tenant isolation.
4. **s3 + smtp connector adapters** — type registry already in place.
