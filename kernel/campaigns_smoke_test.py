"""Phase AC smoke test: campaigns — CRUD, lifecycle, performance tracking.

Verifies:
- create campaign (channel validation, draft status)
- list filters (status, channel)
- get/patch (only draft editable)
- lifecycle: schedule (draft + requires scheduled_for), send (draft/scheduled,
  sets sent_count = audience_size), complete (sent only), 409 guards
- performance: increment open/click, clamped to sent/opened, rates computed
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


print("== Phase AC: campaigns ==")
SUFFIX = str(int(time.time()))
email = f"phaseac-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AC",
    "tenant_name": f"Phase AC {SUFFIX}", "tenant_slug": f"phaseac-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create campaign ==")
s, c = call("POST", "/api/campaigns", {
    "name": "Summer Sale", "channel": "email", "subject": "50% off",
    "content": "Big discounts inside", "audience": "all active customers",
    "audience_size": 1000, "scheduled_for": "2026-09-01T09:00:00Z",
}, token=TOK)
check("campaign created 201", s == 201, f"{s} {c}")
CID = c.get("id")
check("status draft", c.get("status") == "draft", str(c.get("status")))
check("channel email", c.get("channel") == "email", str(c.get("channel")))
check("audience_size 1000", c.get("audience_size") == 1000, str(c.get("audience_size")))

print("== 2. channel validation ==")
s, _ = call("POST", "/api/campaigns", {"name": "X", "channel": "pigeon"}, token=TOK)
check("bad channel 400", s == 400, str(s))

print("== 3. list + filters ==")
s, res = call("GET", "/api/campaigns", token=TOK)
check("list total 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/campaigns?channel=email", token=TOK)
check("channel filter email", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/campaigns?status=draft", token=TOK)
check("status filter draft", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/campaigns?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 4. lifecycle guards ==")
# can't complete a draft
s, _ = call("POST", f"/api/campaigns/{CID}/complete", {}, token=TOK)
check("complete draft 409", s == 409, str(s))
# can't record performance on draft
s, _ = call("POST", f"/api/campaigns/{CID}/performance", {"opened": 5}, token=TOK)
check("perf draft 409", s == 409, str(s))
# schedule it
s, sch = call("POST", f"/api/campaigns/{CID}/schedule", {}, token=TOK)
check("schedule 200", s == 200, str(s))
check("status scheduled", sch.get("status") == "scheduled", str(sch.get("status")))
# can't edit scheduled
s, _ = call("PATCH", f"/api/campaigns/{CID}", {"name": "New"}, token=TOK)
check("edit scheduled 409", s == 409, str(s))
# send it
s, sent = call("POST", f"/api/campaigns/{CID}/send", {}, token=TOK)
check("send 200", s == 200, str(s))
check("status sent", sent.get("status") == "sent", str(sent.get("status")))
check("sent_at stamped", bool(sent.get("sent_at")), str(sent.get("sent_at")))
check("sent_count = audience_size 1000", sent.get("sent_count") == 1000, str(sent.get("sent_count")))

print("== 5. performance tracking ==")
s, perf = call("POST", f"/api/campaigns/{CID}/performance", {"opened": 200, "clicked": 50}, token=TOK)
check("perf 200", s == 200, f"{s} {perf}")
check("opened 200", perf.get("opened_count") == 200, str(perf.get("opened_count")))
check("clicked 50", perf.get("clicked_count") == 50, str(perf.get("clicked_count")))
check("open_rate 20.0", perf.get("open_rate") == 20.0, str(perf.get("open_rate")))
check("click_rate 5.0", perf.get("click_rate") == 5.0, str(perf.get("click_rate")))
# clamp: opened can't exceed sent
s, perf2 = call("POST", f"/api/campaigns/{CID}/performance", {"opened": 5000, "clicked": 0}, token=TOK)
check("opened clamped to sent", perf2.get("opened_count") == 1000, str(perf2.get("opened_count")))
# clamp: clicked can't exceed opened
s, perf3 = call("POST", f"/api/campaigns/{CID}/performance", {"opened": 0, "clicked": 9999}, token=TOK)
check("clicked clamped to opened", perf3.get("clicked_count") == 1000, str(perf3.get("clicked_count")))

print("== 6. complete ==")
s, comp = call("POST", f"/api/campaigns/{CID}/complete", {}, token=TOK)
check("complete 200", s == 200, str(s))
check("status completed", comp.get("status") == "completed", str(comp.get("status")))
# can't re-send completed
s, _ = call("POST", f"/api/campaigns/{CID}/send", {}, token=TOK)
check("re-send completed 409", s == 409, str(s))

print("== 7. schedule requires scheduled_for ==")
s, c2 = call("POST", "/api/campaigns", {"name": "No date", "channel": "sms"}, token=TOK)
s, _ = call("POST", f"/api/campaigns/{c2['id']}/schedule", {}, token=TOK)
check("schedule w/o date 400", s == 400, str(s))

print("== 8. events + delete + isolation ==")
for ev in ("campaign.created", "campaign.scheduled", "campaign.sent", "campaign.performance", "campaign.completed"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/campaigns/{c2['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/campaigns", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseac2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AC2",
    "tenant_name": f"Phase AC2 {SUFFIX}", "tenant_slug": f"phaseac2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/campaigns", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/campaigns/{CID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
