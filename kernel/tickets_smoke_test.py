"""Phase AB smoke test: support tickets — lifecycle, assignment, comments, SLA.

Verifies:
- create ticket (auto number TK-0001, priority validation, SLA hours by priority)
- list filters (status, priority, category, unassigned, breached)
- get/patch (priority change updates SLA; closed tickets not editable)
- lifecycle: start (open only), resolve (open/in_progress), close (resolved only),
  reopen (resolved/closed), 409 guards, resolved_at/closed_at stamps
- assign endpoint sets/clears assignee
- comments: add (empty body 400), list ordered asc, internal flag
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


print("== Phase AB: support tickets ==")
SUFFIX = str(int(time.time()))
email = f"phaseab-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AB",
    "tenant_name": f"Phase AB {SUFFIX}", "tenant_slug": f"phaseab-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create ticket ==")
s, t = call("POST", "/api/tickets", {
    "subject": "Cannot login", "description": "Getting 401 on login",
    "requester_email": "cust@example.com", "category": "Auth", "priority": "high",
}, token=TOK)
check("ticket created 201", s == 201, f"{s} {t}")
TID = t.get("id")
check("number TK-0001", t.get("number") == "TK-0001", str(t.get("number")))
check("status open", t.get("status") == "open", str(t.get("status")))
check("high priority SLA 8h", t.get("sla_hours") == 8, str(t.get("sla_hours")))
check("not breached yet", t.get("sla_breached") is False, str(t.get("sla_breached")))

print("== 2. priority validation + SLA mapping ==")
s, _ = call("POST", "/api/tickets", {"subject": "X", "priority": "bogus"}, token=TOK)
check("bad priority 400", s == 400, str(s))
s, t2 = call("POST", "/api/tickets", {"subject": "Urgent down", "priority": "urgent"}, token=TOK)
check("urgent SLA 2h", t2.get("sla_hours") == 2, str(t2.get("sla_hours")))
s, t3 = call("POST", "/api/tickets", {"subject": "Low ask", "priority": "low"}, token=TOK)
check("low SLA 72h", t3.get("sla_hours") == 72, str(t3.get("sla_hours")))

print("== 3. list + filters ==")
s, res = call("GET", "/api/tickets", token=TOK)
check("list total 3", res.get("total") == 3, str(res.get("total")))
s, res = call("GET", "/api/tickets?priority=high", token=TOK)
check("priority filter high", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/tickets?category=Auth", token=TOK)
check("category filter Auth", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/tickets?unassigned=true", token=TOK)
check("unassigned filter all 3", res.get("total") == 3, str(res.get("total")))
s, res = call("GET", "/api/tickets?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 4. assign ==")
s, me = call("GET", "/api/auth/me", token=TOK)
UID = me.get("id") or me.get("user_id")
s, asg = call("POST", f"/api/tickets/{TID}/assign", {"assignee_id": UID}, token=TOK)
check("assign 200", s == 200, f"{s} {asg}")
check("assignee set", asg.get("assignee_id") == UID, str(asg.get("assignee_id")))
s, res = call("GET", "/api/tickets?unassigned=true", token=TOK)
check("unassigned now 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/tickets?assignee_id={UID}", token=TOK)
check("assignee filter finds 1", res.get("total") == 1, str(res.get("total")))

print("== 5. lifecycle guards ==")
# can't close an open ticket
s, _ = call("POST", f"/api/tickets/{TID}/close", {}, token=TOK)
check("close open 409", s == 409, str(s))
# can't reopen an open ticket
s, _ = call("POST", f"/api/tickets/{TID}/reopen", {}, token=TOK)
check("reopen open 409", s == 409, str(s))
# start it
s, st = call("POST", f"/api/tickets/{TID}/start", {}, token=TOK)
check("start 200", s == 200, str(s))
check("status in_progress", st.get("status") == "in_progress", str(st.get("status")))
# can't re-start
s, _ = call("POST", f"/api/tickets/{TID}/start", {}, token=TOK)
check("re-start 409", s == 409, str(s))
# resolve it
s, rv = call("POST", f"/api/tickets/{TID}/resolve", {}, token=TOK)
check("resolve 200", s == 200, str(s))
check("status resolved", rv.get("status") == "resolved", str(rv.get("status")))
check("resolved_at stamped", bool(rv.get("resolved_at")), str(rv.get("resolved_at")))
# close it
s, cl = call("POST", f"/api/tickets/{TID}/close", {}, token=TOK)
check("close 200", s == 200, str(s))
check("status closed", cl.get("status") == "closed", str(cl.get("status")))
check("closed_at stamped", bool(cl.get("closed_at")), str(cl.get("closed_at")))
# can't edit closed
s, _ = call("PATCH", f"/api/tickets/{TID}", {"subject": "New"}, token=TOK)
check("edit closed 409", s == 409, str(s))
# can't assign closed
s, _ = call("POST", f"/api/tickets/{TID}/assign", {"assignee_id": UID}, token=TOK)
check("assign closed 409", s == 409, str(s))
# reopen it
s, ro = call("POST", f"/api/tickets/{TID}/reopen", {}, token=TOK)
check("reopen 200", s == 200, str(s))
check("status open again", ro.get("status") == "open", str(ro.get("status")))
check("resolved_at cleared", ro.get("resolved_at") == "", str(ro.get("resolved_at")))
check("closed_at cleared", ro.get("closed_at") == "", str(ro.get("closed_at")))

print("== 6. patch updates priority + SLA ==")
s, upd = call("PATCH", f"/api/tickets/{TID}", {"priority": "urgent"}, token=TOK)
check("patch 200", s == 200, f"{s} {upd}")
check("SLA now 2h", upd.get("sla_hours") == 2, str(upd.get("sla_hours")))

print("== 7. comments ==")
s, cm = call("POST", f"/api/tickets/{TID}/comments", {"body": "Looking into it"}, token=TOK)
check("comment created 201", s == 201, f"{s} {cm}")
check("comment not internal", cm.get("internal") is False, str(cm.get("internal")))
s, cm2 = call("POST", f"/api/tickets/{TID}/comments", {"body": "Internal note", "internal": True}, token=TOK)
check("internal comment 201", s == 201, str(s))
check("internal flag true", cm2.get("internal") is True, str(cm2.get("internal")))
s, _ = call("POST", f"/api/tickets/{TID}/comments", {"body": "   "}, token=TOK)
check("empty comment 400", s == 400, str(s))
s, cms = call("GET", f"/api/tickets/{TID}/comments", token=TOK)
check("2 comments listed", cms.get("total") == 2, str(cms.get("total")))
check("ordered asc", cms["items"][0]["body"] == "Looking into it", str(cms["items"][0].get("body")))

print("== 8. events + delete + isolation ==")
for ev in ("ticket.created", "ticket.started", "ticket.resolved", "ticket.closed", "ticket.reopened", "ticket.assigned", "ticket.commented"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/tickets/{t3['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/tickets", token=TOK)
check("two remain after delete", res.get("total") == 2, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseab2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AB2",
    "tenant_name": f"Phase AB2 {SUFFIX}", "tenant_slug": f"phaseab2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/tickets", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/tickets/{TID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
