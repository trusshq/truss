"""Phase K smoke test: audit log & reports — filtered history, actor resolution, CSV export.

Verifies:
- GET /api/audit returns events with summaries + resolved actor names
- type-prefix filter works (record.* only)
- actor filter works
- CSV export returns proper headers + rows
- pagination (limit/offset)

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


def call_text(method, path, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), ""


print("== Phase K: audit log & reports ==")
SUFFIX = str(int(time.time()))
email = f"phasek-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase K Auditor",
    "tenant_name": f"Phase K {SUFFIX}", "tenant_slug": f"phasek-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. generate activity ==")
s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))
s, rec = call("POST", "/api/records/company", {"data": {"name": "AuditCo", "industry": "Software"}}, token=TOK)
check("record created", s in (200, 201), str(s))

print("== 2. audit listing with summaries + actor names ==")
s, res = call("GET", "/api/audit?limit=100", token=TOK)
check("audit 200", s == 200, str(s))
items = res.get("items", [])
check("has events", len(items) > 0, str(len(items)))
types = {i["type"] for i in items}
check("record.created present", "record.created" in types, str(types))
check("plugin.installed present", "plugin.installed" in types, str(types))
# actor resolution: the signup user's full_name should appear
actor_names = {i["actor_name"] for i in items}
check("actor name resolved", "Phase K Auditor" in actor_names, str(actor_names))
# summaries are human-readable
rec_evt = next((i for i in items if i["type"] == "record.created"), None)
check("summary human-readable", rec_evt is not None and "created a record" in rec_evt["summary"], str(rec_evt))

print("== 3. type-prefix filter ==")
s, res = call("GET", "/api/audit?type=record", token=TOK)
check("filter 200", s == 200, str(s))
filt_types = {i["type"] for i in res.get("items", [])}
check("only record.* types", filt_types and all(t.startswith("record") for t in filt_types), str(filt_types))

print("== 4. actor filter ==")
# find my own user id from an event I caused
my_actor = rec_evt["actor_id"] if rec_evt else None
if my_actor:
    s, res = call("GET", f"/api/audit?actor={my_actor}", token=TOK)
    check("actor filter 200", s == 200, str(s))
    check("actor filter returns rows", len(res.get("items", [])) > 0, str(len(res.get("items", []))))
    check("all rows same actor", all(i["actor_id"] == my_actor for i in res.get("items", [])), "")
else:
    check("actor filter (skipped, no actor)", False, "no actor_id on record.created")

print("== 5. CSV export ==")
s, text, ctype = call_text("GET", "/api/audit/export.csv", token=TOK)
check("csv 200", s == 200, str(s))
check("csv content-type", "text/csv" in ctype, ctype)
lines = [l for l in text.strip().splitlines() if l]
check("csv has header", lines and lines[0].startswith("created_at,type,summary,actor"), lines[0] if lines else "")
check("csv has data rows", len(lines) > 1, str(len(lines)))
check("csv mentions record.created", any("record.created" in l for l in lines), "")

print("== 6. pagination ==")
s, res = call("GET", "/api/audit?limit=2&offset=0", token=TOK)
check("limit respected", s == 200 and len(res.get("items", [])) <= 2, str(len(res.get("items", []))))
first_page = [i["id"] for i in res.get("items", [])]
s, res2 = call("GET", "/api/audit?limit=2&offset=2", token=TOK)
second_page = [i["id"] for i in res2.get("items", [])]
check("offset advances", not (set(first_page) & set(second_page)), f"{first_page} vs {second_page}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
