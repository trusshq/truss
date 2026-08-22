"""Phase 3 smoke test: connectors (webhook forwarding + external postgres)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
# Where the KERNEL delivers webhooks (from the kernel's network perspective —
# use host.docker.internal when the kernel runs in a container).
WEBHOOK_RX = os.environ.get("TRUSS_TEST_WEBHOOK_RX", "http://127.0.0.1:9998")
# Where the TEST CLIENT reads back what the receiver got (from the host).
WEBHOOK_RX_CLIENT = os.environ.get("TRUSS_TEST_WEBHOOK_RX_CLIENT", WEBHOOK_RX)
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True, base=BASE):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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

print("== 1. connector types catalog ==")
s, types = call("GET", "/api/connectors/types")
check("types endpoint 200", s == 200, f"{s}")
type_ids = {t["type"] for t in types} if isinstance(types, list) else set()
check("4 types listed", type_ids == {"webhook", "postgres", "s3", "smtp"}, str(type_ids))

print("== 2. create webhook connector ==")
s, wh = call("POST", "/api/connectors", {
    "name": "analytics-sink",
    "type": "webhook",
    "config": {"url": WEBHOOK_RX + "/ingest", "secret": "whsec_test", "events": ["record."]},
    "description": "Forward record events to mock analytics",
})
if s == 409:
    s2, conns = call("GET", "/api/connectors")
    wh = next((c for c in conns if c["name"] == "analytics-sink"), {})
    s = 200
check("webhook connector created", s in (200, 201) and wh.get("type") == "webhook", f"{s} {wh}")
wh_id = wh.get("id")
check("config masked in response", "whsec_test" not in json.dumps(wh), str(wh.get("config")))

print("== 3. invalid configs rejected ==")
s, b = call("POST", "/api/connectors", {"name": "bad1", "type": "webhook", "config": {"url": "not-a-url"}})
check("bad webhook url -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/connectors", {"name": "bad2", "type": "postgres", "config": {"host": "x"}})
check("incomplete postgres -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/connectors", {"name": "bad3", "type": "nope", "config": {}})
check("unknown type -> 422", s == 422, f"{s} {b}")

print("== 4. trigger an event -> webhook delivered ==")
s, lead = call("POST", "/api/records/lead", {
    "data": {"name": "Webhook Test Lead", "email": "wh@example.com", "source": "Website", "status": "New"}
})
check("lead created (fires record.created)", s == 201, f"{s} {lead}")

# give the after_commit delivery a moment
time.sleep(2)
s, received = call("GET", "/received", auth=False, base=WEBHOOK_RX_CLIENT)
received = received if isinstance(received, list) else []
match = [r for r in received if "Webhook Test Lead" in r.get("body", "")]
check("webhook receiver got the event", len(match) >= 1, f"received {len(received)} total")
if match:
    body = json.loads(match[0]["body"])
    check("payload has event type", body.get("type") == "record.created", str(body.get("type")))
    check("signature header present", bool(match[0].get("signature")), str(match[0].get("signature")))

print("== 5. delivery history recorded ==")
s, dels = call("GET", f"/api/connectors/{wh_id}/deliveries")
check("deliveries endpoint 200", s == 200, f"{s}")
ok_del = [d for d in dels if d.get("status") == "success"] if isinstance(dels, list) else []
check("at least one successful delivery", len(ok_del) >= 1, str(dels)[:200])

print("== 6. events filter respected (non-matching not sent) ==")
# count deliveries before/after a plugin event (crm.* doesn't match 'record.' prefix)
before = len(dels) if isinstance(dels, list) else 0
# convert the lead -> fires automation emit_event crm.lead_converted (not record.*)
s, _ = call("PATCH", f"/api/records/lead/{lead['id']}", {"data": {"status": "Converted"}})
time.sleep(2)
s, dels2 = call("GET", f"/api/connectors/{wh_id}/deliveries")
crm_dels = [d for d in dels2 if d.get("event_type") == "crm.lead_converted"] if isinstance(dels2, list) else []
check("crm.lead_converted NOT forwarded (filter)", len(crm_dels) == 0, str(crm_dels))
# but record.updated WAS forwarded
upd_dels = [d for d in dels2 if d.get("event_type") == "record.updated"] if isinstance(dels2, list) else []
check("record.updated forwarded", len(upd_dels) >= 1, str([d.get('event_type') for d in dels2]))

print("== 7. external postgres connector (self -> read-only) ==")
# Point at a reachable Postgres. Defaults match local dev; when the kernel runs
# in Docker, override to the compose db service (host.docker.internal or db).
pg_cfg = {
    "host": os.environ.get("TRUSS_TEST_PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("TRUSS_TEST_PG_PORT", "5432")),
    "database": os.environ.get("TRUSS_TEST_PG_DB", "truss"),
    "user": os.environ.get("TRUSS_TEST_PG_USER", "postgres"),
    "password": os.environ.get("TRUSS_TEST_PG_PASSWORD", "admin"),
}
s, pg = call("POST", "/api/connectors", {
    "name": "external-pg-test",
    "type": "postgres",
    "config": pg_cfg,
    "description": "Point at our own DB to prove the adapter works",
})
if s == 409:
    s2, conns = call("GET", "/api/connectors")
    pg = next((c for c in conns if c["name"] == "external-pg-test"), {})
    s = 200
check("postgres connector created", s in (200, 201), f"{s} {pg}")
pg_id = pg.get("id")

s, t = call("POST", f"/api/connectors/{pg_id}/test")
check("test connection ok", s == 200 and t.get("ok") is True, f"{s} {t}")

s, tables = call("GET", f"/api/connectors/{pg_id}/tables")
check("introspect tables ok", s == 200 and tables.get("ok") is True, f"{s}")
check("sees tenants table", "tenants" in (tables.get("tables") or {}), str(list((tables.get('tables') or {}).keys())[:8]))

s, q = call("POST", f"/api/connectors/{pg_id}/query", {"sql": "SELECT slug, name FROM tenants ORDER BY slug", "limit": 10})
check("read-only query ok", s == 200 and q.get("ok") is True and q.get("row_count", 0) >= 1, f"{s} {q}")

s, q2 = call("POST", f"/api/connectors/{pg_id}/query", {"sql": "DELETE FROM tenants"})
check("non-SELECT rejected", s == 200 and q2.get("ok") is False, f"{s} {q2}")

print("== 8. cleanup test connectors ==")
s, _ = call("DELETE", f"/api/connectors/{wh_id}")
check("webhook connector deleted", s == 204, f"{s}")
s, _ = call("DELETE", f"/api/connectors/{pg_id}")
check("postgres connector deleted", s == 204, f"{s}")

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
