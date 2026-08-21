"""Phase 2 smoke test: automation engine fires declared rules off the event bus."""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


print("== 0. login ==")
s, b = call("POST", "/api/auth/login", {"email": "owner@acme-demo.dev", "password": "password123"}, auth=False)
check("login ok", s == 200 and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access_token")

print("== 1. declared rules visible ==")
s, rules = call("GET", "/api/automations")
check("rules endpoint 200", s == 200, f"{s}")
lead_rule = next((r for r in rules if r["slug"] == "lead_converted_event"), None) if isinstance(rules, list) else None
check("lead_converted_event declared", lead_rule is not None, str(rules)[:200])

print("== 2. create a lead, then convert it ==")
s, lead = call("POST", "/api/records/lead", {
    "data": {"name": "Automation Test Lead", "email": "auto@example.com", "source": "Website", "status": "New"}
})
check("lead created", s == 201, f"{s} {lead}")
lead_id = lead.get("id")

s, upd = call("PATCH", f"/api/records/lead/{lead_id}", {"data": {"status": "Converted"}})
check("lead converted", s == 200 and upd.get("data", {}).get("status") == "Converted", f"{s} {upd}")

print("== 3. automation fired: crm.lead_converted event exists ==")
s, ev = call("GET", "/api/events?limit=100")
items = ev if isinstance(ev, list) else ev.get("items", [])
conv = [e for e in items if e.get("type") == "crm.lead_converted"]
check("crm.lead_converted emitted", len(conv) >= 1, f"types seen: {[e.get('type') for e in items[:10]]}")
if conv:
    check("event carries record context", conv[0].get("payload", {}).get("record_id") == lead_id, str(conv[0].get("payload")))

print("== 4. run history recorded ==")
s, runs = call("GET", "/api/automations/runs")
check("runs endpoint 200", s == 200, f"{s}")
run = next((r for r in runs if r["automation_slug"] == "lead_converted_event"), None) if isinstance(runs, list) else None
check("run recorded", run is not None, str(runs)[:200])
if run:
    check("run status success", run.get("status") == "success", str(run))

print("== 5. non-matching update does NOT fire ==")
s, lead2 = call("POST", "/api/records/lead", {
    "data": {"name": "No Fire Lead", "email": "nofire@example.com", "source": "Referral", "status": "New"}
})
s, _ = call("PATCH", f"/api/records/lead/{lead2['id']}", {"data": {"status": "Contacted"}})
s, runs2 = call("GET", "/api/automations/runs")
contact_runs = [r for r in runs2 if r.get("detail", {}).get("results") and
                any(res.get("emitted") == "crm.lead_converted" for res in r["detail"]["results"])
                and r["created_at"] > (run["created_at"] if run else "")]
# simpler: count total lead_converted events — should still be exactly 1 from our conversion
s, ev2 = call("GET", "/api/events?limit=100")
items2 = ev2 if isinstance(ev2, list) else ev2.get("items", [])
conv2 = [e for e in items2 if e.get("type") == "crm.lead_converted"]
check("no extra firing on Contacted", len(conv2) == len(conv), f"{len(conv2)} vs {len(conv)}")

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
