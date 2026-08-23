"""Phase S smoke test: expenses & approvals — CRUD + submit/approve/reject/reimburse.

Verifies:
- create draft expense (category validation, amount in cents)
- list filters (status, category, mine)
- summary aggregates by status + category
- workflow: draft -> submit -> approve -> reimburse
- reject path: submitted -> rejected, then editable + resubmittable
- guards: can't edit/delete submitted/approved; can't submit zero; can't
  approve a draft; can't reimburse unapproved; double transitions 409
- review metadata recorded (reviewed_by, note, at)
- events emitted on each transition
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


print("== Phase S: expenses ==")
SUFFIX = str(int(time.time()))
email = f"phases-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase S",
    "tenant_name": f"Phase S {SUFFIX}", "tenant_slug": f"phases-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")  # owner => can also approve

print("== 1. create draft ==")
s, ex = call("POST", "/api/expenses", {
    "title": "Flight to client", "category": "Travel",
    "amount_cents": 45000, "currency": "usd", "occurred_on": "2026-08-20",
    "notes": "Round trip SFO",
}, token=TOK)
check("create 201", s == 201, f"{s} {ex}")
EID = ex.get("id")
check("draft status", ex.get("status") == "draft", str(ex.get("status")))
check("currency uppercased", ex.get("currency") == "USD", str(ex.get("currency")))
check("amount stored", ex.get("amount_cents") == 45000, str(ex.get("amount_cents")))

s, res = call("POST", "/api/expenses", {"title": "x", "category": "Bogus", "amount_cents": 100}, token=TOK)
check("bad category 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/expenses", {"title": "x", "amount_cents": -5}, token=TOK)
check("negative amount 422", s == 422, f"{s} {res}")

print("== 2. more expenses for filters/summary ==")
s, ex2 = call("POST", "/api/expenses", {"title": "Team lunch", "category": "Meals", "amount_cents": 8000}, token=TOK)
check("second created", s == 201, f"{s} {ex2}")
EID2 = ex2.get("id")
s, ex3 = call("POST", "/api/expenses", {"title": "SaaS sub", "category": "Software", "amount_cents": 12000}, token=TOK)
check("third created", s == 201, f"{s} {ex3}")
EID3 = ex3.get("id")

print("== 3. list filters ==")
s, res = call("GET", "/api/expenses", token=TOK)
check("list all = 3", res.get("total") == 3, str(res.get("total")))
s, res = call("GET", "/api/expenses?category=Travel", token=TOK)
check("filter category", res.get("total") == 1 and res["items"][0]["id"] == EID, str(res.get("total")))
s, res = call("GET", "/api/expenses?mine=true", token=TOK)
check("filter mine", res.get("total") == 3, str(res.get("total")))

print("== 4. summary ==")
s, res = call("GET", "/api/expenses/summary", token=TOK)
check("summary 200", s == 200, str(s))
check("summary total", res.get("total_cents") == 65000, str(res.get("total_cents")))
check("summary count", res.get("count") == 3, str(res.get("count")))
check("summary by_category has Travel", any(r["label"] == "Travel" for r in res.get("by_category", [])), str(res.get("by_category")))

print("== 5. workflow: submit -> approve -> reimburse ==")
s, res = call("POST", f"/api/expenses/{EID}/submit", token=TOK)
check("submit 200", s == 200, f"{s} {res}")
check("status submitted", res.get("status") == "submitted", str(res.get("status")))

# can't edit or delete while submitted
s, res = call("PATCH", f"/api/expenses/{EID}", {"title": "changed"}, token=TOK)
check("edit submitted 409", s == 409, f"{s} {res}")
s, res = call("DELETE", f"/api/expenses/{EID}", token=TOK)
check("delete submitted 409", s == 409, f"{s} {res}")

s, res = call("POST", f"/api/expenses/{EID}/approve", {"note": "looks good"}, token=TOK)
check("approve 200", s == 200, f"{s} {res}")
check("status approved", res.get("status") == "approved", str(res.get("status")))
check("review note recorded", res.get("review_note") == "looks good", str(res.get("review_note")))
check("reviewed_by set", bool(res.get("reviewed_by")), str(res.get("reviewed_by")))
check("reviewed_at set", bool(res.get("reviewed_at")), str(res.get("reviewed_at")))

s, res = call("POST", f"/api/expenses/{EID}/reimburse", token=TOK)
check("reimburse 200", s == 200, f"{s} {res}")
check("status reimbursed", res.get("status") == "reimbursed", str(res.get("status")))

print("== 6. reject path ==")
s, res = call("POST", f"/api/expenses/{EID2}/submit", token=TOK)
check("submit ex2", s == 200, f"{s} {res}")
s, res = call("POST", f"/api/expenses/{EID2}/reject", {"note": "missing receipt"}, token=TOK)
check("reject 200", s == 200, f"{s} {res}")
check("status rejected", res.get("status") == "rejected", str(res.get("status")))
# rejected is editable + resubmittable
s, res = call("PATCH", f"/api/expenses/{EID2}", {"notes": "receipt attached now"}, token=TOK)
check("edit rejected 200", s == 200, f"{s} {res}")
s, res = call("POST", f"/api/expenses/{EID2}/submit", token=TOK)
check("resubmit rejected 200", s == 200, f"{s} {res}")
check("resubmitted status", res.get("status") == "submitted", str(res.get("status")))

print("== 7. guards ==")
# can't approve a draft
s, res = call("POST", f"/api/expenses/{EID3}/approve", {}, token=TOK)
check("approve draft 409", s == 409, f"{s} {res}")
# can't reimburse unapproved
s, res = call("POST", f"/api/expenses/{EID3}/reimburse", token=TOK)
check("reimburse draft 409", s == 409, f"{s} {res}")
# can't submit zero amount
s, zero = call("POST", "/api/expenses", {"title": "zero", "amount_cents": 0}, token=TOK)
check("zero created", s == 201, f"{s} {zero}")
s, res = call("POST", f"/api/expenses/{zero['id']}/submit", token=TOK)
check("submit zero 422", s == 422, f"{s} {res}")
# double approve 409 (already reimbursed)
s, res = call("POST", f"/api/expenses/{EID}/approve", {}, token=TOK)
check("double approve 409", s == 409, f"{s} {res}")

print("== 8. events ==")
for ev in ("expense.created", "expense.submitted", "expense.approved", "expense.rejected", "expense.reimbursed"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, str(len(events)))

print("== 9. delete draft + tenant isolation ==")
s, res = call("DELETE", f"/api/expenses/{zero['id']}", token=TOK)
check("delete draft 200", s == 200, f"{s} {res}")
email2 = f"phases2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase S2",
    "tenant_name": f"Phase S2 {SUFFIX}", "tenant_slug": f"phases2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/expenses", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/expenses/{EID}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
