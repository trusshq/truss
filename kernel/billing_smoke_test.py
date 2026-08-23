"""Phase L smoke test: billing & subscriptions — plans, checkout, usage, limits, invoices.

Verifies:
- GET /api/billing/plans returns the public catalog
- fresh tenant auto-gets a free subscription
- usage reflects live counts with headroom
- checkout switches plan + seats and issues an invoice
- invoices list shows it
- cancel sets cancel_at_period_end
- limit enforcement: trial plan blocks record creation past cap (402)
- upgrade to business (unlimited) unblocks

Idempotent: fresh tenant per run.
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


print("== Phase L: billing & subscriptions ==")
SUFFIX = str(int(time.time()))
email = f"phasel-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase L",
    "tenant_name": f"Phase L {SUFFIX}", "tenant_slug": f"phasel-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. plan catalog ==")
s, res = call("GET", "/api/billing/plans", token=TOK)
check("plans 200", s == 200, str(s))
ids = {p["id"] for p in res.get("items", [])}
check("public plans free/pro/business", ids == {"free", "pro", "business"}, str(ids))
check("trial hidden from catalog", "trial" not in ids, str(ids))

print("== 2. auto free subscription ==")
s, sub = call("GET", "/api/billing/subscription", token=TOK)
check("subscription 200", s == 200, str(s))
check("defaults to free", sub.get("plan") == "free", str(sub.get("plan")))
check("status active", sub.get("status") == "active", str(sub.get("status")))

print("== 3. usage + headroom ==")
s, usage = call("GET", "/api/billing/usage", token=TOK)
check("usage 200", s == 200, str(s))
check("usage has members/records/agents", set(usage.get("usage", {})) >= {"members", "records", "agents"}, str(usage.get("usage")))
check("headroom present", "headroom" in usage, str(usage.keys()))
check("1 member counted", usage["usage"]["members"] == 1, str(usage["usage"]))

print("== 4. checkout to pro ==")
s, res = call("POST", "/api/billing/checkout", {"plan": "pro", "seats": 3}, token=TOK)
check("checkout 201", s == 201, f"{s} {res}")
check("plan pro", res.get("plan") == "pro", str(res))
check("seats 3", res.get("seats") == 3, str(res))
check("invoice issued", res.get("invoice", "").startswith("INV-"), str(res.get("invoice")))
check("amount 3 x $12", res.get("amount_cents") == 3600, str(res.get("amount_cents")))

print("== 5. invoices ==")
s, res = call("GET", "/api/billing/invoices", token=TOK)
check("invoices 200", s == 200, str(s))
check("one invoice", res.get("total") == 1, str(res.get("total")))
inv = res["items"][0]
check("invoice paid", inv["status"] == "paid", str(inv["status"]))
check("invoice lines", inv["lines"].get("qty") == 3, str(inv["lines"]))

print("== 6. cancel at period end ==")
s, res = call("POST", "/api/billing/cancel", token=TOK)
check("cancel 200", s == 200, str(s))
check("cancel flag set", res.get("cancel_at_period_end") is True, str(res))
s, sub = call("GET", "/api/billing/subscription", token=TOK)
check("subscription shows cancel flag", sub.get("cancel_at_period_end") is True, str(sub))

print("== 7. limit enforcement (trial plan) ==")
# install CRM so we have an object to create records in
s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))
# downgrade to trial (cap: 5 records)
s, res = call("POST", "/api/billing/checkout", {"plan": "trial", "seats": 1}, token=TOK)
check("downgrade to trial", s == 201, f"{s} {res}")
# create records until the cap bites (trial allows 5 total)
created = 0
blocked_at = None
for i in range(8):
    s, r = call("POST", "/api/records/company", {"data": {"name": f"LimitCo {i}"}}, token=TOK)
    if s in (200, 201):
        created += 1
    else:
        blocked_at = (i, s, r)
        break
check("records created up to cap", created == 5, f"created={created}")
check("6th record blocked 402", blocked_at is not None and blocked_at[1] == 402, str(blocked_at))

print("== 8. upgrade unblocks (business = unlimited) ==")
s, res = call("POST", "/api/billing/checkout", {"plan": "business", "seats": 1}, token=TOK)
check("upgrade to business", s == 201, f"{s} {res}")
s, r = call("POST", "/api/records/company", {"data": {"name": "UnlimitedCo"}}, token=TOK)
check("record creation unblocked", s in (200, 201), f"{s} {r}")
s, usage = call("GET", "/api/billing/usage", token=TOK)
check("business limits unlimited", usage["limits"]["records"] is None, str(usage["limits"]))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
