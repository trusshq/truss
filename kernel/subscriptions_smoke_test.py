"""Phase AE smoke test: subscriptions — plans, lifecycle, and MRR.

Verifies:
- create plan (interval validation, price in cents)
- plans list/get/patch/delete (delete blocked while subscriptions exist)
- create subscription (active plan only, bad plan 404)
- list filters (status, plan_id)
- lifecycle: pause (active only), resume (paused only), cancel (stamps
  cancelled_at), reactivate (cancelled only), 409 guards
- cancelled subscriptions locked from edit
- MRR: monthly full price, yearly /12, only active counted
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


print("== Phase AE: subscriptions ==")
SUFFIX = str(int(time.time()))
email = f"phaseae-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AE",
    "tenant_name": f"Phase AE {SUFFIX}", "tenant_slug": f"phaseae-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create plans ==")
s, p1 = call("POST", "/api/subscriptions/plans", {
    "name": "Pro Monthly", "interval": "monthly", "price_cents": 4900,
}, token=TOK)
check("plan created 201", s == 201, f"{s} {p1}")
P1 = p1.get("id")
check("interval monthly", p1.get("interval") == "monthly", str(p1.get("interval")))
check("price 4900", p1.get("price_cents") == 4900, str(p1.get("price_cents")))
s, p2 = call("POST", "/api/subscriptions/plans", {
    "name": "Pro Yearly", "interval": "yearly", "price_cents": 49000,
}, token=TOK)
P2 = p2.get("id")
check("yearly plan created", s == 201, str(s))
s, _ = call("POST", "/api/subscriptions/plans", {"name": "X", "interval": "weekly"}, token=TOK)
check("bad interval 400", s == 400, str(s))

print("== 2. plans list/get/patch ==")
s, res = call("GET", "/api/subscriptions/plans", token=TOK)
check("plans total 2", res.get("total") == 2, str(res.get("total")))
s, got = call("GET", f"/api/subscriptions/plans/{P1}", token=TOK)
check("get plan", got.get("name") == "Pro Monthly", str(got.get("name")))
s, upd = call("PATCH", f"/api/subscriptions/plans/{P1}", {"price_cents": 5900}, token=TOK)
check("patch plan price", upd.get("price_cents") == 5900, str(upd.get("price_cents")))

print("== 3. create subscriptions ==")
s, sub1 = call("POST", "/api/subscriptions", {
    "plan_id": P1, "customer": "Acme Corp", "current_period_end": "2026-09-23",
}, token=TOK)
check("subscription created 201", s == 201, f"{s} {sub1}")
S1 = sub1.get("id")
check("status active", sub1.get("status") == "active", str(sub1.get("status")))
s, sub2 = call("POST", "/api/subscriptions", {"plan_id": P2, "customer": "Globex"}, token=TOK)
S2 = sub2.get("id")
check("second subscription", s == 201, str(s))
# bad plan
s, _ = call("POST", "/api/subscriptions", {"plan_id": "00000000-0000-0000-0000-000000000000", "customer": "X"}, token=TOK)
check("bad plan 404", s == 404, str(s))
# inactive plan blocked
s, p3 = call("POST", "/api/subscriptions/plans", {"name": "Legacy", "active": False}, token=TOK)
s, _ = call("POST", "/api/subscriptions", {"plan_id": p3["id"], "customer": "X"}, token=TOK)
check("inactive plan 409", s == 409, str(s))

print("== 4. list filters ==")
s, res = call("GET", "/api/subscriptions", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/subscriptions?status=active", token=TOK)
check("status filter active", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/subscriptions?plan_id={P1}", token=TOK)
check("plan filter", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/subscriptions?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 5. MRR ==")
# monthly 5900 + yearly 49000/12 = 4083.33 -> total 9983
s, mrr = call("GET", "/api/subscriptions/mrr", token=TOK)
check("mrr computed", s == 200, str(s))
check("mrr = 5900 + 49000/12", mrr.get("mrr_cents") == round(5900 + 49000 / 12.0), str(mrr.get("mrr_cents")))
check("active count 2", mrr.get("active_subscriptions") == 2, str(mrr.get("active_subscriptions")))

print("== 6. lifecycle guards ==")
# pause
s, pa = call("POST", f"/api/subscriptions/{S1}/pause", {}, token=TOK)
check("pause 200", s == 200, str(s))
check("status paused", pa.get("status") == "paused", str(pa.get("status")))
# can't re-pause
s, _ = call("POST", f"/api/subscriptions/{S1}/pause", {}, token=TOK)
check("re-pause 409", s == 409, str(s))
# paused not in MRR
s, mrr2 = call("GET", "/api/subscriptions/mrr", token=TOK)
check("mrr excludes paused", mrr2.get("active_subscriptions") == 1, str(mrr2.get("active_subscriptions")))
# resume
s, rs = call("POST", f"/api/subscriptions/{S1}/resume", {}, token=TOK)
check("resume 200", s == 200, str(s))
check("status active", rs.get("status") == "active", str(rs.get("status")))
# can't resume active
s, _ = call("POST", f"/api/subscriptions/{S1}/resume", {}, token=TOK)
check("resume active 409", s == 409, str(s))
# cancel
s, cn = call("POST", f"/api/subscriptions/{S1}/cancel", {}, token=TOK)
check("cancel 200", s == 200, str(s))
check("status cancelled", cn.get("status") == "cancelled", str(cn.get("status")))
check("cancelled_at stamped", bool(cn.get("cancelled_at")), str(cn.get("cancelled_at")))
# can't re-cancel
s, _ = call("POST", f"/api/subscriptions/{S1}/cancel", {}, token=TOK)
check("re-cancel 409", s == 409, str(s))
# cancelled locked from edit
s, _ = call("PATCH", f"/api/subscriptions/{S1}", {"customer": "New"}, token=TOK)
check("edit cancelled 409", s == 409, str(s))
# reactivate
s, ra = call("POST", f"/api/subscriptions/{S1}/reactivate", {}, token=TOK)
check("reactivate 200", s == 200, str(s))
check("status active again", ra.get("status") == "active", str(ra.get("status")))
check("cancelled_at cleared", ra.get("cancelled_at") == "", str(ra.get("cancelled_at")))
# can't reactivate active
s, _ = call("POST", f"/api/subscriptions/{S1}/reactivate", {}, token=TOK)
check("reactivate active 409", s == 409, str(s))

print("== 7. plan delete blocked by subscriptions ==")
s, _ = call("DELETE", f"/api/subscriptions/plans/{P1}", token=TOK)
check("delete plan w/ subs 409", s == 409, str(s))

print("== 8. events + delete + isolation ==")
for ev in ("plan.created", "subscription.created", "subscription.paused", "subscription.resumed", "subscription.cancelled", "subscription.reactivated"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/subscriptions/{S2}", token=TOK)
check("delete subscription 200", s == 200, str(s))
s, res = call("GET", "/api/subscriptions", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# now plan P2 has no subs -> deletable
s, _ = call("DELETE", f"/api/subscriptions/plans/{P2}", token=TOK)
check("delete empty plan 200", s == 200, str(s))
# other tenant sees nothing
email2 = f"phaseae2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AE2",
    "tenant_name": f"Phase AE2 {SUFFIX}", "tenant_slug": f"phaseae2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/subscriptions", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/subscriptions/{S1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
