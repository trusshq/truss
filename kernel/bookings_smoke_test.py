"""Phase AF smoke test: bookings — services, scheduling, overlap guard, lifecycle.

Verifies:
- create service (duration bounds, price in cents)
- services list/get/patch/delete (delete blocked while bookings exist)
- create booking (active service only, bad service 404, end computed from
  duration, bad start_at 400)
- overlap guard: double-booking same slot 409, adjacent slot ok, cancelled
  booking frees the slot
- list filters (status, service_id)
- lifecycle: confirm (pending only), complete (confirmed only), cancel
  (pending/confirmed), no-show (confirmed only), 409 guards
- finished bookings locked from edit
- patch reschedule re-checks overlap
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


print("== Phase AF: bookings ==")
SUFFIX = str(int(time.time()))
email = f"phaseaf-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AF",
    "tenant_name": f"Phase AF {SUFFIX}", "tenant_slug": f"phaseaf-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create services ==")
s, sv = call("POST", "/api/bookings/services", {
    "name": "Consultation", "duration_minutes": 60, "price_cents": 15000,
}, token=TOK)
check("service created 201", s == 201, f"{s} {sv}")
SV = sv.get("id")
check("duration 60", sv.get("duration_minutes") == 60, str(sv.get("duration_minutes")))
s, _ = call("POST", "/api/bookings/services", {"name": "X", "duration_minutes": 2}, token=TOK)
check("duration < 5 rejected 422", s == 422, str(s))
s, _ = call("POST", "/api/bookings/services", {"name": "X", "duration_minutes": 999}, token=TOK)
check("duration > 480 rejected 422", s == 422, str(s))

print("== 2. services list/get/patch ==")
s, res = call("GET", "/api/bookings/services", token=TOK)
check("services total 1", res.get("total") == 1, str(res.get("total")))
s, got = call("GET", f"/api/bookings/services/{SV}", token=TOK)
check("get service", got.get("name") == "Consultation", str(got.get("name")))
s, upd = call("PATCH", f"/api/bookings/services/{SV}", {"price_cents": 20000}, token=TOK)
check("patch service price", upd.get("price_cents") == 20000, str(upd.get("price_cents")))

print("== 3. create booking ==")
s, bk = call("POST", "/api/bookings", {
    "service_id": SV, "customer_name": "Jane Doe", "customer_email": "jane@example.com",
    "start_at": "2026-09-01T10:00:00+00:00", "notes": "First visit",
}, token=TOK)
check("booking created 201", s == 201, f"{s} {bk}")
B1 = bk.get("id")
check("status pending", bk.get("status") == "pending", str(bk.get("status")))
check("end = start + 60min", bk.get("end_at") == "2026-09-01T11:00:00+00:00", str(bk.get("end_at")))
# bad service
s, _ = call("POST", "/api/bookings", {"service_id": "00000000-0000-0000-0000-000000000000", "customer_name": "X", "start_at": "2026-09-02T10:00:00+00:00"}, token=TOK)
check("bad service 404", s == 404, str(s))
# bad start_at
s, _ = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "X", "start_at": "not-a-date"}, token=TOK)
check("bad start_at 400", s == 400, str(s))
# inactive service blocked
s, sv2 = call("POST", "/api/bookings/services", {"name": "Legacy", "active": False}, token=TOK)
s, _ = call("POST", "/api/bookings", {"service_id": sv2["id"], "customer_name": "X", "start_at": "2026-09-03T10:00:00+00:00"}, token=TOK)
check("inactive service 409", s == 409, str(s))

print("== 4. overlap guard ==")
# same slot -> 409
s, _ = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "John", "start_at": "2026-09-01T10:30:00+00:00"}, token=TOK)
check("overlapping slot 409", s == 409, str(s))
# adjacent slot (starts exactly at end) -> ok
s, bk2 = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "Adjacent", "start_at": "2026-09-01T11:00:00+00:00"}, token=TOK)
check("adjacent slot ok 201", s == 201, str(s))
B2 = bk2.get("id")

print("== 5. list filters ==")
s, res = call("GET", "/api/bookings", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/bookings?status=pending", token=TOK)
check("status filter pending", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/bookings?service_id={SV}", token=TOK)
check("service filter", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/bookings?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 6. lifecycle guards ==")
# can't complete a pending booking
s, _ = call("POST", f"/api/bookings/{B1}/complete", {}, token=TOK)
check("complete pending 409", s == 409, str(s))
# confirm it
s, cf = call("POST", f"/api/bookings/{B1}/confirm", {}, token=TOK)
check("confirm 200", s == 200, str(s))
check("status confirmed", cf.get("status") == "confirmed", str(cf.get("status")))
# can't re-confirm
s, _ = call("POST", f"/api/bookings/{B1}/confirm", {}, token=TOK)
check("re-confirm 409", s == 409, str(s))
# no-show on confirmed
s, ns = call("POST", f"/api/bookings/{B1}/no-show", {}, token=TOK)
check("no-show 200", s == 200, str(s))
check("status no_show", ns.get("status") == "no_show", str(ns.get("status")))
# no_show locked from edit
s, _ = call("PATCH", f"/api/bookings/{B1}", {"notes": "x"}, token=TOK)
check("edit no_show 409", s == 409, str(s))
# confirm + complete the second
s, _ = call("POST", f"/api/bookings/{B2}/confirm", {}, token=TOK)
s, cp = call("POST", f"/api/bookings/{B2}/complete", {}, token=TOK)
check("complete 200", s == 200, str(s))
check("status completed", cp.get("status") == "completed", str(cp.get("status")))
# can't cancel completed
s, _ = call("POST", f"/api/bookings/{B2}/cancel", {}, token=TOK)
check("cancel completed 409", s == 409, str(s))

print("== 7. cancel frees the slot ==")
s, bk3 = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "Temp", "start_at": "2026-09-05T09:00:00+00:00"}, token=TOK)
B3 = bk3.get("id")
s, _ = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "Clash", "start_at": "2026-09-05T09:30:00+00:00"}, token=TOK)
check("clash with pending 409", s == 409, str(s))
s, _ = call("POST", f"/api/bookings/{B3}/cancel", {}, token=TOK)
check("cancel 200", s == 200, str(s))
s, bk4 = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "After Cancel", "start_at": "2026-09-05T09:30:00+00:00"}, token=TOK)
check("slot free after cancel 201", s == 201, str(s))
B4 = bk4.get("id")

print("== 8. reschedule re-checks overlap ==")
# move B4 into B2's old confirmed slot? B2 is completed so free; use a fresh confirmed one
s, bk5 = call("POST", "/api/bookings", {"service_id": SV, "customer_name": "Anchor", "start_at": "2026-09-06T10:00:00+00:00"}, token=TOK)
B5 = bk5.get("id")
s, _ = call("PATCH", f"/api/bookings/{B4}", {"start_at": "2026-09-06T10:30:00+00:00"}, token=TOK)
check("reschedule into occupied 409", s == 409, str(s))
s, mv = call("PATCH", f"/api/bookings/{B4}", {"start_at": "2026-09-06T12:00:00+00:00"}, token=TOK)
check("reschedule to free slot 200", s == 200, str(s))
check("end recomputed", mv.get("end_at") == "2026-09-06T13:00:00+00:00", str(mv.get("end_at")))

print("== 9. service delete blocked by bookings ==")
s, _ = call("DELETE", f"/api/bookings/services/{SV}", token=TOK)
check("delete service w/ bookings 409", s == 409, str(s))

print("== 10. events + delete + isolation ==")
for ev in ("booking_service.created", "booking.created", "booking.confirmed", "booking.completed", "booking.cancelled", "booking.no_show"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/bookings/{B5}", token=TOK)
check("delete booking 200", s == 200, str(s))
# other tenant sees nothing
email2 = f"phaseaf2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AF2",
    "tenant_name": f"Phase AF2 {SUFFIX}", "tenant_slug": f"phaseaf2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/bookings", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/bookings/{B1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
