"""Phase R smoke test: time tracking — entries, live timers, summaries.

Verifies:
- log a completed entry (duration auto-computed from start/stop)
- explicit duration honored; stop<start rejected
- live timer: start -> running, only one per user (starting a 2nd stops the 1st)
- stop timer computes duration; stopping a stopped entry 409s
- list filters: running, object, record_id, range
- summary aggregates total/by_object/by_user (completed only)
- patch + delete + events
- tenant isolation

Idempotent: fresh tenants per run.
"""
import json
import os
import time as _time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

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


def iso(dt):
    return dt.isoformat()


print("== Phase R: time tracking ==")
SUFFIX = str(int(_time.time()))
email = f"phaser-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase R",
    "tenant_name": f"Phase R {SUFFIX}", "tenant_slug": f"phaser-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))
s, rec = call("POST", "/api/records/deal", {"data": {"name": "Timed Deal", "stage": "Proposal"}}, token=TOK)
check("deal created", s in (200, 201), f"{s} {rec}")
RECID = rec.get("id")

NOW = datetime.now(timezone.utc)

print("== 1. log completed entry (auto duration) ==")
start = NOW - timedelta(hours=2)
stop = NOW - timedelta(minutes=30)
s, e1 = call("POST", "/api/time", {
    "description": "Discovery call prep",
    "started_at": iso(start),
    "stopped_at": iso(stop),
    "object": "deal",
    "record_id": RECID,
}, token=TOK)
check("create 201", s == 201, f"{s} {e1}")
EID1 = e1.get("id")
check("duration auto = 90", e1.get("duration_minutes") == 90, str(e1.get("duration_minutes")))
check("not running", e1.get("running") is False, str(e1.get("running")))
check("record linked", e1.get("record_id") == RECID, str(e1.get("record_id")))

print("== 2. explicit duration + validation ==")
s, e2 = call("POST", "/api/time", {
    "description": "Manual log", "started_at": iso(NOW - timedelta(hours=5)),
    "stopped_at": iso(NOW - timedelta(hours=4)), "duration_minutes": 45,
}, token=TOK)
check("explicit duration honored", s == 201 and e2.get("duration_minutes") == 45, f"{s} {e2.get('duration_minutes')}")
s, res = call("POST", "/api/time", {
    "description": "backwards", "started_at": iso(NOW), "stopped_at": iso(NOW - timedelta(hours=1)),
}, token=TOK)
check("stop<start 422", s == 422, f"{s} {res}")

print("== 3. live timer ==")
s, t1 = call("POST", "/api/time/timer/start", {"description": "Working on proposal", "object": "deal", "record_id": RECID}, token=TOK)
check("timer start 201", s == 201, f"{s} {t1}")
TID1 = t1.get("id")
check("timer running", t1.get("running") is True, str(t1.get("running")))
check("timer duration 0", t1.get("duration_minutes") == 0, str(t1.get("duration_minutes")))

# only one running timer per user: starting a 2nd stops the 1st
_time.sleep(1)
s, t2 = call("POST", "/api/time/timer/start", {"description": "Switched task"}, token=TOK)
check("second timer start 201", s == 201, f"{s} {t2}")
TID2 = t2.get("id")
s, res = call("GET", f"/api/time/{TID1}", token=TOK)
check("first timer auto-stopped", res.get("running") is False, str(res.get("running")))
check("first timer has duration", res.get("duration_minutes") is not None, str(res.get("duration_minutes")))

print("== 4. stop timer ==")
s, res = call("POST", f"/api/time/{TID2}/timer/stop", token=TOK)
check("stop 200", s == 200, f"{s} {res}")
check("stopped not running", res.get("running") is False, str(res.get("running")))
check("stopped has duration", res.get("duration_minutes") is not None, str(res.get("duration_minutes")))
s, res = call("POST", f"/api/time/{TID2}/timer/stop", token=TOK)
check("double stop 409", s == 409, f"{s} {res}")

print("== 5. list filters ==")
s, res = call("GET", "/api/time", token=TOK)
check("list all = 4", res.get("total") == 4, str(res.get("total")))
s, res = call("GET", "/api/time?running=true", token=TOK)
check("running filter = 0", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", "/api/time?object=deal", token=TOK)
check("object filter = 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/time?record_id={RECID}", token=TOK)
check("record filter = 2", res.get("total") == 2, str(res.get("total")))
lo = iso(NOW - timedelta(hours=3))
hi = iso(NOW + timedelta(hours=1))
s, res = call("GET", f"/api/time?start={urllib.parse.quote(lo)}&end={urllib.parse.quote(hi)}", token=TOK)
check("range filter >= 2", res.get("total") >= 2, str(res.get("total")))

print("== 6. summary ==")
s, res = call("GET", "/api/time/summary", token=TOK)
check("summary 200", s == 200, str(s))
check("summary counts completed only", res.get("entries") == 4, str(res.get("entries")))
check("summary total > 0", res.get("total_minutes", 0) > 0, str(res.get("total_minutes")))
check("summary by_object has deal", any(r["label"] == "deal" for r in res.get("by_object", [])), str(res.get("by_object")))
check("summary by_user present", len(res.get("by_user", [])) >= 1, str(res.get("by_user")))

print("== 7. patch + delete ==")
s, res = call("PATCH", f"/api/time/{EID1}", {"description": "Updated prep", "notes": "billable"}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch description", res.get("description") == "Updated prep", str(res.get("description")))
check("patch notes", res.get("notes") == "billable", str(res.get("notes")))
s, res = call("DELETE", f"/api/time/{EID1}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/time", token=TOK)
check("three remain", res.get("total") == 3, str(res.get("total")))
s, events = call("GET", "/api/events?type=time.entry_deleted", token=TOK)
check("delete event emitted", len(events) >= 1, str(len(events)))

print("== 8. tenant isolation ==")
email2 = f"phaser2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase R2",
    "tenant_name": f"Phase R2 {SUFFIX}", "tenant_slug": f"phaser2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/time", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/time/{TID2}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
