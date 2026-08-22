"""Truss Marketplace — community plugin catalog + workspace templates.

The catalog is a curated, bundled registry of community-authored plugin
manifests. Installing one materializes its plugin.json into the external
plugins directory and runs it through the standard plugin registry —
community plugins are first-class citizens, no special runtime path.

Templates are starter packs: a set of plugins plus seed records, so a new
workspace goes from empty to useful in one click.
"""
from __future__ import annotations

# ---------------- community plugin catalog ----------------

# Each entry is a full, valid PluginManifest plus marketplace metadata.
COMMUNITY_PLUGINS: list[dict] = [
    {
        "category": "Operations",
        "downloads": 4820,
        "rating": 4.8,
        "manifest": {
            "id": "community-inventory",
            "name": "Inventory",
            "version": "0.3.1",
            "description": "Products, stock levels, and reorder tracking for small warehouses and e-commerce ops.",
            "author": "mika.dev",
            "icon": "📦",
            "permissions": ["objects:write", "records:write", "events:emit"],
            "objects": [
                {
                    "slug": "product",
                    "name": "Product",
                    "name_plural": "Products",
                    "description": "Items you stock and sell",
                    "icon": "📦",
                    "fields": [
                        {"slug": "sku", "name": "SKU", "type": "text", "required": True, "position": 0},
                        {"slug": "name", "name": "Name", "type": "text", "required": True, "position": 1},
                        {"slug": "stock", "name": "Stock", "type": "number", "position": 2},
                        {"slug": "reorder_point", "name": "Reorder Point", "type": "number", "position": 3},
                        {"slug": "unit_cost", "name": "Unit Cost", "type": "currency", "position": 4},
                        {"slug": "status", "name": "Status", "type": "select", "position": 5,
                         "options": {"choices": ["Active", "Low Stock", "Out of Stock", "Discontinued"]}},
                    ],
                },
                {
                    "slug": "stock_movement",
                    "name": "Stock Movement",
                    "name_plural": "Stock Movements",
                    "description": "Inbound and outbound stock events",
                    "icon": "🔁",
                    "fields": [
                        {"slug": "product_sku", "name": "Product SKU", "type": "text", "required": True, "position": 0},
                        {"slug": "direction", "name": "Direction", "type": "select", "required": True, "position": 1,
                         "options": {"choices": ["In", "Out", "Adjustment"]}},
                        {"slug": "quantity", "name": "Quantity", "type": "number", "required": True, "position": 2},
                        {"slug": "reason", "name": "Reason", "type": "text", "position": 3},
                        {"slug": "movement_date", "name": "Date", "type": "date", "position": 4},
                    ],
                },
            ],
            "tools": [
                {
                    "slug": "create_product",
                    "name": "Create Product",
                    "description": "Add a product to inventory",
                    "action": "create_record",
                    "object": "product",
                    "params": [
                        {"name": "sku", "type": "string", "description": "SKU code", "required": True},
                        {"name": "name", "type": "string", "description": "Product name", "required": True},
                        {"name": "stock", "type": "number", "description": "Initial stock"},
                    ],
                },
                {
                    "slug": "search_products",
                    "name": "Search Products",
                    "description": "Search inventory by text",
                    "action": "query_records",
                    "object": "product",
                    "params": [{"name": "search", "type": "string", "description": "Search text"}],
                },
            ],
            "automations": [
                {
                    "slug": "low_stock_event",
                    "name": "Emit event when product goes low stock",
                    "trigger": "record.updated",
                    "object": "product",
                    "condition": {"field": "status", "equals": "Low Stock"},
                    "actions": [{"action": "emit_event", "type": "inventory.low_stock"}],
                }
            ],
            "ui": [
                {"slug": "products-table", "label": "Products", "icon": "📦", "view": "table", "object": "product"},
                {"slug": "inventory-board", "label": "Stock Board", "icon": "🗂️", "view": "kanban", "object": "product",
                 "config": {"group_by": "status"}},
                {"slug": "movements-table", "label": "Movements", "icon": "🔁", "view": "table", "object": "stock_movement"},
            ],
        },
    },
    {
        "category": "HR",
        "downloads": 3110,
        "rating": 4.6,
        "manifest": {
            "id": "community-hiring",
            "name": "Hiring Pipeline",
            "version": "0.2.0",
            "description": "Applicant tracking: roles, candidates, and interview stages in a kanban pipeline.",
            "author": "talentlabs",
            "icon": "🧑‍💼",
            "permissions": ["objects:write", "records:write", "events:emit"],
            "objects": [
                {
                    "slug": "job_role",
                    "name": "Role",
                    "name_plural": "Roles",
                    "description": "Open positions",
                    "icon": "🪧",
                    "fields": [
                        {"slug": "title", "name": "Title", "type": "text", "required": True, "position": 0},
                        {"slug": "department", "name": "Department", "type": "select", "position": 1,
                         "options": {"choices": ["Engineering", "Design", "Sales", "Marketing", "Operations", "Other"]}},
                        {"slug": "status", "name": "Status", "type": "select", "position": 2,
                         "options": {"choices": ["Open", "On Hold", "Filled", "Cancelled"]}},
                        {"slug": "salary_range", "name": "Salary Range", "type": "text", "position": 3},
                    ],
                },
                {
                    "slug": "candidate",
                    "name": "Candidate",
                    "name_plural": "Candidates",
                    "description": "Applicants in your pipeline",
                    "icon": "🧑‍💼",
                    "fields": [
                        {"slug": "name", "name": "Name", "type": "text", "required": True, "position": 0},
                        {"slug": "email", "name": "Email", "type": "email", "position": 1},
                        {"slug": "role", "name": "Role", "type": "text", "required": True, "position": 2},
                        {"slug": "stage", "name": "Stage", "type": "select", "required": True, "position": 3,
                         "options": {"choices": ["Applied", "Screening", "Interview", "Offer", "Hired", "Rejected"]}},
                        {"slug": "source", "name": "Source", "type": "select", "position": 4,
                         "options": {"choices": ["Job Board", "Referral", "LinkedIn", "Agency", "Other"]}},
                        {"slug": "notes", "name": "Notes", "type": "textarea", "position": 5},
                    ],
                },
            ],
            "tools": [
                {
                    "slug": "create_candidate",
                    "name": "Add Candidate",
                    "description": "Add a candidate to the hiring pipeline",
                    "action": "create_record",
                    "object": "candidate",
                    "params": [
                        {"name": "name", "type": "string", "description": "Candidate name", "required": True},
                        {"name": "role", "type": "string", "description": "Role applying for", "required": True},
                        {"name": "email", "type": "string", "description": "Candidate email"},
                    ],
                },
                {
                    "slug": "move_candidate_stage",
                    "name": "Move Candidate Stage",
                    "description": "Advance a candidate through the pipeline",
                    "action": "update_record",
                    "object": "candidate",
                    "params": [
                        {"name": "record_id", "type": "string", "description": "Candidate id", "required": True},
                        {"name": "stage", "type": "string", "description": "New stage", "required": True},
                    ],
                },
            ],
            "automations": [],
            "ui": [
                {"slug": "roles-table", "label": "Roles", "icon": "🪧", "view": "table", "object": "job_role"},
                {"slug": "candidates-board", "label": "Candidates", "icon": "🧑‍💼", "view": "kanban", "object": "candidate",
                 "config": {"group_by": "stage"}},
            ],
        },
    },
    {
        "category": "Strategy",
        "downloads": 2540,
        "rating": 4.7,
        "manifest": {
            "id": "community-okrs",
            "name": "OKRs",
            "version": "0.1.4",
            "description": "Objectives and key results with quarterly tracking and confidence scoring.",
            "author": "northstar",
            "icon": "🎯",
            "permissions": ["objects:write", "records:write", "events:emit"],
            "objects": [
                {
                    "slug": "objective",
                    "name": "Objective",
                    "name_plural": "Objectives",
                    "description": "What you want to achieve this quarter",
                    "icon": "🎯",
                    "fields": [
                        {"slug": "title", "name": "Objective", "type": "text", "required": True, "position": 0},
                        {"slug": "quarter", "name": "Quarter", "type": "select", "required": True, "position": 1,
                         "options": {"choices": ["Q1", "Q2", "Q3", "Q4"]}},
                        {"slug": "owner", "name": "Owner", "type": "text", "position": 2},
                        {"slug": "status", "name": "Status", "type": "select", "position": 3,
                         "options": {"choices": ["On Track", "At Risk", "Behind", "Done"]}},
                    ],
                },
                {
                    "slug": "key_result",
                    "name": "Key Result",
                    "name_plural": "Key Results",
                    "description": "Measurable outcomes under an objective",
                    "icon": "📈",
                    "fields": [
                        {"slug": "title", "name": "Key Result", "type": "text", "required": True, "position": 0},
                        {"slug": "objective", "name": "Objective", "type": "text", "required": True, "position": 1},
                        {"slug": "target", "name": "Target", "type": "number", "position": 2},
                        {"slug": "current", "name": "Current", "type": "number", "position": 3},
                        {"slug": "confidence", "name": "Confidence", "type": "select", "position": 4,
                         "options": {"choices": ["High", "Medium", "Low"]}},
                    ],
                },
            ],
            "tools": [
                {
                    "slug": "create_objective",
                    "name": "Create Objective",
                    "description": "Add a quarterly objective",
                    "action": "create_record",
                    "object": "objective",
                    "params": [
                        {"name": "title", "type": "string", "description": "Objective title", "required": True},
                        {"name": "quarter", "type": "string", "description": "Q1-Q4", "required": True},
                    ],
                },
            ],
            "automations": [],
            "ui": [
                {"slug": "objectives-board", "label": "Objectives", "icon": "🎯", "view": "kanban", "object": "objective",
                 "config": {"group_by": "status"}},
                {"slug": "key-results-table", "label": "Key Results", "icon": "📈", "view": "table", "object": "key_result"},
            ],
        },
    },
    {
        "category": "Billing",
        "downloads": 1980,
        "rating": 4.5,
        "manifest": {
            "id": "community-subscriptions",
            "name": "Subscriptions",
            "version": "0.2.2",
            "description": "Track subscribers, plans, MRR, and churn in one place.",
            "author": "billflow",
            "icon": "🔁",
            "permissions": ["objects:write", "records:write", "events:emit"],
            "objects": [
                {
                    "slug": "plan",
                    "name": "Plan",
                    "name_plural": "Plans",
                    "description": "Pricing plans you offer",
                    "icon": "🏷️",
                    "fields": [
                        {"slug": "name", "name": "Plan Name", "type": "text", "required": True, "position": 0},
                        {"slug": "price", "name": "Monthly Price", "type": "currency", "required": True, "position": 1},
                        {"slug": "billing", "name": "Billing", "type": "select", "position": 2,
                         "options": {"choices": ["Monthly", "Annual"]}},
                        {"slug": "features", "name": "Features", "type": "textarea", "position": 3},
                    ],
                },
                {
                    "slug": "subscriber",
                    "name": "Subscriber",
                    "name_plural": "Subscribers",
                    "description": "Customers on a plan",
                    "icon": "🙋",
                    "fields": [
                        {"slug": "name", "name": "Customer", "type": "text", "required": True, "position": 0},
                        {"slug": "email", "name": "Email", "type": "email", "position": 1},
                        {"slug": "plan", "name": "Plan", "type": "text", "required": True, "position": 2},
                        {"slug": "mrr", "name": "MRR", "type": "currency", "position": 3},
                        {"slug": "status", "name": "Status", "type": "select", "position": 4,
                         "options": {"choices": ["Active", "Trialing", "Past Due", "Cancelled"]}},
                        {"slug": "start_date", "name": "Start Date", "type": "date", "position": 5},
                    ],
                },
            ],
            "tools": [
                {
                    "slug": "create_subscriber",
                    "name": "Add Subscriber",
                    "description": "Add a subscriber on a plan",
                    "action": "create_record",
                    "object": "subscriber",
                    "params": [
                        {"name": "name", "type": "string", "description": "Customer name", "required": True},
                        {"name": "plan", "type": "string", "description": "Plan name", "required": True},
                        {"name": "mrr", "type": "number", "description": "Monthly revenue"},
                    ],
                },
            ],
            "automations": [
                {
                    "slug": "churn_event",
                    "name": "Emit event when subscriber cancels",
                    "trigger": "record.updated",
                    "object": "subscriber",
                    "condition": {"field": "status", "equals": "Cancelled"},
                    "actions": [{"action": "emit_event", "type": "billing.subscriber_churned"}],
                }
            ],
            "ui": [
                {"slug": "plans-table", "label": "Plans", "icon": "🏷️", "view": "table", "object": "plan"},
                {"slug": "subscribers-board", "label": "Subscribers", "icon": "🙋", "view": "kanban", "object": "subscriber",
                 "config": {"group_by": "status"}},
            ],
        },
    },
]


def catalog_entry(p: dict) -> dict:
    """Marketplace-facing shape: metadata + manifest summary (no full manifest)."""
    m = p["manifest"]
    return {
        "id": m["id"],
        "name": m["name"],
        "version": m["version"],
        "description": m["description"],
        "author": m["author"],
        "icon": m["icon"],
        "category": p["category"],
        "downloads": p["downloads"],
        "rating": p["rating"],
        "objects": [o["name_plural"] or o["name"] for o in m.get("objects", [])],
        "permissions": m.get("permissions", []),
    }


def get_manifest(plugin_id: str) -> dict | None:
    for p in COMMUNITY_PLUGINS:
        if p["manifest"]["id"] == plugin_id:
            return p["manifest"]
    return None


# ---------------- workspace templates ----------------

TEMPLATES: list[dict] = [
    {
        "id": "startup-os",
        "name": "Startup OS",
        "icon": "🚀",
        "description": "The full stack for an early-stage startup: CRM pipeline, task board, and invoicing — pre-seeded with sample data so every view has something in it.",
        "plugins": ["truss-crm", "truss-tasks", "truss-invoices"],
        "seeds": [
            {"object": "company", "data": {"name": "Northwind Labs", "domain": "https://northwind.example", "industry": "Software", "employees": 12}},
            {"object": "company", "data": {"name": "Acme Retail", "domain": "https://acme.example", "industry": "E-commerce", "employees": 45}},
            {"object": "lead", "data": {"name": "Priya Sharma", "email": "priya@northwind.example", "source": "Website", "status": "New"}},
            {"object": "lead", "data": {"name": "Jonas Weber", "email": "jonas@acme.example", "source": "Referral", "status": "Contacted"}},
            {"object": "deal", "data": {"name": "Northwind — Annual Plan", "stage": "Proposal", "amount": 24000}},
            {"object": "deal", "data": {"name": "Acme — Pilot", "stage": "Discovery", "amount": 6000}},
            {"object": "task", "data": {"title": "Send Northwind proposal", "status": "In Progress", "priority": "High", "tags": ["follow-up"]}},
            {"object": "task", "data": {"title": "Set up onboarding call", "status": "To Do", "priority": "Medium"}},
            {"object": "invoice", "data": {"number": "INV-001", "customer": "Northwind Labs", "amount": 12000, "status": "Sent"}},
            {"object": "invoice", "data": {"number": "INV-002", "customer": "Acme Retail", "amount": 3000, "status": "Draft"}},
        ],
    },
    {
        "id": "sales-team",
        "name": "Sales Team",
        "icon": "🤝",
        "description": "A ready-made sales pipeline: companies, leads, and a deal board with sample opportunities across every stage.",
        "plugins": ["truss-crm"],
        "seeds": [
            {"object": "company", "data": {"name": "Globex Corp", "industry": "Manufacturing", "employees": 220}},
            {"object": "company", "data": {"name": "Initech", "industry": "Software", "employees": 80}},
            {"object": "lead", "data": {"name": "Dana Cole", "email": "dana@globex.example", "source": "Event", "status": "Qualified"}},
            {"object": "deal", "data": {"name": "Globex — Enterprise", "stage": "Negotiation", "amount": 96000}},
            {"object": "deal", "data": {"name": "Initech — Team Plan", "stage": "Proposal", "amount": 18000}},
            {"object": "deal", "data": {"name": "Initech — Expansion", "stage": "Won", "amount": 9000}},
        ],
    },
    {
        "id": "support-center",
        "name": "Support Center",
        "icon": "🎧",
        "description": "Helpdesk plus a task board: ticket queue by status, priorities, and internal follow-ups — seeded with a realistic queue.",
        "plugins": ["truss-helpdesk", "truss-tasks"],
        "seeds": [
            {"object": "ticket", "data": {"subject": "Cannot reset password", "requester_email": "sam@customer.example", "status": "Open", "priority": "High", "category": "Account"}},
            {"object": "ticket", "data": {"subject": "Invoice shows wrong amount", "requester_email": "billing@customer.example", "status": "Pending", "priority": "Normal", "category": "Billing"}},
            {"object": "ticket", "data": {"subject": "Feature request: dark mode", "requester_email": "night@owl.example", "status": "Open", "priority": "Low", "category": "Feature Request"}},
            {"object": "task", "data": {"title": "Write password-reset runbook", "status": "To Do", "priority": "Medium", "tags": ["docs"]}},
            {"object": "task", "data": {"title": "Escalate billing ticket", "status": "In Progress", "priority": "Urgent", "tags": ["urgent"]}},
        ],
    },
    {
        "id": "agency-ops",
        "name": "Agency Ops",
        "icon": "🎨",
        "description": "Run client work end to end: CRM for clients, tasks as project deliverables, and invoices for billing — with a sample client engagement.",
        "plugins": ["truss-crm", "truss-tasks", "truss-invoices"],
        "seeds": [
            {"object": "company", "data": {"name": "Bright Studio Client Co", "industry": "Services", "employees": 30}},
            {"object": "deal", "data": {"name": "Website Redesign", "stage": "Won", "amount": 15000}},
            {"object": "task", "data": {"title": "Wireframes — v1", "status": "Done", "priority": "High", "tags": ["feature"]}},
            {"object": "task", "data": {"title": "Design system handoff", "status": "In Progress", "priority": "High"}},
            {"object": "task", "data": {"title": "Build landing page", "status": "To Do", "priority": "Medium"}},
            {"object": "invoice", "data": {"number": "AG-101", "customer": "Bright Studio Client Co", "amount": 7500, "status": "Paid"}},
            {"object": "invoice", "data": {"number": "AG-102", "customer": "Bright Studio Client Co", "amount": 7500, "status": "Sent"}},
        ],
    },
]


def template_summary(t: dict) -> dict:
    return {
        "id": t["id"],
        "name": t["name"],
        "icon": t["icon"],
        "description": t["description"],
        "plugins": t["plugins"],
        "record_count": len(t["seeds"]),
    }


def get_template(template_id: str) -> dict | None:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    return None
