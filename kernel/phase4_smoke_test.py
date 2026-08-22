"""Phase 4 smoke test: new first-party apps + regression on the bug fixes."""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


print("== 0. login ==")
s, b = call("POST", "/api/auth/login", {"email": "owner@acme-demo.dev", "password": "password123"}, auth=False)
check("login ok", s == 200 and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access_token")

print("== 1. all 4 plugins discovered ==")
s, cat = call("GET", "/api/plugins/catalog")
ids = {p["id"] for p in cat} if isinstance(cat, list) else set()
# subset check: marketplace-installed community plugins also appear in the
# catalog (by design), so assert the 4 builtins are present, not an exact set
check("4 builtin plugins in catalog", {"truss-crm", "truss-invoices", "truss-tasks", "truss-helpdesk"} <= ids, str(ids))

print("== 2. install the three new apps ==")
for pid in ["truss-invoices", "truss-tasks", "truss-helpdesk"]:
    s, b = call("POST", "/api/plugins/install", {"plugin_id": pid})
    check(f"installed {pid}", s in (200, 201), f"{s} {b}")

print("== 3. objects materialized ==")
s, objs = call("GET", "/api/objects")
slugs = {o["slug"] for o in objs} if isinstance(objs, list) else set()
check("invoice object exists", "invoice" in slugs, str(slugs))
check("task object exists", "task" in slugs, str(slugs))
check("ticket object exists", "ticket" in slugs, str(slugs))

print("== 4. create records in each new app ==")
s, inv = call("POST", "/api/records/invoice", {
    "data": {"number": "INV-001", "customer": "Acme Corp", "amount": 1500, "status": "Draft"}
})
check("invoice created", s == 201, f"{s} {inv}")

s, task = call("POST", "/api/records/task", {
    "data": {"title": "Ship Phase 4", "status": "In Progress", "priority": "High", "tags": ["feature", "urgent"]}
})
check("task created (with multiselect tags)", s == 201, f"{s} {task}")

s, tick = call("POST", "/api/records/ticket", {
    "data": {"subject": "Cannot login", "requester_email": "user@example.com", "status": "Open", "priority": "High", "category": "Technical"}
})
check("ticket created", s == 201, f"{s} {tick}")

print("== 5. BUG FIX: multiselect choice validation ==")
s, b = call("POST", "/api/records/task", {
    "data": {"title": "Bad tags", "tags": ["not-a-real-tag"]}
})
check("invalid multiselect value -> 422", s == 422, f"{s} {b}")

print("== 6. BUG FIX: pagination offset works ==")
# create 3 more invoices so we have 4 total
for i in range(2, 5):
    call("POST", "/api/records/invoice", {
        "data": {"number": f"INV-00{i}", "customer": f"Customer {i}", "amount": 100 * i, "status": "Sent"}
    })
s, page1 = call("GET", "/api/records/invoice?limit=2&offset=0")
s2, page2 = call("GET", "/api/records/invoice?limit=2&offset=2")
check("page1 has 2 items", s == 200 and len(page1.get("items", [])) == 2, f"{s} {len(page1.get('items', []))}")
check("page2 has 2 items", s2 == 200 and len(page2.get("items", [])) == 2, f"{s2} {len(page2.get('items', []))}")
p1_ids = {i["id"] for i in page1.get("items", [])}
p2_ids = {i["id"] for i in page2.get("items", [])}
check("pages don't overlap", p1_ids.isdisjoint(p2_ids), f"overlap: {p1_ids & p2_ids}")
check("total reported correctly", page1.get("total", 0) >= 4, str(page1.get("total")))

print("== 7. automations from new apps fire ==")
s, _ = call("PATCH", f"/api/records/invoice/{inv['id']}", {"data": {"status": "Paid"}})
s, ev = call("GET", "/api/events?limit=100")
items = ev if isinstance(ev, list) else ev.get("items", [])
paid_ev = [e for e in items if e.get("type") == "billing.invoice_paid"]
check("billing.invoice_paid emitted", len(paid_ev) >= 1, f"types: {[e.get('type') for e in items[:8]]}")

s, _ = call("PATCH", f"/api/records/task/{task['id']}", {"data": {"status": "Done"}})
s, ev2 = call("GET", "/api/events?limit=100")
items2 = ev2 if isinstance(ev2, list) else ev2.get("items", [])
done_ev = [e for e in items2 if e.get("type") == "task.completed"]
check("task.completed emitted", len(done_ev) >= 1, f"types: {[e.get('type') for e in items2[:8]]}")

print("== 8. automations list includes new rules ==")
s, rules = call("GET", "/api/automations")
rule_slugs = {r["slug"] for r in rules} if isinstance(rules, list) else set()
check("invoice_paid_event declared", "invoice_paid_event" in rule_slugs, str(rule_slugs))
check("task_completed_event declared", "task_completed_event" in rule_slugs, str(rule_slugs))
check("ticket_opened_event declared", "ticket_opened_event" in rule_slugs, str(rule_slugs))

print("== 9. BUG FIX: connector rename collision ==")
s, c1 = call("POST", "/api/connectors", {"name": "rename-a", "type": "webhook", "config": {"url": "http://127.0.0.1:9998/a"}})
s, c2 = call("POST", "/api/connectors", {"name": "rename-b", "type": "webhook", "config": {"url": "http://127.0.0.1:9998/b"}})
if s == 409:
    # leftover from prior run; fetch existing
    s2, conns = call("GET", "/api/connectors")
    c1 = next((c for c in conns if c["name"] == "rename-a"), c1)
    c2 = next((c for c in conns if c["name"] == "rename-b"), c2)
s, b = call("PATCH", f"/api/connectors/{c2['id']}", {"name": "rename-a", "type": "webhook", "config": {"url": "http://127.0.0.1:9998/b"}})
check("rename to existing name -> 409", s == 409, f"{s} {b}")
# cleanup
call("DELETE", f"/api/connectors/{c1['id']}")
call("DELETE", f"/api/connectors/{c2['id']}")

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
