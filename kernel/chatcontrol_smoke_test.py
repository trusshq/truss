"""Phase F smoke test: chat control surface — kernel control tools in the agent loop.

Verifies the BYOK chat agent can manage the workspace itself:
list objects/agents, search records, create/update records on any object,
assign tasks, create goals, hire agents — all role-gated.

Idempotent: fresh tenant per run.
"""
import json
import os
import time
import urllib.request
import uuid

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
AI_BASE = os.environ.get("TRUSS_TEST_AI_BASE", "http://127.0.0.1:9999/v1")

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


def signup_and_token(suffix):
    email = f"phasef-{suffix}@test.dev"
    s, res = call("POST", "/api/auth/signup", {
        "email": email, "password": "password123", "full_name": "Phase F",
        "tenant_name": f"Phase F {suffix}", "tenant_slug": f"phasef-{suffix}",
    })
    assert s in (200, 201), f"signup failed: {s} {res}"
    return res["access_token"]


def chat(token, message):
    s, res = call("POST", "/api/ai/chat", {"message": message, "history": []}, token=token)
    return s, res


print("== Phase F: chat control surface ==")
tok = signup_and_token(str(int(time.time())))

print("== 1. register AI key (mock provider) ==")
s, key = call("POST", "/api/ai/keys", {
    "name": "mock", "base_url": AI_BASE, "model": "mock-model",
    "api_key": "test-key-123", "is_default": True,
}, token=tok)
check("key created", s in (200, 201), str(s))

print("== 2. enable CRM plugin so objects exist ==")
s, plugins = call("GET", "/api/plugins/catalog", token=tok)
crm = next((p for p in plugins if p.get("id") == "truss-crm"), None)
check("crm in catalog", crm is not None)
if crm:
    s, _ = call("POST", "/api/plugins/install", {"plugin_id": crm["id"]}, token=tok)
    check("crm installed", s in (200, 201), str(s))

print("== 3. list objects via chat ==")
s, res = chat(tok, "What objects are in my workspace?")
check("chat 200", s == 200, str(s))
check("has reply", bool(res.get("reply")), str(res)[:120])
trace = res.get("trace") or []
tools_used = [t.get("tool") for t in trace]
check("called list_objects", "kernel__list_objects" in tools_used, str(tools_used))

print("== 4. list agents via chat ==")
s, res = chat(tok, "List my AI employees")
check("chat 200", s == 200, str(s))
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("called list_agents", "kernel__list_agents" in tools_used, str(tools_used))

print("== 5. analytics count via chat ==")
s, res = chat(tok, "How many leads do we have?")
check("chat 200", s == 200, str(s))
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("called analytics", "kernel__analytics" in tools_used, str(tools_used))

print("== 6. hire an agent via chat (admin-gated) ==")
s, res = chat(tok, "Hire an AI employee named Scout")
check("chat 200", s == 200, str(s))
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("called hire_agent", "kernel__hire_agent" in tools_used, str(tools_used))
# verify the agent actually exists now
s, agents = call("GET", "/api/agents", token=tok)
names = [a.get("name") for a in agents]
check("agent created", "Mock Hire" in names, str(names))

print("== 7. create a goal via chat ==")
s, res = chat(tok, "Create a goal: close 10 deals")
check("chat 200", s == 200, str(s))
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("called create_goal", "kernel__create_goal" in tools_used, str(tools_used))
s, goals = call("GET", "/api/org/goals", token=tok)
check("goal exists", any(g.get("title") == "Mock goal" for g in goals), str([g.get("title") for g in goals]))

print("== 8. assign a task via chat ==")
s, res = chat(tok, "Assign a task to review the pipeline")
check("chat 200", s == 200, str(s))
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("called assign_task", "kernel__assign_task" in tools_used, str(tools_used))

print("== 9. create a record via chat (generic CRUD) ==")
s, res = chat(tok, "Create a new lead record")
check("chat 200", s == 200, str(s))
# the mock routes non-control intents to truss_crm__create_lead
tools_used = [t.get("tool") for t in (res.get("trace") or [])]
check("created a record", any("create" in (t or "") for t in tools_used), str(tools_used))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
