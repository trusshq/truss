"""Phase X smoke test: approvals center — unified inbox across all approval queues.

Verifies:
- GET /api/approvals returns items + total + by_kind counts
- submitted expenses appear as kind=expense
- pending leave appears as kind=leave
- agent tasks with needs_review appear as kind=agent_task
- non-pending items (draft/approved/rejected/auto-approved tasks) are excluded
- items sorted newest-first
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


print("== Phase X: approvals center ==")
SUFFIX = str(int(time.time()))
email = f"phasex-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase X",
    "tenant_name": f"Phase X {SUFFIX}", "tenant_slug": f"phasex-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. empty inbox ==")
s, res = call("GET", "/api/approvals", token=TOK)
check("approvals 200", s == 200, str(s))
check("empty total 0", res.get("total") == 0, str(res.get("total")))
check("by_kind zeros", res.get("by_kind") == {"expense": 0, "leave": 0, "agent_task": 0}, str(res.get("by_kind")))

print("== 2. seed one of each pending kind ==")
# submitted expense
s, ex = call("POST", "/api/expenses", {"title": "Flight", "category": "Travel", "amount_cents": 12000}, token=TOK)
check("expense created", s == 201, f"{s} {ex}")
call("POST", f"/api/expenses/{ex['id']}/submit", {}, token=TOK)
# pending leave
s, emp = call("POST", "/api/hr/employees", {"name": "Zoe", "email": f"zoe-{SUFFIX}@x.com"}, token=TOK)
check("employee created", s == 201, f"{s} {emp}")
s, lv = call("POST", "/api/hr/leave", {"employee_id": emp["id"], "leave_type": "sick",
                                       "start_date": "2026-09-10", "end_date": "2026-09-11"}, token=TOK)
check("leave created", s == 201, f"{s} {lv}")
# agent task needing review
s, ag = call("POST", "/api/agents", {"name": "Tasker", "role": "ops"}, token=TOK)
check("agent created", s in (200, 201), f"{s} {ag}")
s, task = call("POST", f"/api/agents/{ag['id']}/tasks",
               {"agent_id": ag["id"], "title": "Send newsletter", "needs_review": True}, token=TOK)
check("review task created", s == 201, f"{s} {task}")

print("== 3. seed items that should NOT appear ==")
# draft expense (not submitted)
call("POST", "/api/expenses", {"title": "DraftOnly", "category": "Meals", "amount_cents": 900}, token=TOK)
# approved leave
s, lv2 = call("POST", "/api/hr/leave", {"employee_id": emp["id"], "leave_type": "vacation",
                                        "start_date": "2026-10-01", "end_date": "2026-10-02"}, token=TOK)
call("POST", f"/api/hr/leave/{lv2['id']}/approve", {}, token=TOK)
# auto-approved task (needs_review=False)
call("POST", f"/api/agents/{ag['id']}/tasks",
     {"agent_id": ag["id"], "title": "Auto task", "needs_review": False}, token=TOK)

print("== 4. inbox reflects exactly the 3 pending items ==")
s, res = call("GET", "/api/approvals", token=TOK)
check("approvals 200", s == 200, str(s))
check("total = 3", res.get("total") == 3, str(res.get("total")))
check("by_kind 1/1/1", res.get("by_kind") == {"expense": 1, "leave": 1, "agent_task": 1}, str(res.get("by_kind")))
kinds = {i["kind"] for i in res["items"]}
check("all 3 kinds present", kinds == {"expense", "leave", "agent_task"}, str(kinds))
exp_item = next(i for i in res["items"] if i["kind"] == "expense")
check("expense title", exp_item["title"] == "Flight", str(exp_item.get("title")))
check("expense detail has amount", "120.00" in exp_item["detail"], str(exp_item.get("detail")))
leave_item = next(i for i in res["items"] if i["kind"] == "leave")
check("leave detail has range", "2026-09-10" in leave_item["detail"], str(leave_item.get("detail")))
task_item = next(i for i in res["items"] if i["kind"] == "agent_task")
check("task title", task_item["title"] == "Send newsletter", str(task_item.get("title")))
check("task carries agent_id", bool(task_item.get("agent_id")), str(task_item.get("agent_id")))
# sorted newest-first
created = [i["created_at"] for i in res["items"]]
check("sorted newest-first", created == sorted(created, reverse=True), str(created))

print("== 5. approving removes from inbox ==")
call("POST", f"/api/expenses/{ex['id']}/approve", {}, token=TOK)
s, res = call("GET", "/api/approvals", token=TOK)
check("total drops to 2", res.get("total") == 2, str(res.get("total")))
check("expense gone from by_kind", res["by_kind"]["expense"] == 0, str(res.get("by_kind")))

print("== 6. tenant isolation ==")
email2 = f"phasex2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase X2",
    "tenant_name": f"Phase X2 {SUFFIX}", "tenant_slug": f"phasex2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/approvals", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
