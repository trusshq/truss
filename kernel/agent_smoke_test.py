"""Phase A smoke test: AI employees (agents) + task execution against a mock provider.

Covers: hire/list/patch/pause/resume/terminate, task lifecycle (proposed ->
approved -> running -> done), the human approval gate, budget auto-pause,
agent-as-actor record creation, and agent.* event emission.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
AI_BASE = os.environ.get("TRUSS_TEST_AI_BASE", "http://127.0.0.1:9999/v1")
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req) as resp:
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


print("== 0. signup fresh tenant (agent-test) ==")
s, b = call("POST", "/api/auth/signup", {
    "email": "agent-owner@test.dev",
    "password": "password123",
    "full_name": "Agent Owner",
    "tenant_name": "Agent Test Co",
    "tenant_slug": "agent-test-co",
}, auth=False)
if s == 409:
    s, b = call("POST", "/api/auth/login", {"email": "agent-owner@test.dev", "password": "password123"}, auth=False)
check("auth ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access" + "_token")

print("== 1. install CRM plugin (gives the agent tools) ==")
s, b = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"})
if s == 409 or (isinstance(b, dict) and b.get("ok")):
    s = 201
check("crm installed", s in (200, 201), f"{s} {b}")

print("== 2. create AI key -> mock provider ==")
s, b = call("POST", "/api/ai/keys", {
    "name": "agent-mock",
    "provider": "openai-compatible",
    "base_url": AI_BASE,
    "model": "mock-model",
    "api_key": "test-key-123",
    "is_default": True,
})
if s == 409:
    s2, keys = call("GET", "/api/ai/keys")
    b = next((k for k in keys if k["name"] == "agent-mock"), {})
    s = 200
check("ai key created", s in (200, 201) and b.get("name") == "agent-mock", f"{s} {b}")
key_id = b.get("id")

print("== 3. hire an agent (SDR) ==")
s, agent = call("POST", "/api/agents", {
    "name": "Sam the SDR",
    "role": "Sales Development Rep",
    "persona": "You are a diligent SDR. Qualify every inbound lead promptly.",
    "icon": "📞",
    "ai_key_id": key_id,
    "permission_role": "member",
    "budget_tokens": 0,
})
check("agent hired", s == 201 and agent.get("name") == "Sam the SDR", f"{s} {agent}")
agent_id = agent.get("id")
check("agent active by default", agent.get("status") == "active", str(agent.get("status")))
check("agent has icon", agent.get("icon") == "📞", str(agent.get("icon")))

print("== 4. duplicate name rejected ==")
s, b = call("POST", "/api/agents", {"name": "Sam the SDR", "role": "dup"})
check("dup name -> 409", s == 409, f"{s} {b}")

print("== 5. list agents ==")
s, agents = call("GET", "/api/agents")
check("list ok", s == 200 and isinstance(agents, list) and len(agents) >= 1, f"{s}")
check("our agent present", any(a["id"] == agent_id for a in agents), str([a["name"] for a in agents]))

print("== 6. create task (auto-approved, no review) ==")
s, task = call("POST", f"/api/agents/{agent_id}/tasks", {
    "agent_id": agent_id,
    "title": "Qualify the new inbound lead",
    "description": "Create a lead record for the prospect.",
    "needs_review": False,
})
check("task created", s == 201 and task.get("title"), f"{s} {task}")
check("auto-approved", task.get("status") == "approved", str(task.get("status")))
task_id = task.get("id")

print("== 7. run the task (agent executes via mock provider) ==")
s, run = call("POST", f"/api/agents/{agent_id}/tasks/{task_id}/run")
check("run 200", s == 200, f"{s} {run}")
check("task done", run.get("task", {}).get("status") == "done", str(run.get("task", {}).get("status")))
check("run ok", run.get("run", {}).get("ok") is True, str(run.get("run")))
check("agent made tool call", len(run.get("run", {}).get("trace", [])) >= 1, str(run.get("run", {}).get("trace")))
check("reply present", bool(run.get("run", {}).get("reply")), str(run.get("run", {}).get("reply")))
check("tokens recorded", run.get("task", {}).get("tokens_used", 0) > 0, str(run.get("task", {}).get("tokens_used")))

print("== 8. record actually created by the agent ==")
s, b = call("GET", "/api/records/lead?search=" + urllib.parse.quote("AI Test Lead"))
check("lead exists via agent", s == 200 and b.get("total", 0) >= 1, f"{s} {b}")

print("== 9. agent token usage accumulated ==")
s, agent = call("GET", f"/api/agents/{agent_id}")
check("tokens_used > 0", agent.get("tokens_used", 0) > 0, str(agent.get("tokens_used")))
check("runs_count == 1", agent.get("runs_count") == 1, str(agent.get("runs_count")))

print("== 10. agent.* events emitted with actor_type=agent ==")
s, events = call("GET", "/api/events?type=agent.task_completed")
check("task_completed event", s == 200 and len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
if events:
    ev = events[0]
    check("event actor is the agent", ev.get("actor_id") == agent_id, str(ev.get("actor_id")))
    check("payload flagged actor_type=agent", ev.get("payload", {}).get("actor_type") == "agent", str(ev.get("payload")))

print("== 11. approval gate: needs_review task cannot run until approved ==")
s, task2 = call("POST", f"/api/agents/{agent_id}/tasks", {
    "agent_id": agent_id,
    "title": "Send a follow-up email",
    "needs_review": True,
})
check("review task created", s == 201, f"{s} {task2}")
check("status proposed", task2.get("status") == "proposed", str(task2.get("status")))
task2_id = task2.get("id")
s, b = call("POST", f"/api/agents/{agent_id}/tasks/{task2_id}/run")
check("run blocked pre-approval -> 409", s == 409, f"{s} {b}")

print("== 12. approve then run ==")
s, b = call("POST", f"/api/agents/{agent_id}/tasks/{task2_id}/approve")
check("approved", s == 200 and b.get("status") == "approved", f"{s} {b}")
s, run2 = call("POST", f"/api/agents/{agent_id}/tasks/{task2_id}/run")
check("run after approval 200", s == 200, f"{s} {run2}")
check("task2 done", run2.get("task", {}).get("status") == "done", str(run2.get("task", {}).get("status")))

print("== 13. reject a proposed task ==")
s, task3 = call("POST", f"/api/agents/{agent_id}/tasks", {
    "agent_id": agent_id, "title": "Do something risky", "needs_review": True,
})
s, b = call("POST", f"/api/agents/{agent_id}/tasks/{task3['id']}/reject")
check("rejected", s == 200 and b.get("status") == "rejected", f"{s} {b}")

print("== 14. pause blocks execution ==")
s, b = call("POST", f"/api/agents/{agent_id}/pause")
check("paused", s == 200 and b.get("status") == "paused", f"{s} {b}")
s, task4 = call("POST", f"/api/agents/{agent_id}/tasks", {
    "agent_id": agent_id, "title": "Task while paused", "needs_review": False,
})
s, run3 = call("POST", f"/api/agents/{agent_id}/tasks/{task4['id']}/run")
check("run while paused fails", run3.get("task", {}).get("status") == "failed", str(run3.get("task", {}).get("status")))
s, b = call("POST", f"/api/agents/{agent_id}/resume")
check("resumed", s == 200 and b.get("status") == "active", f"{s} {b}")

print("== 15. budget exhaustion auto-pauses ==")
s, b = call("PATCH", f"/api/agents/{agent_id}", {"budget_tokens": 10})
check("tiny budget set", s == 200 and b.get("budget_tokens") == 10, f"{s} {b}")
s, task5 = call("POST", f"/api/agents/{agent_id}/tasks", {
    "agent_id": agent_id, "title": "Over-budget task", "needs_review": False,
})
s, run4 = call("POST", f"/api/agents/{agent_id}/tasks/{task5['id']}/run")
check("over-budget run fails", run4.get("task", {}).get("status") == "failed", str(run4.get("task", {}).get("status")))
s, agent = call("GET", f"/api/agents/{agent_id}")
check("agent auto-paused on budget", agent.get("status") == "paused", str(agent.get("status")))
# restore for cleanliness
call("POST", f"/api/agents/{agent_id}/resume")
call("PATCH", f"/api/agents/{agent_id}", {"budget_tokens": 0})

print("== 16. terminate agent ==")
s, b = call("DELETE", f"/api/agents/{agent_id}")
check("terminated 204", s == 204, f"{s}")
s, agents = call("GET", "/api/agents")
check("agent gone", not any(a["id"] == agent_id for a in agents), str([a["name"] for a in agents]))

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
