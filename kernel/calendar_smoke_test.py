"""Phase P smoke test: calendar & scheduling — CRUD, range queries, upcoming.

Verifies:
- create event with attendees + record link
- time validation (bad ISO, end before start)
- list by range [start, end)
- upcoming=N returns future events ordered
- filter by object / record_id
- get / patch / delete
- tenant isolation
- events emitted on create/delete

Idempotent: fresh tenants per run.
"""
import json
import os
import time
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


print("== Phase P: calendar ==")
SUFFIX = str(int(time.time()))
email = f"phasep-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase P",
    "tenant_name": f"Phase P {SUFFIX}", "tenant_slug": f"phasep-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))
s, rec = call("POST", "/api/records/deal", {"data": {"name": "Big Deal", "stage": "Discovery"}}, token=TOK)
check("deal created", s in (200, 201), f"{s} {rec}")
RECID = rec.get("id")

NOW = datetime.now(timezone.utc)

print("== 1. create event ==")
start1 = NOW + timedelta(hours=2)
end1 = NOW + timedelta(hours=3)
s, ev = call("POST", "/api/calendar", {
    "title": "Deal review",
    "description": "Walk through the pipeline",
    "starts_at": iso(start1),
    "ends_at": iso(end1),
    "location": "Zoom",
    "attendees": ["user-a", "user-b"],
    "object": "deal",
    "record_id": RECID,
}, token=TOK)
check("create 201", s == 201, f"{s} {ev}")
EID = ev.get("id")
check("has id", bool(EID), str(ev))
check("starts normalized", ev.get("starts_at", "").startswith(start1.strftime("%Y-%m-%dT%H")), str(ev.get("starts_at")))
check("attendees stored", ev.get("attendees") == ["user-a", "user-b"], str(ev.get("attendees")))
check("record linked", ev.get("record_id") == RECID, str(ev.get("record_id")))

print("== 2. validation ==")
s, res = call("POST", "/api/calendar", {"title": "bad", "starts_at": "not-a-date"}, token=TOK)
check("bad ISO 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/calendar", {
    "title": "backwards", "starts_at": iso(NOW + timedelta(hours=5)), "ends_at": iso(NOW + timedelta(hours=1)),
}, token=TOK)
check("end<start 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/calendar", {"title": "x", "starts_at": iso(NOW), "record_id": "not-a-uuid"}, token=TOK)
check("bad record_id 422", s == 422, f"{s} {res}")

print("== 3. more events for range tests ==")
past = NOW - timedelta(days=2)
tomorrow = NOW + timedelta(days=1)
s, ev_past = call("POST", "/api/calendar", {"title": "Past standup", "starts_at": iso(past)}, token=TOK)
check("past event created", s == 201, f"{s} {ev_past}")
s, ev_tmr = call("POST", "/api/calendar", {"title": "Tomorrow planning", "starts_at": iso(tomorrow)}, token=TOK)
check("tomorrow event created", s == 201, f"{s} {ev_tmr}")

print("== 4. range query ==")
lo = iso(NOW - timedelta(hours=1))
hi = iso(NOW + timedelta(hours=25))  # tomorrow event sits at exactly +24h; keep bound exclusive-safe
s, res = call("GET", f"/api/calendar?start={urllib.parse.quote(lo)}&end={urllib.parse.quote(hi)}", token=TOK)
check("range 200", s == 200, str(s))
titles = [e["title"] for e in res.get("items", [])]
check("range includes future, excludes past", "Deal review" in titles and "Tomorrow planning" in titles and "Past standup" not in titles, str(titles))

print("== 5. upcoming ==")
s, res = call("GET", "/api/calendar?upcoming=10", token=TOK)
check("upcoming 200", s == 200, str(s))
items = res.get("items", [])
check("upcoming excludes past", all(e["title"] != "Past standup" for e in items), str([e["title"] for e in items]))
starts = [e["starts_at"] for e in items]
check("upcoming ordered asc", starts == sorted(starts), str(starts))

print("== 6. filter by object/record ==")
s, res = call("GET", "/api/calendar?object=deal", token=TOK)
check("filter object", res.get("total") == 1 and res["items"][0]["id"] == EID, str(res.get("total")))
s, res = call("GET", f"/api/calendar?record_id={RECID}", token=TOK)
check("filter record", res.get("total") == 1, str(res.get("total")))

print("== 7. get + patch ==")
s, res = call("GET", f"/api/calendar/{EID}", token=TOK)
check("get 200", s == 200 and res.get("title") == "Deal review", f"{s} {res.get('title')}")
new_start = NOW + timedelta(hours=6)
s, res = call("PATCH", f"/api/calendar/{EID}", {"title": "Deal review v2", "starts_at": iso(new_start)}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch title", res.get("title") == "Deal review v2", str(res.get("title")))
check("patch start", res.get("starts_at", "").startswith(new_start.strftime("%Y-%m-%dT%H")), str(res.get("starts_at")))

print("== 8. tenant isolation ==")
email2 = f"phasep2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase P2",
    "tenant_name": f"Phase P2 {SUFFIX}", "tenant_slug": f"phasep2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/calendar", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/calendar/{EID}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print("== 9. delete + events ==")
s, res = call("DELETE", f"/api/calendar/{EID}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/calendar", token=TOK)
check("two remain", res.get("total") == 2, str(res.get("total")))
s, events = call("GET", "/api/events?type=calendar.event_deleted", token=TOK)
check("delete event emitted", len(events) >= 1, str(len(events)))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
