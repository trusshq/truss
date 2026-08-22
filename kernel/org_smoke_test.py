"""Phase B smoke test: org chart, delegation, goals, notifications, comments,
budget ledger, review inbox — the Paperclip collaboration layer."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
AI_BASE = os.environ.get("TRUSS_TEST_AI_BASE", "http://127.0.0.1:9999/v1")
SUFFIX = str(int(time.time()))
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth and TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
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
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "  " + str(detail))


print("== 0. signup fresh tenant (org-test) ==")
email = "org-owner-" + SUFFIX + "@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email,
    "password": "password123",
    "full_name": "Org Owner",
    "tenant_name": "Org Test Co",
    "tenant_slug": "org-test-" + SUFFIX,
}, auth=False)
check("auth ok", s in (200, 201) and ("access" + "_token") in b, str(s) + " " + str(b))
TOKEN = b.get("access" + "_token")
me = call("GET", "/api/auth/me")[1]
my_user_id = me.get("id") or me.get("user_id")

print("== 1. install CRM plugin + AI key -> mock provider ==")
s, b = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"})
if s == 409 or (isinstance(b, dict) and b.get("ok")):
    s = 201
check("crm installed", s in (200, 201), str(s) + " " + str(b))
s, b = call("POST", "/api/ai/keys", {
    "name": "org-mock",
    "provider": "openai-compatible",
    "base_url": AI_BASE,
    "model": "mock-model",
    "api_key": "test-key-123",
    "is_default": True,
})
check("ai key created", s in (200, 201), str(s) + " " + str(b))
key_id = b.get("id")

print("== 2. hire a manager + two reports ==")
s, mgr = call("POST", "/api/agents", {
    "name": "Mia Manager", "role": "Sales Director", "icon": "👔",
    "ai_key_id": key_id, "permission_role": "member",
})
check("manager hired", s == 201, str(s) + " " + str(mgr))
mgr_id = mgr.get("id")
s, rep1 = call("POST", "/api/agents", {
    "name": "Sam SDR", "role": "SDR", "icon": "📞",
    "ai_key_id": key_id, "permission_role": "member",
    "reports_to_agent_id": mgr_id,
})
check("report1 hired under manager", s == 201 and rep1.get("reports_to_agent_id") == mgr_id, str(s) + " " + str(rep1))
rep1_id = rep1.get("id")
s, rep2 = call("POST", "/api/agents", {
    "name": "Quinn Qualifier", "role": "Lead Qualifier", "icon": "🔍",
    "ai_key_id": key_id, "permission_role": "member",
    "reports_to_agent_id": mgr_id,
})
check("report2 hired under manager", s == 201, str(s) + " " + str(rep2))
rep2_id = rep2.get("id")

print("== 3. org tree shape ==")
s, tree = call("GET", "/api/org/tree")
check("tree 200", s == 200 and isinstance(tree, list), str(s))
roots = [n for n in tree if n["kind"] == "agent"]
mgr_node = next((n for n in roots if n["id"] == mgr_id), None)
check("manager is a root", mgr_node is not None, str([n["name"] for n in roots]))
if mgr_node:
    child_ids = {c["id"] for c in mgr_node["children"]}
    check("manager has 2 reports", child_ids == {rep1_id, rep2_id}, str(child_ids))

print("== 4. cycle + self-report rejected ==")
s, b = call("POST", "/api/org/reports-to", {"agent_id": mgr_id, "manager_agent_id": rep1_id})
check("cycle mgr->rep1 rejected 422", s == 422, str(s) + " " + str(b))
s, b = call("POST", "/api/org/reports-to", {"agent_id": rep1_id, "manager_agent_id": rep1_id})
check("self-report rejected 422", s == 422, str(s) + " " + str(b))

print("== 5. report-to-human ==")
s, b = call("POST", "/api/org/reports-to", {"agent_id": rep2_id, "manager_user_id": my_user_id})
check("rep2 now reports to human", s == 200 and b.get("reports_to_user_id") == my_user_id, str(s) + " " + str(b))
# put rep2 back under the manager for delegation tests
call("POST", "/api/org/reports-to", {"agent_id": rep2_id, "manager_agent_id": mgr_id})

print("== 6. delegation: manager -> direct report ==")
s, dt = call("POST", f"/api/agents/{mgr_id}/delegate", {
    "report_id": rep1_id,
    "title": "Qualify inbound leads",
    "description": "Work the new leads queue.",
    "needs_review": False,
})
check("delegated 201", s == 201, str(s) + " " + str(dt))
check("provenance set", dt.get("delegated_by_agent_id") == mgr_id, str(dt.get("delegated_by_agent_id")))
check("delegated auto-approved", dt.get("status") == "approved", str(dt.get("status")))
check("assigned to report", dt.get("agent_id") == rep1_id, str(dt.get("agent_id")))

print("== 7. delegation to a NON-report rejected ==")
s, b = call("POST", f"/api/agents/{rep1_id}/delegate", {
    "report_id": mgr_id, "title": "upward delegation",
})
check("non-report rejected 422", s == 422, str(s) + " " + str(b))

print("== 8. goals: create parent + sub-goal, link task ==")
s, goal = call("POST", "/api/org/goals", {
    "title": "Book 50 meetings", "metric": "meetings", "target_value": 50.0,
    "unit": "meetings", "owner_agent_id": mgr_id,
})
check("parent goal created", s == 201, str(s) + " " + str(goal))
goal_id = goal.get("id")
s, sub = call("POST", "/api/org/goals", {
    "title": "Qualify 100 leads", "metric": "leads", "target_value": 100.0,
    "owner_agent_id": rep1_id, "parent_goal_id": goal_id,
})
check("sub-goal created", s == 201 and sub.get("parent_goal_id") == goal_id, str(s) + " " + str(sub))
sub_id = sub.get("id")
# move sub-goal to 50% -> parent should roll up to 25 (0.5 * 50)
s, b = call("PATCH", f"/api/org/goals/{sub_id}", {"current_value": 50.0})
check("sub-goal updated", s == 200 and b.get("current_value") == 50.0, str(s) + " " + str(b))
s, parent = call("GET", "/api/org/goals")
p = next((g for g in parent if g["id"] == goal_id), {})
check("parent rolled up to 25", abs(p.get("current_value", -1) - 25.0) < 0.01, str(p.get("current_value")))
check("parent progress 0.5", abs(p.get("progress", -1) - 0.5) < 0.01, str(p.get("progress")))

print("== 9. task linked to a goal ==")
s, gt = call("POST", f"/api/agents/{rep1_id}/tasks", {
    "agent_id": rep1_id, "title": "Goal-linked task",
    "goal_id": sub_id, "needs_review": False,
})
check("goal-linked task created", s == 201 and gt.get("goal_id") == sub_id, str(s) + " " + str(gt))
s, gtasks = call("GET", f"/api/org/goals/{sub_id}/tasks")
check("goal tasks endpoint", s == 200 and any(t["id"] == gt["id"] for t in gtasks), str(s))

print("== 10. review inbox shows proposed tasks ==")
s, rt = call("POST", f"/api/agents/{rep1_id}/tasks", {
    "agent_id": rep1_id, "title": "Needs human eyes", "needs_review": True,
})
check("proposed task created", s == 201 and rt.get("status") == "proposed", str(s))
s, inbox = call("GET", "/api/org/review")
check("review inbox 200", s == 200, str(s))
pend = inbox.get("pending_tasks", [])
check("proposed task in inbox", any(t["id"] == rt["id"] for t in pend), str([t["id"] for t in pend]))
check("inbox carries agent_name", all("agent_name" in t for t in pend), str(pend[:1]))

print("== 11. run a task -> notification fires ==")
s, run = call("POST", f"/api/agents/{rep1_id}/tasks/{dt['id']}/run")
check("delegated task ran", s == 200 and run.get("task", {}).get("status") == "done", str(s) + " " + str(run.get("task", {}).get("status")))
s, notif = call("GET", "/api/org/notifications")
check("notifications 200", s == 200, str(s))
items = notif.get("items", [])
check("task_done notification present", any(n["kind"] == "task_done" for n in items), str([n["kind"] for n in items]))
check("unread_count >= 1", notif.get("unread_count", 0) >= 1, str(notif.get("unread_count")))

print("== 12. mark one read + read-all ==")
one = next((n for n in items if n["kind"] == "task_done"), None)
if one:
    s, b = call("POST", f"/api/org/notifications/{one['id']}/read")
    check("mark read", s == 200 and b.get("read") is True, str(s) + " " + str(b))
s, b = call("POST", "/api/org/notifications/read-all")
check("read-all", s == 200 and "marked" in b, str(s) + " " + str(b))
s, notif = call("GET", "/api/org/notifications?unread_only=true")
check("no unread after read-all", notif.get("unread_count", 1) == 0, str(notif.get("unread_count")))

print("== 13. comments + @mention ==")
s, c = call("POST", f"/api/org/tasks/{dt['id']}/comments", {
    "body": "Nice work — @" + email.split("@")[0] + " please review the queue.",
})
check("comment created", s == 201, str(s) + " " + str(c))
check("mention resolved", len(c.get("mentions", [])) >= 1, str(c.get("mentions")))
s, comments = call("GET", f"/api/org/tasks/{dt['id']}/comments")
check("comment listed", s == 200 and any(x["id"] == c["id"] for x in comments), str(s))
s, notif = call("GET", "/api/org/notifications")
check("mention notification fired", any(n["kind"] == "mention" for n in notif.get("items", [])), str([n["kind"] for n in notif.get("items", [])]))

print("== 14. budget ledger ==")
s, led = call("GET", "/api/org/budget")
check("ledger 200", s == 200, str(s))
check("ledger lists agents", len(led.get("agents", [])) >= 3, str(len(led.get("agents", []))))
check("total_tokens_used > 0", led.get("total_tokens_used", 0) > 0, str(led.get("total_tokens_used")))
rep1_row = next((a for a in led.get("agents", []) if a["agent_id"] == rep1_id), {})
check("rep1 has usage", rep1_row.get("tokens_used", 0) > 0, str(rep1_row.get("tokens_used")))

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
