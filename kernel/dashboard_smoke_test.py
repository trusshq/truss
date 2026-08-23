"""Phase W smoke test: unified dashboard — aggregated KPIs across all modules.

Verifies:
- GET /api/dashboard returns all 17 KPI fields
- counts reflect seeded data across records, agents, projects, expenses,
  inventory, HR, calendar, time, forms, KB
- low-stock and pending-approval signals are correct
- tenant isolation (fresh tenant sees zeros)

Idempotent: fresh tenants per run.
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def call(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


print("== Phase W: dashboard ==")
SUFFIX = str(int(time.time()))
email = f"phasew-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase W",
    "tenant_name": f"Phase W {SUFFIX}", "tenant_slug": f"phasew-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. empty dashboard shape ==")
s, d = call("GET", "/api/dashboard", token=TOK)
check("dashboard 200", s == 200, str(s))
EXPECTED_KEYS = {
    "objects_total", "records_total", "agents_total", "agents_active",
    "projects_total", "projects_active", "expenses_pending", "expenses_submitted",
    "expenses_approved_cents", "products_total", "products_low_stock",
    "employees_total", "leave_pending", "upcoming_events_7d", "time_minutes_7d",
    "forms_total", "kb_published",
}
check("all 17 keys present", EXPECTED_KEYS.issubset(d.keys()), str(sorted(EXPECTED_KEYS - set(d.keys()))))
check("fresh tenant zeros", all(d[k] == 0 for k in EXPECTED_KEYS), str({k: d[k] for k in EXPECTED_KEYS if d[k] != 0}))

print("== 2. seed data across modules ==")
# object + records
s, obj = call("POST", "/api/objects", {"name": "Widget", "slug": "widget", "fields": [{"slug": "name", "name": "Name", "type": "text"}]}, token=TOK)
check("object created", s in (200, 201), f"{s} {obj}")
for i in range(3):
    s, _ = call("POST", "/api/records/widget", {"data": {"name": f"W{i}"}}, token=TOK)
    assert s in (200, 201), f"seed record failed: {s}"
# agent
s, ag = call("POST", "/api/agents", {"name": "Dana", "role": "ops"}, token=TOK)
check("agent created", s in (200, 201), f"{s} {ag}")
# project
s, pr = call("POST", "/api/projects", {"name": "Alpha", "status": "active", "budget_cents": 100000}, token=TOK)
check("project created", s == 201, f"{s} {pr}")
# expenses: one draft, one submitted+approved
s, ex1 = call("POST", "/api/expenses", {"title": "Draft", "category": "Travel", "amount_cents": 5000}, token=TOK)
check("expense draft", s == 201, f"{s} {ex1}")
s, ex2 = call("POST", "/api/expenses", {"title": "Approved", "category": "Travel", "amount_cents": 7000}, token=TOK)
call("POST", f"/api/expenses/{ex2['id']}/submit", {}, token=TOK)
s, _ = call("POST", f"/api/expenses/{ex2['id']}/approve", {}, token=TOK)
check("expense approved", s == 200, str(s))
# inventory: one normal, one low
call("POST", "/api/inventory/products", {"name": "A", "sku": "A1", "quantity": 50, "reorder_point": 5}, token=TOK)
call("POST", "/api/inventory/products", {"name": "B", "sku": "B1", "quantity": 2, "reorder_point": 10}, token=TOK)
# HR: employee + pending leave
s, emp = call("POST", "/api/hr/employees", {"name": "Eve", "email": f"eve-{SUFFIX}@x.com"}, token=TOK)
check("employee created", s == 201, f"{s} {emp}")
call("POST", "/api/hr/leave", {"employee_id": emp["id"], "leave_type": "vacation",
                               "start_date": "2026-09-01", "end_date": "2026-09-03"}, token=TOK)
# calendar: one event tomorrow
NOW = datetime.now(timezone.utc)
call("POST", "/api/calendar", {"title": "Standup", "starts_at": (NOW + timedelta(hours=20)).isoformat()}, token=TOK)
# time: 90 minutes logged now
call("POST", "/api/time", {"description": "work", "started_at": (NOW - timedelta(minutes=90)).isoformat(),
                           "stopped_at": NOW.isoformat()}, token=TOK)
# form
call("POST", "/api/forms", {"name": "Intake", "slug": f"intake-{SUFFIX}", "object": "widget", "fields": ["name"]}, token=TOK)
# KB published article
s, kb = call("POST", "/api/kb", {"title": "Guide", "slug": f"guide-{SUFFIX}", "body": "# hi"}, token=TOK)
call("POST", f"/api/kb/{kb['id']}/publish", {}, token=TOK)

print("== 3. aggregated dashboard reflects seeded data ==")
s, d = call("GET", "/api/dashboard", token=TOK)
check("dashboard 200 again", s == 200, str(s))
check("objects_total = 1", d.get("objects_total") == 1, str(d.get("objects_total")))
check("records_total = 3", d.get("records_total") == 3, str(d.get("records_total")))
check("agents_total = 1", d.get("agents_total") == 1, str(d.get("agents_total")))
check("agents_active = 1", d.get("agents_active") == 1, str(d.get("agents_active")))
check("projects_total = 1", d.get("projects_total") == 1, str(d.get("projects_total")))
check("projects_active = 1", d.get("projects_active") == 1, str(d.get("projects_active")))
check("expenses_pending = 1 (draft)", d.get("expenses_pending") == 1, str(d.get("expenses_pending")))
check("expenses_submitted = 0", d.get("expenses_submitted") == 0, str(d.get("expenses_submitted")))
check("expenses_approved_cents = 7000", d.get("expenses_approved_cents") == 7000, str(d.get("expenses_approved_cents")))
check("products_total = 2", d.get("products_total") == 2, str(d.get("products_total")))
check("products_low_stock = 1", d.get("products_low_stock") == 1, str(d.get("products_low_stock")))
check("employees_total = 1", d.get("employees_total") == 1, str(d.get("employees_total")))
check("leave_pending = 1", d.get("leave_pending") == 1, str(d.get("leave_pending")))
check("upcoming_events_7d = 1", d.get("upcoming_events_7d") == 1, str(d.get("upcoming_events_7d")))
check("time_minutes_7d = 90", d.get("time_minutes_7d") == 90, str(d.get("time_minutes_7d")))
check("forms_total = 1", d.get("forms_total") == 1, str(d.get("forms_total")))
check("kb_published = 1", d.get("kb_published") == 1, str(d.get("kb_published")))

print("== 4. tenant isolation ==")
email2 = f"phasew2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase W2",
    "tenant_name": f"Phase W2 {SUFFIX}", "tenant_slug": f"phasew2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, d2 = call("GET", "/api/dashboard", token=TOK2)
check("other tenant zeros", s == 200 and all(d2[k] == 0 for k in EXPECTED_KEYS),
      str({k: d2[k] for k in EXPECTED_KEYS if d2.get(k) != 0}))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
