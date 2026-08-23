"""Phase AI smoke test: loyalty — members, points ledger, rewards, redemptions.

Verifies:
- create member (points 0, tier bronze, status active)
- list filters (status, tier)
- get/patch member (status validation)
- points: award (positive), deduct (negative), zero rejected, over-deduct
  rejected, ledger records balance_after, inactive member blocked
- tiers: bronze < 1000, silver >= 1000, gold >= 5000
- rewards: create (cost >= 1), list (active filter, ordered by cost),
  patch, delete (blocked while redemptions exist)
- redemptions: redeem (deducts points, pending), insufficient points
  rejected, inactive member/reward rejected, list filters (status,
  member_id), fulfill (pending only), cancel (pending only, refunds
  points), 409 guards
- events emitted
- delete member cascades
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


print("== Phase AI: loyalty & rewards ==")
SUFFIX = str(int(time.time()))
email = f"phaseai-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AI",
    "tenant_name": f"Phase AI {SUFFIX}", "tenant_slug": f"phaseai-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. members ==")
s, m1 = call("POST", "/api/loyalty/members", {"name": "Alice", "email": "alice@x.com"}, token=TOK)
check("member created 201", s == 201, f"{s} {m1}")
M1 = m1.get("id")
check("points 0", m1.get("points") == 0, str(m1.get("points")))
check("tier bronze", m1.get("tier") == "bronze", str(m1.get("tier")))
check("status active", m1.get("status") == "active", str(m1.get("status")))
s, m2 = call("POST", "/api/loyalty/members", {"name": "Bob"}, token=TOK)
M2 = m2.get("id")
s, res = call("GET", "/api/loyalty/members", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/loyalty/members?status=active", token=TOK)
check("status filter", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/loyalty/members?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))
# patch member
s, pm = call("PATCH", f"/api/loyalty/members/{M2}", {"phone": "555-0100"}, token=TOK)
check("patch member 200", s == 200, str(s))
check("phone set", pm.get("phone") == "555-0100", str(pm.get("phone")))
s, _ = call("PATCH", f"/api/loyalty/members/{M2}", {"status": "bogus"}, token=TOK)
check("patch bad status 400", s == 400, str(s))

print("== 2. points + tiers ==")
s, ev1 = call("POST", f"/api/loyalty/members/{M1}/points", {"delta": 500, "reason": "Welcome bonus"}, token=TOK)
check("award 500 201", s == 201, f"{s} {ev1}")
check("balance_after 500", ev1.get("balance_after") == 500, str(ev1.get("balance_after")))
s, _ = call("POST", f"/api/loyalty/members/{M1}/points", {"delta": 0}, token=TOK)
check("zero delta 400", s == 400, str(s))
s, _ = call("POST", f"/api/loyalty/members/{M1}/points", {"delta": -9999}, token=TOK)
check("over-deduct 400", s == 400, str(s))
# push to silver (>= 1000)
s, _ = call("POST", f"/api/loyalty/members/{M1}/points", {"delta": 600, "reason": "Purchase"}, token=TOK)
s, got = call("GET", f"/api/loyalty/members/{M1}", token=TOK)
check("points 1100", got.get("points") == 1100, str(got.get("points")))
check("tier silver", got.get("tier") == "silver", str(got.get("tier")))
# push to gold (>= 5000)
s, _ = call("POST", f"/api/loyalty/members/{M1}/points", {"delta": 4000, "reason": "Big spend"}, token=TOK)
s, got = call("GET", f"/api/loyalty/members/{M1}", token=TOK)
check("tier gold", got.get("tier") == "gold", str(got.get("tier")))
# tier filter
s, res = call("GET", "/api/loyalty/members?tier=gold", token=TOK)
check("tier filter gold", res.get("total") == 1, str(res.get("total")))
# ledger
s, ledger = call("GET", f"/api/loyalty/members/{M1}/points", token=TOK)
check("ledger total 3", ledger.get("total") == 3, str(ledger.get("total")))
# inactive member blocked
s, _ = call("PATCH", f"/api/loyalty/members/{M2}", {"status": "inactive"}, token=TOK)
s, _ = call("POST", f"/api/loyalty/members/{M2}/points", {"delta": 10}, token=TOK)
check("inactive points 409", s == 409, str(s))
s, _ = call("PATCH", f"/api/loyalty/members/{M2}", {"status": "active"}, token=TOK)

print("== 3. rewards ==")
s, rw1 = call("POST", "/api/loyalty/rewards", {"name": "Free coffee", "points_cost": 200}, token=TOK)
check("reward created 201", s == 201, f"{s} {rw1}")
RW1 = rw1.get("id")
s, rw2 = call("POST", "/api/loyalty/rewards", {"name": "Gift card", "points_cost": 1000}, token=TOK)
RW2 = rw2.get("id")
s, _ = call("POST", "/api/loyalty/rewards", {"name": "X", "points_cost": 0}, token=TOK)
check("cost 0 rejected 422", s == 422, str(s))
s, res = call("GET", "/api/loyalty/rewards", token=TOK)
check("rewards total 2", res.get("total") == 2, str(res.get("total")))
check("ordered by cost", [r["points_cost"] for r in res["items"]] == [200, 1000], str([r["points_cost"] for r in res["items"]]))
s, res = call("GET", "/api/loyalty/rewards?active=true", token=TOK)
check("active filter", res.get("total") == 2, str(res.get("total")))
# patch reward
s, prw = call("PATCH", f"/api/loyalty/rewards/{RW2}", {"points_cost": 900}, token=TOK)
check("patch reward 200", s == 200, str(s))
check("cost updated", prw.get("points_cost") == 900, str(prw.get("points_cost")))

print("== 4. redemptions ==")
# M1 has 5100 points; redeem coffee (200)
s, rd1 = call("POST", "/api/loyalty/redemptions", {"member_id": M1, "reward_id": RW1}, token=TOK)
check("redeem 201", s == 201, f"{s} {rd1}")
RD1 = rd1.get("id")
check("points_spent 200", rd1.get("points_spent") == 200, str(rd1.get("points_spent")))
check("status pending", rd1.get("status") == "pending", str(rd1.get("status")))
s, got = call("GET", f"/api/loyalty/members/{M1}", token=TOK)
check("balance 4900 after redeem", got.get("points") == 4900, str(got.get("points")))
# insufficient points (M2 has 0)
s, _ = call("POST", "/api/loyalty/redemptions", {"member_id": M2, "reward_id": RW1}, token=TOK)
check("insufficient points 400", s == 400, str(s))
# bad uuid
s, _ = call("POST", "/api/loyalty/redemptions", {"member_id": "nope", "reward_id": RW1}, token=TOK)
check("bad member uuid 400", s == 400, str(s))
# inactive reward blocked
s, rw3 = call("POST", "/api/loyalty/rewards", {"name": "Retired", "points_cost": 50}, token=TOK)
RW3 = rw3.get("id")
s, _ = call("PATCH", f"/api/loyalty/rewards/{RW3}", {"active": False}, token=TOK)
s, _ = call("POST", "/api/loyalty/redemptions", {"member_id": M1, "reward_id": RW3}, token=TOK)
check("inactive reward 409", s == 409, str(s))
# list filters
s, res = call("GET", "/api/loyalty/redemptions", token=TOK)
check("redemptions total 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/loyalty/redemptions?status=pending", token=TOK)
check("status filter pending", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", f"/api/loyalty/redemptions?member_id={M1}", token=TOK)
check("member filter", res.get("total") == 1, str(res.get("total")))
# fulfill
s, ff = call("POST", f"/api/loyalty/redemptions/{RD1}/fulfill", {}, token=TOK)
check("fulfill 200", s == 200, str(s))
check("status fulfilled", ff.get("status") == "fulfilled", str(ff.get("status")))
s, _ = call("POST", f"/api/loyalty/redemptions/{RD1}/fulfill", {}, token=TOK)
check("re-fulfill 409", s == 409, str(s))
# cancel a new redemption -> refund
s, rd2 = call("POST", "/api/loyalty/redemptions", {"member_id": M1, "reward_id": RW1}, token=TOK)
RD2 = rd2.get("id")
s, got = call("GET", f"/api/loyalty/members/{M1}", token=TOK)
bal_before = got.get("points")
s, cc = call("POST", f"/api/loyalty/redemptions/{RD2}/cancel", {}, token=TOK)
check("cancel 200", s == 200, str(s))
check("status cancelled", cc.get("status") == "cancelled", str(cc.get("status")))
s, got = call("GET", f"/api/loyalty/members/{M1}", token=TOK)
check("points refunded", got.get("points") == bal_before + 200, f"{got.get('points')} vs {bal_before + 200}")
s, _ = call("POST", f"/api/loyalty/redemptions/{RD2}/cancel", {}, token=TOK)
check("re-cancel 409", s == 409, str(s))
# reward delete blocked by redemptions
s, _ = call("DELETE", f"/api/loyalty/rewards/{RW1}", token=TOK)
check("delete reward w/ redemptions 409", s == 409, str(s))
# reward with no redemptions deletes fine
s, _ = call("DELETE", f"/api/loyalty/rewards/{RW3}", token=TOK)
check("delete unused reward 200", s == 200, str(s))

print("== 5. events + delete + isolation ==")
for ev in ("loyalty.member_created", "loyalty.points_adjusted", "loyalty.reward_created",
           "loyalty.redeemed", "loyalty.redemption_fulfilled", "loyalty.redemption_cancelled"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/loyalty/members/{M2}", token=TOK)
check("delete member 200", s == 200, str(s))
s, res = call("GET", "/api/loyalty/members", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseai2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AI2",
    "tenant_name": f"Phase AI2 {SUFFIX}", "tenant_slug": f"phaseai2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/loyalty/members", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/loyalty/members/{M1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
