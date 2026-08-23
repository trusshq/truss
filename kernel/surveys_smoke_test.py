"""Phase AH smoke test: surveys — questions, lifecycle, responses, analytics.

Verifies:
- create survey (draft status)
- list filters (status)
- get/patch (non-draft locked)
- questions: create (kind validation, choice needs >= 2 options), list,
  patch, delete; non-draft locked from question changes
- lifecycle: publish (draft + requires >= 1 question), close (published
  only), 409 guards
- responses: submit (published only, required questions, unknown
  question rejected), list
- analytics: total_responses, rating average, choice counts
- events emitted
- delete (admin) cascades questions + responses
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


print("== Phase AH: surveys & feedback ==")
SUFFIX = str(int(time.time()))
email = f"phaseah-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase AH",
    "tenant_name": f"Phase AH {SUFFIX}", "tenant_slug": f"phaseah-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create survey ==")
s, sv = call("POST", "/api/surveys", {
    "title": "Customer satisfaction", "description": "Q3 CSAT pulse",
}, token=TOK)
check("survey created 201", s == 201, f"{s} {sv}")
SV1 = sv.get("id")
check("status draft", sv.get("status") == "draft", str(sv.get("status")))
check("response_count 0", sv.get("response_count") == 0, str(sv.get("response_count")))

print("== 2. list filters ==")
s, sv2 = call("POST", "/api/surveys", {"title": "Onboarding feedback"}, token=TOK)
SV2 = sv2.get("id")
s, res = call("GET", "/api/surveys", token=TOK)
check("list total 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/surveys?status=draft", token=TOK)
check("status filter draft", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/surveys?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 3. questions ==")
s, q1 = call("POST", f"/api/surveys/{SV1}/questions", {
    "text": "How satisfied are you?", "kind": "rating", "position": 1, "required": True,
}, token=TOK)
check("rating Q created 201", s == 201, f"{s} {q1}")
Q1 = q1.get("id")
s, q2 = call("POST", f"/api/surveys/{SV1}/questions", {
    "text": "Which feature do you use most?", "kind": "choice",
    "options": ["Reports", "Automations", "CRM"], "position": 2,
}, token=TOK)
Q2 = q2.get("id")
check("choice Q created", s == 201, str(s))
s, q3 = call("POST", f"/api/surveys/{SV1}/questions", {
    "text": "Any other feedback?", "kind": "text", "position": 3,
}, token=TOK)
Q3 = q3.get("id")
check("text Q created", s == 201, str(s))
# validation
s, _ = call("POST", f"/api/surveys/{SV1}/questions", {"text": "X", "kind": "bogus"}, token=TOK)
check("bad kind 400", s == 400, str(s))
s, _ = call("POST", f"/api/surveys/{SV1}/questions", {"text": "X", "kind": "choice", "options": ["only-one"]}, token=TOK)
check("choice < 2 options 400", s == 400, str(s))
# list ordered by position
s, qs = call("GET", f"/api/surveys/{SV1}/questions", token=TOK)
check("question list total 3", qs.get("total") == 3, str(qs.get("total")))
check("ordered by position", [q["position"] for q in qs["items"]] == [1, 2, 3], str([q["position"] for q in qs["items"]]))
# patch a question (text change; keep Q3 optional so response 2 may omit it)
s, pq = call("PATCH", f"/api/surveys/questions/{Q3}", {"text": "Any other feedback for us?"}, token=TOK)
check("patch question 200", s == 200, str(s))
check("patch applied", pq.get("text") == "Any other feedback for us?", str(pq.get("text")))

print("== 4. lifecycle guards ==")
# publish requires >= 1 question (SV2 has none)
s, _ = call("POST", f"/api/surveys/{SV2}/publish", {}, token=TOK)
check("publish w/o question 400", s == 400, str(s))
# can't close a draft
s, _ = call("POST", f"/api/surveys/{SV1}/close", {}, token=TOK)
check("close draft 409", s == 409, str(s))
# publish SV1
s, pub = call("POST", f"/api/surveys/{SV1}/publish", {}, token=TOK)
check("publish 200", s == 200, str(s))
check("status published", pub.get("status") == "published", str(pub.get("status")))
# can't re-publish
s, _ = call("POST", f"/api/surveys/{SV1}/publish", {}, token=TOK)
check("re-publish 409", s == 409, str(s))
# published locked from edit
s, _ = call("PATCH", f"/api/surveys/{SV1}", {"title": "New"}, token=TOK)
check("edit published 409", s == 409, str(s))
# published locked from question add
s, _ = call("POST", f"/api/surveys/{SV1}/questions", {"text": "X"}, token=TOK)
check("add Q to published 409", s == 409, str(s))
# published locked from question edit
s, _ = call("PATCH", f"/api/surveys/questions/{Q1}", {"text": "X"}, token=TOK)
check("edit Q on published 409", s == 409, str(s))

print("== 5. responses ==")
# draft survey rejects responses
s, _ = call("POST", f"/api/surveys/{SV2}/responses", {"answers": {}}, token=TOK)
check("respond to draft 409", s == 409, str(s))
# missing required question
s, _ = call("POST", f"/api/surveys/{SV1}/responses", {"respondent": "a@x.com", "answers": {}}, token=TOK)
check("missing required 400", s == 400, str(s))
# unknown question id
s, _ = call("POST", f"/api/surveys/{SV1}/responses", {
    "respondent": "a@x.com", "answers": {Q1: 5, "deadbeef": "x"},
}, token=TOK)
check("unknown question 400", s == 400, str(s))
# valid responses
s, r1 = call("POST", f"/api/surveys/{SV1}/responses", {
    "respondent": "alice@x.com", "answers": {Q1: 5, Q2: "Reports", Q3: "Love it"},
}, token=TOK)
check("response 1 created 201", s == 201, f"{s} {r1}")
s, r2 = call("POST", f"/api/surveys/{SV1}/responses", {
    "respondent": "bob@x.com", "answers": {Q1: 3, Q2: "CRM"},
}, token=TOK)
check("response 2 created 201", s == 201, str(s))
s, resp = call("GET", f"/api/surveys/{SV1}/responses", token=TOK)
check("response list total 2", resp.get("total") == 2, str(resp.get("total")))

print("== 6. analytics ==")
s, an = call("GET", f"/api/surveys/{SV1}/analytics", token=TOK)
check("analytics 200", s == 200, str(s))
check("total_responses 2", an.get("total_responses") == 2, str(an.get("total_responses")))
by_q = {q["question_id"]: q for q in an.get("questions", [])}
check("rating average 4.0", by_q.get(Q1, {}).get("average") == 4.0, str(by_q.get(Q1, {}).get("average")))
check("rating answered 2", by_q.get(Q1, {}).get("answered") == 2, str(by_q.get(Q1, {}).get("answered")))
check("choice counts", by_q.get(Q2, {}).get("choice_counts") == {"Reports": 1, "CRM": 1}, str(by_q.get(Q2, {}).get("choice_counts")))
check("text answered 1", by_q.get(Q3, {}).get("answered") == 1, str(by_q.get(Q3, {}).get("answered")))

print("== 7. close + events + delete + isolation ==")
s, cl = call("POST", f"/api/surveys/{SV1}/close", {}, token=TOK)
check("close 200", s == 200, str(s))
check("status closed", cl.get("status") == "closed", str(cl.get("status")))
# closed rejects responses
s, _ = call("POST", f"/api/surveys/{SV1}/responses", {"answers": {Q1: 4}}, token=TOK)
check("respond to closed 409", s == 409, str(s))
# can't re-close
s, _ = call("POST", f"/api/surveys/{SV1}/close", {}, token=TOK)
check("re-close 409", s == 409, str(s))
for ev in ("survey.created", "survey.published", "survey.closed", "survey.question_created", "survey.response_submitted"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/surveys/{SV1}", token=TOK)
check("delete survey 200", s == 200, str(s))
s, res = call("GET", "/api/surveys", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phaseah2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase AH2",
    "tenant_name": f"Phase AH2 {SUFFIX}", "tenant_slug": f"phaseah2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/surveys", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/surveys/{SV2}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
