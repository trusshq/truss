"""Major Phase 7 smoke test: payroll — profiles, pay runs, payslips, lifecycle.

Verifies:
- create payroll profile (active employee only, duplicate rejected,
  frequency + tax validation, salary >= 1)
- list filters (status), get/patch profile (validation)
- pay run: create generates one payslip per ACTIVE profile with correct
  gross/tax/net math per frequency; period validation
- run lifecycle: draft -> approve -> pay (marks slips paid), cancel
  guards, delete draft-only, approve/paid guards
- payslips: list filters (run, employee, status), get
- profile delete blocked while payslips exist
- events emitted
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


print("== Major Phase 7: payroll ==")
SUFFIX = str(int(time.time()))
email = f"phase7-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase 7",
    "tenant_name": f"Phase 7 {SUFFIX}", "tenant_slug": f"phase7-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 0. seed employees ==")
s, e1 = call("POST", "/api/hr/employees", {
    "name": "Alice", "email": "alice@x.com", "title": "Engineer", "department": "Eng",
}, token=TOK)
check("employee 1 created", s == 201, f"{s} {e1}")
E1 = e1.get("id")
s, e2 = call("POST", "/api/hr/employees", {
    "name": "Bob", "email": "bob@x.com", "title": "Designer", "department": "Design",
}, token=TOK)
E2 = e2.get("id")
check("employee 2 created", s == 201, str(s))
# a terminated employee for the guard
s, e3 = call("POST", "/api/hr/employees", {
    "name": "Carl", "email": "carl@x.com", "status": "terminated",
}, token=TOK)
E3 = e3.get("id")

print("== 1. profiles ==")
s, p1 = call("POST", "/api/payroll/profiles", {
    "employee_id": E1, "annual_salary_cents": 12000000, "frequency": "monthly", "tax_rate_pct": 20,
}, token=TOK)
check("profile 1 created 201", s == 201, f"{s} {p1}")
P1 = p1.get("id")
check("status active", p1.get("status") == "active", str(p1.get("status")))
# duplicate rejected
s, _ = call("POST", "/api/payroll/profiles", {"employee_id": E1, "annual_salary_cents": 1}, token=TOK)
check("duplicate profile 409", s == 409, str(s))
# terminated employee rejected
s, _ = call("POST", "/api/payroll/profiles", {"employee_id": E3, "annual_salary_cents": 1}, token=TOK)
check("terminated employee 409", s == 409, str(s))
# bad frequency
s, _ = call("POST", "/api/payroll/profiles", {"employee_id": E2, "annual_salary_cents": 1, "frequency": "bogus"}, token=TOK)
check("bad frequency 400", s == 400, str(s))
# salary 0 rejected (422 from Field ge=1)
s, _ = call("POST", "/api/payroll/profiles", {"employee_id": E2, "annual_salary_cents": 0}, token=TOK)
check("salary 0 rejected 422", s == 422, str(s))
# tax > 100 rejected
s, _ = call("POST", "/api/payroll/profiles", {"employee_id": E2, "annual_salary_cents": 1, "tax_rate_pct": 101}, token=TOK)
check("tax > 100 rejected 422", s == 422, str(s))
# biweekly profile for Bob: 5200000 annual -> 200000 per 26 periods
s, p2 = call("POST", "/api/payroll/profiles", {
    "employee_id": E2, "annual_salary_cents": 5200000, "frequency": "biweekly", "tax_rate_pct": 10,
}, token=TOK)
P2 = p2.get("id")
check("profile 2 created", s == 201, str(s))
# list + filter
s, res = call("GET", "/api/payroll/profiles", token=TOK)
check("profiles total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/payroll/profiles?status=active", token=TOK)
check("status filter active", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/payroll/profiles?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))
# patch profile
s, pp = call("PATCH", f"/api/payroll/profiles/{P2}", {"tax_rate_pct": 15}, token=TOK)
check("patch profile 200", s == 200, str(s))
check("tax updated", pp.get("tax_rate_pct") == 15, str(pp.get("tax_rate_pct")))
s, _ = call("PATCH", f"/api/payroll/profiles/{P2}", {"frequency": "bogus"}, token=TOK)
check("patch bad frequency 400", s == 400, str(s))

print("== 2. pay run generation ==")
# bad period
s, _ = call("POST", "/api/payroll/runs", {"period_start": "2026-08-31", "period_end": "2026-08-01"}, token=TOK)
check("period_end < start 400", s == 400, str(s))
s, run = call("POST", "/api/payroll/runs", {"period_start": "2026-08-01", "period_end": "2026-08-31"}, token=TOK)
check("run created 201", s == 201, f"{s} {run}")
R1 = run.get("id")
check("status draft", run.get("status") == "draft", str(run.get("status")))
# Alice monthly: 12000000/12 = 1000000 gross, 20% tax = 200000, net 800000
# Bob biweekly: 5200000/26 = 200000 gross, 15% tax = 30000, net 170000
check("total gross", run.get("total_gross_cents") == 1200000, str(run.get("total_gross_cents")))
check("total tax", run.get("total_tax_cents") == 230000, str(run.get("total_tax_cents")))
check("total net", run.get("total_net_cents") == 970000, str(run.get("total_net_cents")))
# payslips generated
s, res = call("GET", f"/api/payroll/payslips?pay_run_id={R1}", token=TOK)
check("2 payslips generated", res.get("total") == 2, str(res.get("total")))
slips = {it["employee_id"]: it for it in res.get("items", [])}
alice = slips.get(E1, {})
bob = slips.get(E2, {})
check("alice gross 1000000", alice.get("gross_cents") == 1000000, str(alice.get("gross_cents")))
check("alice tax 200000", alice.get("tax_cents") == 200000, str(alice.get("tax_cents")))
check("alice net 800000", alice.get("net_cents") == 800000, str(alice.get("net_cents")))
check("bob gross 200000", bob.get("gross_cents") == 200000, str(bob.get("gross_cents")))
check("bob tax 30000", bob.get("tax_cents") == 30000, str(bob.get("tax_cents")))
check("bob net 170000", bob.get("net_cents") == 170000, str(bob.get("net_cents")))
check("slips pending", alice.get("status") == "pending" and bob.get("status") == "pending",
      f"{alice.get('status')} {bob.get('status')}")
A_SLIP = alice.get("id")

print("== 3. run lifecycle ==")
# pay before approve rejected
s, _ = call("POST", f"/api/payroll/runs/{R1}/pay", token=TOK)
check("pay draft 409", s == 409, str(s))
# approve
s, ap = call("POST", f"/api/payroll/runs/{R1}/approve", token=TOK)
check("approve 200", s == 200, str(s))
check("status approved", ap.get("status") == "approved", str(ap.get("status")))
# double approve rejected
s, _ = call("POST", f"/api/payroll/runs/{R1}/approve", token=TOK)
check("double approve 409", s == 409, str(s))
# delete approved rejected
s, _ = call("DELETE", f"/api/payroll/runs/{R1}", token=TOK)
check("delete approved 409", s == 409, str(s))
# pay
s, paid = call("POST", f"/api/payroll/runs/{R1}/pay", token=TOK)
check("pay 200", s == 200, str(s))
check("status paid", paid.get("status") == "paid", str(paid.get("status")))
# slips now paid
s, res = call("GET", f"/api/payroll/payslips?pay_run_id={R1}&status=paid", token=TOK)
check("all slips paid", res.get("total") == 2, str(res.get("total")))
# cancel paid rejected
s, _ = call("POST", f"/api/payroll/runs/{R1}/cancel", token=TOK)
check("cancel paid 409", s == 409, str(s))

print("== 4. cancel + delete draft ==")
s, run2 = call("POST", "/api/payroll/runs", {"period_start": "2026-09-01", "period_end": "2026-09-30"}, token=TOK)
R2 = run2.get("id")
check("run 2 created", s == 201, str(s))
s, _ = call("POST", f"/api/payroll/runs/{R2}/cancel", token=TOK)
check("cancel draft 200", s == 200, str(s))
s, run3 = call("POST", "/api/payroll/runs", {"period_start": "2026-10-01", "period_end": "2026-10-31"}, token=TOK)
R3 = run3.get("id")
s, _ = call("DELETE", f"/api/payroll/runs/{R3}", token=TOK)
check("delete draft 200", s == 200, str(s))
# run list filters
s, res = call("GET", "/api/payroll/runs?status=paid", token=TOK)
check("run status filter paid", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/payroll/runs?status=bogus", token=TOK)
check("run bad status 400", s == 400, str(s))

print("== 5. payslip filters + delete guards + events + isolation ==")
s, res = call("GET", f"/api/payroll/payslips?employee_id={E1}", token=TOK)
check("employee filter", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/payroll/payslips?status=bogus", token=TOK)
check("slip bad status 400", s == 400, str(s))
s, got = call("GET", f"/api/payroll/payslips/{A_SLIP}", token=TOK)
check("get payslip 200", s == 200, str(s))
# profile delete blocked while payslips exist
s, _ = call("DELETE", f"/api/payroll/profiles/{P1}", token=TOK)
check("delete profile w/ payslips 409", s == 409, str(s))
for ev in ("payroll.profile_created", "payroll.run_created", "payroll.run_approved", "payroll.run_paid"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
# other tenant sees nothing
email2 = f"phase7b-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase 7b",
    "tenant_name": f"Phase 7b {SUFFIX}", "tenant_slug": f"phase7b-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/payroll/profiles", token=TOK2)
check("other tenant profiles empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/payroll/runs/{R1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
