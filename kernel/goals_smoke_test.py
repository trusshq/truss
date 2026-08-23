"""Phase AG smoke test: goals & OKRs — key results, progress rollup, lifecycle.

Verifies:
- create goal (draft status, owner validation)
- list filters (status, period)
- get/patch (finished goals locked)
- key results: create (target > 0, weight >= 1), list, patch, delete;
  finished goals locked from KR changes
- progress rollup: weighted average of capped completions
- lifecycle: activate (draft + requires >= 1 KR), achieve (active only),
  miss (active only), cancel (draft/active), 409 guards
- events emitted
- delete (admin) cascades key results
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


print("== Phase AG: goals & OKRs ==")
SUFFIX = str(int(time.time()))
email = f"phaseag-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AG",
    "tenant_name": f"Phase AG {SUFFIX}", "tenant_slug": f"phaseag-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create goal ==")
s, g = call("POST", "/api/goals", {
    "title": "Grow revenue", "description": "Double MRR this quarter",
    "period": "2026-Q3",
}, token=TOK)
check("goal created 201", s == 201, f"{s} {g}")
G1 = g.get("id")
check("status draft", g.get("status") == "draft", str(g.get("status")))
check("progress 0 with no KRs", g.get("progress") == 0.0, str(g.get("progress")))
# bad owner
s, _ = call("POST", "/api/goals", {"title": "X", "owner_id": "not-a-uuid"}, token=TOK)
check("bad owner 400", s == 400, str(s))

print("== 2. list filters ==")
s, g2 = call("POST", "/api/goals", {"title": "Ship v2", "period": "2026-Q4"}, token=TOK)
G2 = g2.get("id")
s, res = call("GET", "/api/goals", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/goals?period=2026-Q3", token=TOK)
check("period filter", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/goals?status=draft", token=TOK)
check("status filter draft", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/goals?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 3. key results ==")
s, kr1 = call("POST", f"/api/goals/{G1}/key-results", {
    "title": "Reach 100 customers", "unit": "customers",
    "target_value": 100, "current_value": 50, "weight": 2,
}, token=TOK)
check("KR created 201", s == 201, f"{s} {kr1}")
KR1 = kr1.get("id")
check("KR completion 50%", kr1.get("completion") == 50.0, str(kr1.get("completion")))
s, kr2 = call("POST", f"/api/goals/{G1}/key-results", {
    "title": "Hit $20k MRR", "unit": "$",
    "target_value": 20000, "current_value": 25000, "weight": 1,
}, token=TOK)
KR2 = kr2.get("id")
check("KR capped at 100%", kr2.get("completion") == 100.0, str(kr2.get("completion")))
# validation
s, _ = call("POST", f"/api/goals/{G1}/key-results", {"title": "X", "target_value": 0}, token=TOK)
check("target 0 rejected 422", s == 422, str(s))
s, _ = call("POST", f"/api/goals/{G1}/key-results", {"title": "X", "weight": 0}, token=TOK)
check("weight 0 rejected 422", s == 422, str(s))

print("== 4. progress rollup ==")
# weighted: (50% * 2 + 100% * 1) / 3 = 66.67
s, got = call("GET", f"/api/goals/{G1}", token=TOK)
check("progress weighted 66.67", got.get("progress") == 66.67, str(got.get("progress")))
check("2 KRs embedded", len(got.get("key_results", [])) == 2, str(len(got.get("key_results", []))))
# update KR current -> progress moves
s, _ = call("PATCH", f"/api/goals/key-results/{KR1}", {"current_value": 100}, token=TOK)
s, got = call("GET", f"/api/goals/{G1}", token=TOK)
check("progress 100 after KR update", got.get("progress") == 100.0, str(got.get("progress")))

print("== 5. KR list + delete ==")
s, krs = call("GET", f"/api/goals/{G1}/key-results", token=TOK)
check("KR list total 2", krs.get("total") == 2, str(krs.get("total")))
s, kr3 = call("POST", f"/api/goals/{G2}/key-results", {"title": "Temp KR"}, token=TOK)
s, _ = call("DELETE", f"/api/goals/key-results/{kr3['id']}", token=TOK)
check("delete KR 200", s == 200, str(s))

print("== 6. lifecycle guards ==")
# activate requires >= 1 KR (G2 has none now)
s, _ = call("POST", f"/api/goals/{G2}/activate", {}, token=TOK)
check("activate w/o KR 400", s == 400, str(s))
# can't achieve a draft
s, _ = call("POST", f"/api/goals/{G1}/achieve", {}, token=TOK)
check("achieve draft 409", s == 409, str(s))
# activate G1
s, act = call("POST", f"/api/goals/{G1}/activate", {}, token=TOK)
check("activate 200", s == 200, str(s))
check("status active", act.get("status") == "active", str(act.get("status")))
# can't re-activate
s, _ = call("POST", f"/api/goals/{G1}/activate", {}, token=TOK)
check("re-activate 409", s == 409, str(s))
# achieve it
s, ach = call("POST", f"/api/goals/{G1}/achieve", {}, token=TOK)
check("achieve 200", s == 200, str(s))
check("status achieved", ach.get("status") == "achieved", str(ach.get("status")))
# achieved locked from edit
s, _ = call("PATCH", f"/api/goals/{G1}", {"title": "New"}, token=TOK)
check("edit achieved 409", s == 409, str(s))
# achieved locked from KR add
s, _ = call("POST", f"/api/goals/{G1}/key-results", {"title": "X"}, token=TOK)
check("add KR to achieved 409", s == 409, str(s))
# achieved locked from KR edit
s, _ = call("PATCH", f"/api/goals/key-results/{KR1}", {"current_value": 5}, token=TOK)
check("edit KR on achieved 409", s == 409, str(s))
# can't re-achieve
s, _ = call("POST", f"/api/goals/{G1}/achieve", {}, token=TOK)
check("re-achieve 409", s == 409, str(s))

print("== 7. miss + cancel ==")
s, kr4 = call("POST", f"/api/goals/{G2}/key-results", {"title": "Ship it"}, token=TOK)
s, _ = call("POST", f"/api/goals/{G2}/activate", {}, token=TOK)
s, ms = call("POST", f"/api/goals/{G2}/miss", {}, token=TOK)
check("miss 200", s == 200, str(s))
check("status missed", ms.get("status") == "missed", str(ms.get("status")))
# cancel a draft
s, g3 = call("POST", "/api/goals", {"title": "Dropped"}, token=TOK)
s, cn = call("POST", f"/api/goals/{g3['id']}/cancel", {}, token=TOK)
check("cancel draft 200", s == 200, str(s))
check("status cancelled", cn.get("status") == "cancelled", str(cn.get("status")))
# can't re-cancel
s, _ = call("POST", f"/api/goals/{g3['id']}/cancel", {}, token=TOK)
check("re-cancel 409", s == 409, str(s))

print("== 8. events + delete cascade + isolation ==")
for ev in ("goal.created", "goal.activated", "goal.achieved", "goal.missed", "goal.cancelled", "goal.key_result_created"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/goals/{G1}", token=TOK)
check("delete goal 200", s == 200, str(s))
s, res = call("GET", "/api/goals", token=TOK)
check("two remain after delete", res.get("total") == 2, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseag2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AG2",
    "tenant_name": f"Phase AG2 {SUFFIX}", "tenant_slug": f"phaseag2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/goals", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/goals/{G2}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
