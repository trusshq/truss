"""Phase V smoke test: HR/People — employee directory + leave approvals.

Verifies:
- create employee (email collision 409, status validation, email lowercased)
- list filters (department, status, q search)
- get/patch/delete
- leave request: create (type + date validation), list filters
- approve/reject workflow (pending only, 409 on re-review)
- events emitted; tenant isolation

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


print("== Phase V: HR ==")
SUFFIX = str(int(time.time()))
email = f"phasev-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase V",
    "tenant_name": f"Phase V {SUFFIX}", "tenant_slug": f"phasev-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create employees ==")
s, e1 = call("POST", "/api/hr/employees", {
    "name": "Alice Chen", "email": "Alice@Example.com", "title": "Engineer",
    "department": "Engineering", "hire_date": "2025-01-15",
}, token=TOK)
check("create 201", s == 201, f"{s} {e1}")
EID = e1.get("id")
check("email lowercased", e1.get("email") == "alice@example.com", str(e1.get("email")))
check("status active", e1.get("status") == "active", str(e1.get("status")))

s, res = call("POST", "/api/hr/employees", {"name": "dup", "email": "alice@example.com"}, token=TOK)
check("email collision 409", s == 409, f"{s} {res}")
s, res = call("POST", "/api/hr/employees", {"name": "x", "email": "x@y.com", "status": "bogus"}, token=TOK)
check("bad status 422", s == 422, f"{s} {res}")

s, e2 = call("POST", "/api/hr/employees", {
    "name": "Bob Diaz", "email": "bob@example.com", "title": "Designer", "department": "Design",
}, token=TOK)
check("second employee", s == 201, f"{s} {e2}")
EID2 = e2.get("id")

print("== 2. list filters ==")
s, res = call("GET", "/api/hr/employees", token=TOK)
check("list all = 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/hr/employees?department=Engineering", token=TOK)
check("filter department = 1", res.get("total") == 1 and res["items"][0]["id"] == EID, str(res.get("total")))
s, res = call("GET", "/api/hr/employees?q=bob", token=TOK)
check("search q = 1", res.get("total") == 1 and res["items"][0]["id"] == EID2, str(res.get("total")))

print("== 3. patch employee ==")
s, res = call("PATCH", f"/api/hr/employees/{EID}", {"title": "Senior Engineer", "status": "on_leave"}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch title", res.get("title") == "Senior Engineer", str(res.get("title")))
check("patch status", res.get("status") == "on_leave", str(res.get("status")))

print("== 4. leave requests ==")
s, l1 = call("POST", "/api/hr/leave", {
    "employee_id": EID, "leave_type": "vacation",
    "start_date": "2026-09-01", "end_date": "2026-09-05", "reason": "Family trip",
}, token=TOK)
check("leave created", s == 201, f"{s} {l1}")
LID = l1.get("id")
check("leave pending", l1.get("status") == "pending", str(l1.get("status")))

s, res = call("POST", "/api/hr/leave", {
    "employee_id": EID, "leave_type": "bogus", "start_date": "2026-09-01", "end_date": "2026-09-02",
}, token=TOK)
check("bad leave_type 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/hr/leave", {
    "employee_id": EID, "leave_type": "sick", "start_date": "2026-09-05", "end_date": "2026-09-01",
}, token=TOK)
check("end before start 422", s == 422, f"{s} {res}")

s, res = call("GET", "/api/hr/leave", token=TOK)
check("list leave = 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/hr/leave?status=pending", token=TOK)
check("filter pending = 1", res.get("total") == 1, str(res.get("total")))

print("== 5. approve/reject workflow ==")
s, res = call("POST", f"/api/hr/leave/{LID}/approve", {"note": "Enjoy!"}, token=TOK)
check("approve 200", s == 200, f"{s} {res}")
check("status approved", res.get("status") == "approved", str(res.get("status")))
check("review note", res.get("review_note") == "Enjoy!", str(res.get("review_note")))
check("reviewed_at set", bool(res.get("reviewed_at")), str(res.get("reviewed_at")))

s, res = call("POST", f"/api/hr/leave/{LID}/approve", {}, token=TOK)
check("re-approve 409", s == 409, f"{s} {res}")

s, l2 = call("POST", "/api/hr/leave", {
    "employee_id": EID2, "leave_type": "sick", "start_date": "2026-09-10", "end_date": "2026-09-11",
}, token=TOK)
check("second leave", s == 201, f"{s} {l2}")
s, res = call("POST", f"/api/hr/leave/{l2['id']}/reject", {"note": "Coverage needed"}, token=TOK)
check("reject 200", s == 200, f"{s} {res}")
check("status rejected", res.get("status") == "rejected", str(res.get("status")))

print("== 6. events + delete + isolation ==")
for ev in ("hr.employee_created", "hr.leave_requested", "hr.leave_approved", "hr.leave_rejected"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, str(len(events)))

s, res = call("DELETE", f"/api/hr/employees/{EID2}", token=TOK)
check("delete employee 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/hr/employees", token=TOK)
check("one remains", res.get("total") == 1, str(res.get("total")))

email2 = f"phasev2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase V2",
    "tenant_name": f"Phase V2 {SUFFIX}", "tenant_slug": f"phasev2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/hr/employees", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/hr/employees/{EID}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
