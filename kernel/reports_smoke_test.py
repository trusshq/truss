"""Phase M smoke test: saved reports & dashboards — CRUD, run, runs, scheduling.

Verifies:
- create/list/get/update/delete saved reports
- query + cron validation
- manual run snapshots a result into ReportRun
- runs history lists snapshots
- scheduled reports fire via tick_due_reports (deterministic future-now tick)
- error snapshotting for a broken query

Idempotent: fresh tenant per run.
"""
import asyncio
import json
import os
import time
import urllib.request
import urllib.error
from datetime import timedelta

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


print("== Phase M: saved reports ==")
SUFFIX = str(int(time.time()))
email = f"phasem-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase M",
    "tenant_name": f"Phase M {SUFFIX}", "tenant_slug": f"phasem-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

# seed data: CRM + a few records to report on
s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))
for i in range(3):
    s, _ = call("POST", "/api/records/lead", {"data": {"name": f"Lead {i}", "source": "Website", "status": "New"}}, token=TOK)
    assert s in (200, 201), f"seed lead failed: {s}"

print("== 1. create report ==")
s, rep = call("POST", "/api/reports", {
    "name": "Lead count",
    "description": "How many leads we have",
    "query": {"object": "lead", "metric": "count"},
}, token=TOK)
check("create 201", s == 201, f"{s} {rep}")
RID = rep.get("id")
check("has id", bool(RID), str(rep))
check("no cron -> no next_run", rep.get("next_run_at") is None, str(rep.get("next_run_at")))

print("== 2. validation ==")
s, res = call("POST", "/api/reports", {"name": "bad", "query": {"object": "lead", "metric": "bogus"}}, token=TOK)
check("bad metric 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/reports", {"name": "bad", "query": {"metric": "count"}}, token=TOK)
check("missing object 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/reports", {"name": "bad", "query": {"object": "lead", "metric": "count"}, "cron": "not a cron"}, token=TOK)
check("bad cron 422", s == 422, f"{s} {res}")

print("== 3. list + get ==")
s, res = call("GET", "/api/reports", token=TOK)
check("list 200", s == 200, str(s))
check("one report listed", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", f"/api/reports/{RID}", token=TOK)
check("get 200", s == 200 and res.get("name") == "Lead count", f"{s} {res.get('name')}")

print("== 4. manual run + snapshot ==")
s, run = call("POST", f"/api/reports/{RID}/run", token=TOK)
check("run 201", s == 201, f"{s} {run}")
check("run ok", run.get("status") == "ok", str(run.get("status")))
check("result count == 3", run.get("result", {}).get("value") == 3, str(run.get("result")))
check("trigger manual", run.get("trigger") == "manual", str(run.get("trigger")))

print("== 5. runs history ==")
s, res = call("GET", f"/api/reports/{RID}/runs", token=TOK)
check("runs 200", s == 200, str(s))
check("one run recorded", res.get("total") == 1, str(res.get("total")))

print("== 6. update query + add cron schedule ==")
s, res = call("PATCH", f"/api/reports/{RID}", {
    "query": {"object": "lead", "metric": "group_by", "field": "source"},
    "cron": "* * * * *",
}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("cron stored", res.get("cron") == "* * * * *", str(res.get("cron")))
check("next_run_at computed", res.get("next_run_at") is not None, str(res.get("next_run_at")))

print("== 7. scheduled run via deterministic tick ==")
# advance a future 'now' past next_run_at and tick the report scheduler directly
from datetime import datetime, timezone
from truss_kernel.services import reports as reports_svc

future = datetime.now(timezone.utc) + timedelta(days=2)
fired = asyncio.run(reports_svc.tick_due_reports(now=future))
check("tick fired >= 1", fired >= 1, f"fired={fired}")
s, res = call("GET", f"/api/reports/{RID}/runs", token=TOK)
sched_runs = [r for r in res.get("items", []) if r["trigger"] == "schedule"]
check("schedule run recorded", len(sched_runs) >= 1, str([r["trigger"] for r in res.get("items", [])]))
check("schedule run ok", sched_runs and sched_runs[0]["status"] == "ok", str(sched_runs[:1]))
check("group_by result shape", sched_runs and "rows" in sched_runs[0].get("result", {}), str(sched_runs[:1]))

print("== 8. error snapshotting ==")
s, res = call("PATCH", f"/api/reports/{RID}", {"query": {"object": "no_such_object", "metric": "count"}}, token=TOK)
check("patch to broken query", s == 200, str(s))
s, run = call("POST", f"/api/reports/{RID}/run", token=TOK)
check("broken run 201", s == 201, f"{s} {run}")
check("broken run status error", run.get("status") == "error", str(run.get("status")))
check("error message captured", bool(run.get("error")), str(run.get("error")))

print("== 9. delete (admin) ==")
s, res = call("DELETE", f"/api/reports/{RID}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/reports", token=TOK)
check("gone from list", res.get("total") == 0, str(res.get("total")))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
