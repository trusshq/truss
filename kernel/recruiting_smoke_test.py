"""Phase AJ smoke test: recruiting/ATS — jobs, candidates, applications, pipeline.

Verifies:
- create job (employment_type validation, status open)
- list filters (status, department)
- get/patch job (status + employment_type validation)
- candidates: create (source validation), list (source filter), patch,
  delete (blocked while applications exist)
- applications: create (open job only, duplicate rejected, bad uuid),
  list filters (stage, job_id, candidate_id)
- pipeline: applied -> screening -> interview -> offer -> hired with
  strict transition guards, reject from any non-terminal stage, terminal
  stages locked, hired marks job filled
- job delete blocked by applications
- events emitted
- delete cascades
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


print("== Phase AJ: recruiting / ATS ==")
SUFFIX = str(int(time.time()))
email = f"phaseaj-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AJ",
    "tenant_name": f"Phase AJ {SUFFIX}", "tenant_slug": f"phaseaj-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. jobs ==")
s, j1 = call("POST", "/api/recruiting/jobs", {
    "title": "Backend Engineer", "department": "Engineering",
    "location": "Remote", "employment_type": "full_time",
    "description": "Build the kernel",
}, token=TOK)
check("job created 201", s == 201, f"{s} {j1}")
J1 = j1.get("id")
check("status open", j1.get("status") == "open", str(j1.get("status")))
s, j2 = call("POST", "/api/recruiting/jobs", {
    "title": "Designer", "department": "Design", "employment_type": "contract",
}, token=TOK)
J2 = j2.get("id")
s, _ = call("POST", "/api/recruiting/jobs", {"title": "X", "employment_type": "bogus"}, token=TOK)
check("bad employment_type 400", s == 400, str(s))
s, res = call("GET", "/api/recruiting/jobs", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/recruiting/jobs?status=open", token=TOK)
check("status filter open", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/recruiting/jobs?department=Engineering", token=TOK)
check("department filter", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/recruiting/jobs?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))
# patch job
s, pj = call("PATCH", f"/api/recruiting/jobs/{J2}", {"location": "NYC"}, token=TOK)
check("patch job 200", s == 200, str(s))
check("location set", pj.get("location") == "NYC", str(pj.get("location")))
s, _ = call("PATCH", f"/api/recruiting/jobs/{J2}", {"status": "bogus"}, token=TOK)
check("patch bad status 400", s == 400, str(s))

print("== 2. candidates ==")
s, c1 = call("POST", "/api/recruiting/candidates", {
    "name": "Carol", "email": "carol@x.com", "source": "referral", "skills": "python,fastapi",
}, token=TOK)
check("candidate created 201", s == 201, f"{s} {c1}")
C1 = c1.get("id")
s, c2 = call("POST", "/api/recruiting/candidates", {"name": "Dave", "source": "job_board"}, token=TOK)
C2 = c2.get("id")
s, _ = call("POST", "/api/recruiting/candidates", {"name": "X", "source": "bogus"}, token=TOK)
check("bad source 400", s == 400, str(s))
s, res = call("GET", "/api/recruiting/candidates", token=TOK)
check("candidates total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/recruiting/candidates?source=referral", token=TOK)
check("source filter", res.get("total") == 1, str(res.get("total")))
# patch candidate
s, pc = call("PATCH", f"/api/recruiting/candidates/{C2}", {"skills": "figma"}, token=TOK)
check("patch candidate 200", s == 200, str(s))
check("skills set", pc.get("skills") == "figma", str(pc.get("skills")))

print("== 3. applications ==")
s, a1 = call("POST", "/api/recruiting/applications", {
    "job_id": J1, "candidate_id": C1, "notes": "Strong referral",
}, token=TOK)
check("application created 201", s == 201, f"{s} {a1}")
A1 = a1.get("id")
check("stage applied", a1.get("stage") == "applied", str(a1.get("stage")))
# duplicate rejected
s, _ = call("POST", "/api/recruiting/applications", {"job_id": J1, "candidate_id": C1}, token=TOK)
check("duplicate application 409", s == 409, str(s))
# bad uuid
s, _ = call("POST", "/api/recruiting/applications", {"job_id": "nope", "candidate_id": C1}, token=TOK)
check("bad job uuid 400", s == 400, str(s))
# closed job rejected
s, _ = call("PATCH", f"/api/recruiting/jobs/{J2}", {"status": "closed"}, token=TOK)
s, _ = call("POST", "/api/recruiting/applications", {"job_id": J2, "candidate_id": C2}, token=TOK)
check("apply to closed job 409", s == 409, str(s))
s, _ = call("PATCH", f"/api/recruiting/jobs/{J2}", {"status": "open"}, token=TOK)
# second application for pipeline tests
s, a2 = call("POST", "/api/recruiting/applications", {"job_id": J1, "candidate_id": C2}, token=TOK)
A2 = a2.get("id")
check("application 2 created", s == 201, str(s))
# list filters
s, res = call("GET", "/api/recruiting/applications", token=TOK)
check("applications total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/recruiting/applications?stage=applied", token=TOK)
check("stage filter applied", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/recruiting/applications?job_id={J1}", token=TOK)
check("job filter", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", f"/api/recruiting/applications?candidate_id={C1}", token=TOK)
check("candidate filter", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/recruiting/applications?stage=bogus", token=TOK)
check("bad stage 400", s == 400, str(s))

print("== 4. pipeline ==")
# invalid jump applied -> offer
s, _ = call("POST", f"/api/recruiting/applications/{A1}/stage", {"stage": "offer"}, token=TOK)
check("jump applied->offer 409", s == 409, str(s))
# walk A1 through the full pipeline
for nxt in ("screening", "interview", "offer", "hired"):
    s, mv = call("POST", f"/api/recruiting/applications/{A1}/stage", {"stage": nxt}, token=TOK)
    check(f"move to {nxt} 200", s == 200, str(s))
    check(f"stage is {nxt}", mv.get("stage") == nxt, str(mv.get("stage")))
# hired marks job filled
s, got = call("GET", f"/api/recruiting/jobs/{J1}", token=TOK)
check("job filled after hire", got.get("status") == "filled", str(got.get("status")))
# terminal stage locked
s, _ = call("POST", f"/api/recruiting/applications/{A1}/stage", {"stage": "rejected"}, token=TOK)
check("hired locked 409", s == 409, str(s))
# reject A2 from applied
s, rj = call("POST", f"/api/recruiting/applications/{A2}/stage", {"stage": "rejected", "notes": "Not a fit"}, token=TOK)
check("reject 200", s == 200, str(s))
check("stage rejected", rj.get("stage") == "rejected", str(rj.get("stage")))
check("notes updated", rj.get("notes") == "Not a fit", str(rj.get("notes")))
# rejected locked
s, _ = call("POST", f"/api/recruiting/applications/{A2}/stage", {"stage": "screening"}, token=TOK)
check("rejected locked 409", s == 409, str(s))

print("== 5. delete guards + events + isolation ==")
# job delete blocked by applications
s, _ = call("DELETE", f"/api/recruiting/jobs/{J1}", token=TOK)
check("delete job w/ applications 409", s == 409, str(s))
# candidate delete blocked by applications
s, _ = call("DELETE", f"/api/recruiting/candidates/{C1}", token=TOK)
check("delete candidate w/ applications 409", s == 409, str(s))
# delete an application, then its candidate is free
s, _ = call("DELETE", f"/api/recruiting/applications/{A2}", token=TOK)
check("delete application 200", s == 200, str(s))
s, _ = call("DELETE", f"/api/recruiting/candidates/{C2}", token=TOK)
check("delete freed candidate 200", s == 200, str(s))
# job with no remaining apps? J1 still has A1, so use J2 (no apps)
s, _ = call("DELETE", f"/api/recruiting/jobs/{J2}", token=TOK)
check("delete app-free job 200", s == 200, str(s))
for ev in ("recruiting.job_created", "recruiting.candidate_created",
           "recruiting.application_created", "recruiting.stage_changed"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
# other tenant sees nothing
email2 = f"phaseaj2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AJ2",
    "tenant_name": f"Phase AJ2 {SUFFIX}", "tenant_slug": f"phaseaj2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/recruiting/jobs", token=TOK2)
check("other tenant jobs empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/recruiting/jobs/{J1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
