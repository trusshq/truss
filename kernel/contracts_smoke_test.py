"""Phase AA smoke test: contracts — CRUD, lifecycle, renewal detection.

Verifies:
- create contract (auto number CT-0001, date validation, end<start 400)
- list filters (status, counterparty search)
- get (includes days_until_end) / patch (only draft/active editable)
- lifecycle: activate (draft only), cancel (draft/active), expire (active only), 409 guards
- renewals endpoint: active contracts inside notice window flagged, sorted by days_until_end
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
from datetime import date, timedelta

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


def d(offset_days):
    return (date.today() + timedelta(days=offset_days)).isoformat()


print("== Phase AA: contracts ==")
SUFFIX = str(int(time.time()))
email = f"phaseaa-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AA",
    "tenant_name": f"Phase AA {SUFFIX}", "tenant_slug": f"phaseaa-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create contract ==")
s, c = call("POST", "/api/contracts", {
    "name": "Annual SaaS", "counterparty": "Acme Corp", "value_cents": 1200000,
    "start_date": d(-30), "end_date": d(10), "auto_renew": True, "renewal_notice_days": 30,
}, token=TOK)
check("contract created 201", s == 201, f"{s} {c}")
CID = c.get("id")
check("number CT-0001", c.get("number") == "CT-0001", str(c.get("number")))
check("status draft", c.get("status") == "draft", str(c.get("status")))
check("value 1200000", c.get("value_cents") == 1200000, str(c.get("value_cents")))

print("== 2. date validation ==")
s, _ = call("POST", "/api/contracts", {"name": "Bad", "start_date": "2026-13-01"}, token=TOK)
check("bad date format 400", s == 400, str(s))
s, _ = call("POST", "/api/contracts", {"name": "Bad", "start_date": d(10), "end_date": d(-10)}, token=TOK)
check("end before start 400", s == 400, str(s))

print("== 3. list + filters ==")
s, res = call("GET", "/api/contracts", token=TOK)
check("list total 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/contracts?counterparty=Acme", token=TOK)
check("counterparty search finds it", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/contracts?status=draft", token=TOK)
check("status filter draft", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/contracts?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 4. get includes days_until_end ==")
s, got = call("GET", f"/api/contracts/{CID}", token=TOK)
check("get 200", s == 200, str(s))
check("days_until_end ~10", got.get("days_until_end") == 10, str(got.get("days_until_end")))

print("== 5. lifecycle guards ==")
# can't expire a draft
s, _ = call("POST", f"/api/contracts/{CID}/expire", {}, token=TOK)
check("expire draft 409", s == 409, str(s))
# activate it
s, act = call("POST", f"/api/contracts/{CID}/activate", {}, token=TOK)
check("activate 200", s == 200, str(s))
check("status active", act.get("status") == "active", str(act.get("status")))
# can't re-activate
s, _ = call("POST", f"/api/contracts/{CID}/activate", {}, token=TOK)
check("re-activate 409", s == 409, str(s))

print("== 6. renewals endpoint ==")
# contract ends in 10 days, notice window 30 -> should be flagged
s, ren = call("GET", "/api/contracts/renewals", token=TOK)
check("renewals 200", s == 200, str(s))
check("one renewal flagged", ren.get("total") == 1, str(ren.get("total")))
if ren.get("items"):
    check("needs_renewal true", ren["items"][0].get("needs_renewal") is True, str(ren["items"][0].get("needs_renewal")))
    check("days_until_end 10", ren["items"][0].get("days_until_end") == 10, str(ren["items"][0].get("days_until_end")))

print("== 7. contract outside window not flagged ==")
s, c2 = call("POST", "/api/contracts", {
    "name": "Far future", "counterparty": "Beta", "value_cents": 5000,
    "start_date": d(0), "end_date": d(365), "renewal_notice_days": 30,
}, token=TOK)
call("POST", f"/api/contracts/{c2['id']}/activate", {}, token=TOK)
s, ren = call("GET", "/api/contracts/renewals", token=TOK)
check("still one renewal (far future excluded)", ren.get("total") == 1, str(ren.get("total")))

print("== 8. expire + cancel paths ==")
s, exp = call("POST", f"/api/contracts/{CID}/expire", {}, token=TOK)
check("expire 200", s == 200, str(s))
check("status expired", exp.get("status") == "expired", str(exp.get("status")))
# can't edit expired
s, _ = call("PATCH", f"/api/contracts/{CID}", {"name": "X"}, token=TOK)
check("edit expired 409", s == 409, str(s))
# cancel the far-future one
s, can = call("POST", f"/api/contracts/{c2['id']}/cancel", {}, token=TOK)
check("cancel active 200", s == 200, str(s))
check("status cancelled", can.get("status") == "cancelled", str(can.get("status")))

print("== 9. events + delete + isolation ==")
for ev in ("contract.created", "contract.activated", "contract.expired", "contract.cancelled"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/contracts/{c2['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/contracts", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseaa2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AA2",
    "tenant_name": f"Phase AA2 {SUFFIX}", "tenant_slug": f"phaseaa2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/contracts", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/contracts/{CID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
