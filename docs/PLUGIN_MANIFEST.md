# Truss Plugin Manifest (`plugin.json`)

A Truss plugin is a **folder containing a `plugin.json`** — a declarative contract the
kernel interprets. In v1 no plugin code executes; you declare objects, AI tools,
automations, and UI surfaces, and the kernel's runtime executes them safely.

Drop your plugin folder into `plugins/<your-plugin>/plugin.json` (next to the kernel)
and restart the kernel — it appears in the catalog, ready to install per tenant.

## Full example

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "version": "0.1.0",
  "description": "What it does, in one sentence.",
  "author": "you",
  "icon": "🧩",
  "permissions": ["objects:write", "records:write", "events:emit"],

  "objects": [
    {
      "slug": "invoice",
      "name": "Invoice",
      "name_plural": "Invoices",
      "description": "Bills you send to customers",
      "icon": "🧾",
      "fields": [
        { "slug": "number", "name": "Number", "type": "text", "required": true, "position": 0 },
        { "slug": "amount", "name": "Amount", "type": "currency", "required": true, "position": 1 },
        { "slug": "status", "name": "Status", "type": "select", "position": 2,
          "options": { "choices": ["Draft", "Sent", "Paid", "Void"] } },
        { "slug": "issued_at", "name": "Issued", "type": "date", "position": 3 },
        { "slug": "notes", "name": "Notes", "type": "textarea", "position": 4 }
      ]
    }
  ],

  "tools": [
    {
      "slug": "create_invoice",
      "name": "Create Invoice",
      "description": "Create a new invoice",
      "action": "create_record",
      "object": "invoice",
      "params": [
        { "name": "number", "type": "string", "required": true },
        { "name": "amount", "type": "number", "required": true }
      ]
    }
  ],

  "automations": [
    {
      "slug": "invoice_paid_event",
      "name": "Emit event when invoice is paid",
      "trigger": "record.updated",
      "object": "invoice",
      "condition": { "field": "status", "equals": "Paid" },
      "actions": [{ "action": "emit_event", "type": "billing.invoice_paid" }]
    }
  ],

  "ui": [
    { "slug": "invoices-table", "label": "Invoices", "icon": "🧾", "view": "table", "object": "invoice" }
  ]
}
```

## Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | ✅ | Globally unique, lowercase, hyphenated (`my-plugin`) |
| `name` | string | ✅ | Display name |
| `version` | string | — | Semver, default `0.1.0` |
| `description` | string | — | Shown in the plugin catalog |
| `author` | string | — | |
| `icon` | string | — | Single emoji |
| `permissions` | string[] | — | Declared requests, surfaced to the admin at install |
| `objects` | ObjectSpec[] | — | Business objects to materialize per tenant |
| `tools` | ToolSpec[] | — | AI-agent-callable capabilities |
| `automations` | AutomationSpec[] | — | Declarative trigger→action rules |
| `ui` | UISurface[] | — | Sidebar entries / views |

## Field types

`text` · `textarea` · `number` · `currency` · `boolean` · `date` · `datetime` ·
`email` · `phone` · `url` · `select` · `multiselect` · `relation` · `user`

- `select` / `multiselect`: provide `options.choices` (string array).
- `relation`: provide `options.related_object` (slug of another object).

## Tools (AI capabilities)

Each tool maps to a kernel `action` the agent may invoke **under the invoking user's
permissions**:

| action | meaning |
|---|---|
| `create_record` | create a record in `object` |
| `update_record` | patch a record (needs `record_id` param) |
| `query_records` | list/search records in `object` |
| `send_webhook` | POST to a tenant-configured URL (connectors phase) |

`params` describe arguments for the model (name, type, description, required).

## Automations

- `trigger`: `record.created` | `record.updated` | `record.deleted` (more later)
- `object`: scope to one object slug, or omit for all
- `condition`: simple equality guard, e.g. `{ "field": "status", "equals": "Paid" }`
- `actions`: list of `{ "action": ..., ... }` — currently `emit_event` (interpreter
  expands in the automation phase)

## UI surfaces

| view | renders |
|---|---|
| `table` | generic list/create/edit view over `object` |
| `kanban` | board grouped by `config.group_by` field (roadmap) |
| `dashboard` | overview card (roadmap) |

## Rules & limits (v1)

1. Object and field slugs must be unique **per tenant**; plugin objects are namespaced
   by `plugin_id` so two plugins can't collide silently.
2. Installing is idempotent — reinstalling never duplicates objects or fields.
3. Disabling hides the plugin's UI/tools/automations but **never deletes data**.
4. Builtin plugin objects cannot be deleted via the objects API (disable the plugin).
5. Manifests are validated at discovery; a broken manifest is skipped with a log line,
   never crashes the kernel.
