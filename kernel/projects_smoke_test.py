"""Phase T smoke test: projects & milestones — CRUD, budget rollups, project links.

Verifies:
- create project (auto slug, collision 409, status validation)
- list/get/patch/delete + status filter
- milestones: create/list/patch(status)/delete, ordered by due date
- project summary rolls up linked time + expenses vs budget
- time entries and expenses can carry project_id
- events emitted; tenant isolation

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


print("== Phase T: projects ==")
SUFFIX = str(int(time.time()))
email = f"phaset-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase T",
    "tenant_name": f"Phase T {SUFFIX}", "tenant_slug": f"phaset-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create project ==")
s, p = call("POST", "/api/projects", {
    "name": "Website Redesign", "description": "Q3 site overhaul",
    "status": "active", "budget_cents": 500000, "currency": "usd",
    "start_date": "2026-08-01", "end_date": "2026-09-30",
}, token=TOK)
check("create 201", s == 201, f"{s} {p}")
PID = p.get("id")
check("auto slug", p.get("slug") == "website-redesign", str(p.get("slug")))
check("currency uppercased", p.get("currency") == "USD", str(p.get("currency")))
check("owner set", bool(p.get("owner_id")), str(p.get("owner_id")))

s, res = call("POST", "/api/projects", {"name": "Website Redesign"}, token=TOK)
check("slug collision 409", s == 409, f"{s} {res}")
s, res = call("POST", "/api/projects", {"name": "x", "status": "bogus"}, token=TOK)
check("bad status 422", s == 422, f"{s} {res}")

print("== 2. list + filter + patch ==")
s, p2 = call("POST", "/api/projects", {"name": "Mobile App", "status": "planning"}, token=TOK)
check("second project", s == 201, f"{s} {p2}")
PID2 = p2.get("id")
s, res = call("GET", "/api/projects", token=TOK)
check("list all = 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/projects?status=active", token=TOK)
check("filter active = 1", res.get("total") == 1 and res["items"][0]["id"] == PID, str(res.get("total")))
s, res = call("PATCH", f"/api/projects/{PID}", {"budget_cents": 600000, "description": "updated"}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch budget", res.get("budget_cents") == 600000, str(res.get("budget_cents")))

print("== 3. milestones ==")
s, m1 = call("POST", f"/api/projects/{PID}/milestones", {"title": "Wireframes", "due_date": "2026-08-15"}, token=TOK)
check("milestone 1 created", s == 201, f"{s} {m1}")
MID1 = m1.get("id")
s, m2 = call("POST", f"/api/projects/{PID}/milestones", {"title": "Launch", "due_date": "2026-09-30"}, token=TOK)
check("milestone 2 created", s == 201, f"{s} {m2}")
s, res = call("GET", f"/api/projects/{PID}/milestones", token=TOK)
check("list milestones = 2", res.get("total") == 2, str(res.get("total")))
check("ordered by due date", res["items"][0]["title"] == "Wireframes", str(res["items"][0].get("title")))
s, res = call("PATCH", f"/api/projects/{PID}/milestones/{MID1}", {"status": "done"}, token=TOK)
check("milestone done", s == 200 and res.get("status") == "done", f"{s} {res.get('status')}")
s, res = call("PATCH", f"/api/projects/{PID}/milestones/{MID1}", {"status": "bogus"}, token=TOK)
check("bad milestone status 422", s == 422, f"{s} {res}")

print("== 4. link time + expenses to project ==")
NOW = datetime.now(timezone.utc)
s, te = call("POST", "/api/time", {
    "description": "Design work", "started_at": (NOW - timedelta(hours=3)).isoformat(),
    "stopped_at": (NOW - timedelta(hours=1)).isoformat(), "project_id": PID,
}, token=TOK)
check("time entry linked", s == 201 and te.get("project_id") == PID, f"{s} {te.get('project_id')}")
check("time duration 120", te.get("duration_minutes") == 120, str(te.get("duration_minutes")))

s, ex = call("POST", "/api/expenses", {
    "title": "Stock photos", "category": "Marketing", "amount_cents": 15000, "project_id": PID,
}, token=TOK)
check("expense linked", s == 201 and ex.get("project_id") == PID, f"{s} {ex.get('project_id')}")

print("== 5. project summary rollup ==")
s, res = call("GET", f"/api/projects/{PID}/summary", token=TOK)
check("summary 200", s == 200, str(s))
check("budget reflected", res.get("budget_cents") == 600000, str(res.get("budget_cents")))
check("spent = 15000", res.get("spent_cents") == 15000, str(res.get("spent_cents")))
check("remaining = 585000", res.get("remaining_cents") == 585000, str(res.get("remaining_cents")))
check("budget_used_pct", res.get("budget_used_pct") == 2.5, str(res.get("budget_used_pct")))
check("time_minutes = 120", res.get("time_minutes") == 120, str(res.get("time_minutes")))
check("milestones 1/2 done", res.get("milestones_done") == 1 and res.get("milestones_total") == 2,
      f"{res.get('milestones_done')}/{res.get('milestones_total')}")

print("== 6. events + milestone delete + project delete + isolation ==")
for ev in ("project.created", "project.milestone_created"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, str(len(events)))

s, res = call("DELETE", f"/api/projects/{PID}/milestones/{m2.get('id')}", token=TOK)
check("delete milestone 200", s == 200, f"{s} {res}")
s, res = call("GET", f"/api/projects/{PID}/milestones", token=TOK)
check("one milestone remains", res.get("total") == 1, str(res.get("total")))

s, res = call("DELETE", f"/api/projects/{PID2}", token=TOK)
check("delete project 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/projects", token=TOK)
check("one project remains", res.get("total") == 1, str(res.get("total")))

email2 = f"phaset2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase T2",
    "tenant_name": f"Phase T2 {SUFFIX}", "tenant_slug": f"phaset2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/projects", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/projects/{PID}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
