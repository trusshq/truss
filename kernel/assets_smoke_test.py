"""Phase AD smoke test: assets — CRUD, lifecycle, assignment, history.

Verifies:
- create asset (auto tag AST-0001, status available)
- list filters (status, category, assignee_id, unassigned)
- get/patch (retired assets locked)
- lifecycle: assign (available/maintenance only), return (assigned only),
  maintenance (available/assigned, clears assignee), retire, restore
  (retired/maintenance), 409 guards
- history audit trail records every action
- events emitted
- delete (admin)
- tenant isolation

Idempotent: fresh tenants per run.
"""
import json
import os
import time
import urllib.request
import urllib.error

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


print("== Phase AD: assets ==")
SUFFIX = str(int(time.time()))
email = f"phasead-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AD",
    "tenant_name": f"Phase AD {SUFFIX}", "tenant_slug": f"phasead-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")
s, me = call("GET", "/api/auth/me", token=TOK)
UID = me.get("user_id") or me.get("id")

print("== 1. create asset ==")
s, a = call("POST", "/api/assets", {
    "name": "MacBook Pro 16", "category": "Laptop", "description": "Dev machine",
    "cost_cents": 249900, "currency": "USD", "purchase_date": "2026-01-15",
    "location": "HQ",
}, token=TOK)
check("asset created 201", s == 201, f"{s} {a}")
AID = a.get("id")
check("tag AST-0001", a.get("tag") == "AST-0001", str(a.get("tag")))
check("status available", a.get("status") == "available", str(a.get("status")))
check("cost 249900", a.get("cost_cents") == 249900, str(a.get("cost_cents")))

print("== 2. second asset + list filters ==")
s, a2 = call("POST", "/api/assets", {"name": "Standing Desk", "category": "Furniture"}, token=TOK)
check("second asset AST-0002", a2.get("tag") == "AST-0002", str(a2.get("tag")))
s, res = call("GET", "/api/assets", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/assets?category=Laptop", token=TOK)
check("category filter Laptop", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/assets?status=available", token=TOK)
check("status filter available", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/assets?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))
s, res = call("GET", "/api/assets?unassigned=true", token=TOK)
check("unassigned filter all 2", res.get("total") == 2, str(res.get("total")))

print("== 3. assign ==")
s, asg = call("POST", f"/api/assets/{AID}/assign", {"assignee_id": UID}, token=TOK)
check("assign 200", s == 200, f"{s} {asg}")
check("status assigned", asg.get("status") == "assigned", str(asg.get("status")))
check("assignee set", asg.get("assignee_id") == UID, str(asg.get("assignee_id")))
s, res = call("GET", "/api/assets?unassigned=true", token=TOK)
check("unassigned now 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", f"/api/assets?assignee_id={UID}", token=TOK)
check("assignee filter finds 1", res.get("total") == 1, str(res.get("total")))
# can't re-assign an assigned asset
s, _ = call("POST", f"/api/assets/{AID}/assign", {"assignee_id": UID}, token=TOK)
check("re-assign 409", s == 409, str(s))
# assign requires assignee_id
s, _ = call("POST", f"/api/assets/{a2['id']}/assign", {}, token=TOK)
check("assign w/o id 400", s == 400, str(s))

print("== 4. return ==")
s, ret = call("POST", f"/api/assets/{AID}/return", {}, token=TOK)
check("return 200", s == 200, str(s))
check("status available", ret.get("status") == "available", str(ret.get("status")))
check("assignee cleared", ret.get("assignee_id") is None, str(ret.get("assignee_id")))
# can't return an available asset
s, _ = call("POST", f"/api/assets/{AID}/return", {}, token=TOK)
check("return available 409", s == 409, str(s))

print("== 5. maintenance ==")
s, mnt = call("POST", f"/api/assets/{AID}/maintenance", {"reason": "Screen crack"}, token=TOK)
check("maintenance 200", s == 200, str(s))
check("status maintenance", mnt.get("status") == "maintenance", str(mnt.get("status")))
# can't retire from maintenance? retire is allowed from any non-retired
s, _ = call("POST", f"/api/assets/{AID}/maintenance", {}, token=TOK)
check("re-maintenance 409", s == 409, str(s))

print("== 6. restore from maintenance ==")
s, rst = call("POST", f"/api/assets/{AID}/restore", {}, token=TOK)
check("restore 200", s == 200, str(s))
check("status available", rst.get("status") == "available", str(rst.get("status")))

print("== 7. retire + lock ==")
s, rtr = call("POST", f"/api/assets/{AID}/retire", {}, token=TOK)
check("retire 200", s == 200, str(s))
check("status retired", rtr.get("status") == "retired", str(rtr.get("status")))
# can't edit retired
s, _ = call("PATCH", f"/api/assets/{AID}", {"name": "New"}, token=TOK)
check("edit retired 409", s == 409, str(s))
# can't re-retire
s, _ = call("POST", f"/api/assets/{AID}/retire", {}, token=TOK)
check("re-retire 409", s == 409, str(s))
# can't assign retired
s, _ = call("POST", f"/api/assets/{AID}/assign", {"assignee_id": UID}, token=TOK)
check("assign retired 409", s == 409, str(s))
# restore retired
s, rst2 = call("POST", f"/api/assets/{AID}/restore", {}, token=TOK)
check("restore retired 200", s == 200, str(s))
check("status available again", rst2.get("status") == "available", str(rst2.get("status")))

print("== 8. patch ==")
s, upd = call("PATCH", f"/api/assets/{AID}", {"location": "Remote", "cost_cents": 200000}, token=TOK)
check("patch 200", s == 200, f"{s} {upd}")
check("location updated", upd.get("location") == "Remote", str(upd.get("location")))
check("cost updated", upd.get("cost_cents") == 200000, str(upd.get("cost_cents")))

print("== 9. history audit trail ==")
s, hist = call("GET", f"/api/assets/{AID}/history", token=TOK)
check("history listed", s == 200 and hist.get("total", 0) >= 7, f"{s} {hist.get('total')}")
actions = [h["action"] for h in hist.get("items", [])]
for act in ("created", "assigned", "returned", "maintenance", "restored", "retired"):
    check(f"history has {act}", act in actions, str(actions))

print("== 10. events + delete + isolation ==")
for ev in ("asset.created", "asset.assigned", "asset.returned", "asset.maintenance", "asset.retired", "asset.restored"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/assets/{a2['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/assets", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phasead2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AD2",
    "tenant_name": f"Phase AD2 {SUFFIX}", "tenant_slug": f"phasead2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/assets", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/assets/{AID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
