"""Phase D smoke test: intelligence & insight — analytics, scorecards, timeline,
and natural-language data queries via the kernel analytics tool.

Idempotent: fresh tenant per run.

CRM schema notes (from truss-crm/plugin.json):
- lead fields: name, email, source, status, notes
    source choices: Website, Referral, Cold Outreach, Event, Social, Other
    status choices: New, Contacted, Qualified, Unqualified, Converted
- deal fields: name, stage, amount(currency), company, close_date, notes
    stage choices: Discovery, Proposal, Negotiation, Won, Lost
"""
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


print("== 0. signup fresh tenant ==")
email = "insight-owner-" + SUFFIX + "@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email,
    "password": "password123",
    "full_name": "Insight Owner",
    "tenant_name": "Insight Test Co",
    "tenant_slug": "insight-test-" + SUFFIX,
}, auth=False)
check("auth ok", s in (200, 201) and ("access" + "_token") in b, str(s) + " " + str(b))
TOKEN = b.get("access" + "_token")

print("== 1. install CRM + AI key -> mock provider ==")
s, b = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"})
if s == 409 or (isinstance(b, dict) and b.get("ok")):
    s = 201
check("crm installed", s in (200, 201), str(s) + " " + str(b))
s, b = call("POST", "/api/ai/keys", {
    "name": "insight-mock",
    "provider": "openai-compatible",
    "base_url": AI_BASE,
    "model": "mock-model",
    "api_key": "test-key-123",
    "is_default": True,
})
check("ai key created", s in (200, 201), str(s) + " " + str(b))
key_id = b.get("id")

print("== 2. seed 5 leads (valid source/status choices) ==")
leads = [
    {"name": "Alpha Corp", "email": "a-" + SUFFIX + "@x.com", "source": "Website", "status": "New"},
    {"name": "Beta LLC", "email": "b-" + SUFFIX + "@x.com", "source": "Website", "status": "Qualified"},
    {"name": "Gamma Inc", "email": "g-" + SUFFIX + "@x.com", "source": "Referral", "status": "New"},
    {"name": "Delta Co", "email": "d-" + SUFFIX + "@x.com", "source": "Referral", "status": "Converted"},
    {"name": "Epsilon Ltd", "email": "e-" + SUFFIX + "@x.com", "source": "Cold Outreach", "status": "New"},
]
seeded = 0
for ld in leads:
    s, b = call("POST", "/api/records/lead", {"data": ld})
    if s == 201:
        seeded += 1
    else:
        print("    seed failed:", ld["name"], s, b)
check("5 leads seeded", seeded == 5, str(seeded))

print("== 2b. seed 5 deals with amounts (for numeric analytics) ==")
deals = [
    {"name": "Deal A", "stage": "Discovery", "amount": "1000"},
    {"name": "Deal B", "stage": "Proposal", "amount": "2500"},
    {"name": "Deal C", "stage": "Discovery", "amount": "500"},
    {"name": "Deal D", "stage": "Won", "amount": "4000"},
    {"name": "Deal E", "stage": "Negotiation", "amount": "750"},
]
dseeded = 0
for d in deals:
    s, b = call("POST", "/api/records/deal", {"data": d})
    if s == 201:
        dseeded += 1
    else:
        print("    seed failed:", d["name"], s, b)
check("5 deals seeded", dseeded == 5, str(dseeded))

print("== 3. analytics: count leads ==")
s, b = call("POST", "/api/insights/query", {"object": "lead", "metric": "count"})
check("count 200", s == 200, str(s) + " " + str(b))
check("lead count == 5", b.get("value") == 5, str(b.get("value")))

print("== 4. analytics: group_by lead source ==")
s, b = call("POST", "/api/insights/query", {"object": "lead", "metric": "group_by", "field": "source"})
check("group_by 200", s == 200, str(s) + " " + str(b))
rows = {r["key"]: r["value"] for r in b.get("rows", [])}
check("Website == 2", rows.get("Website") == 2, str(rows))
check("Referral == 2", rows.get("Referral") == 2, str(rows))
check("Cold Outreach == 1", rows.get("Cold Outreach") == 1, str(rows))

print("== 5. analytics: sum of deal amount ==")
s, b = call("POST", "/api/insights/query", {"object": "deal", "metric": "sum", "field": "amount"})
check("sum 200", s == 200, str(s) + " " + str(b))
check("sum == 8750", abs(b.get("value", 0) - 8750) < 0.01, str(b.get("value")))

print("== 6. analytics: avg of deal amount ==")
s, b = call("POST", "/api/insights/query", {"object": "deal", "metric": "avg", "field": "amount"})
check("avg == 1750", abs(b.get("value", 0) - 1750) < 0.01, str(b.get("value")))

print("== 7. analytics: group_by deal stage sum amount ==")
s, b = call("POST", "/api/insights/query", {
    "object": "deal", "metric": "group_by", "field": "stage", "value_field": "amount",
})
check("group_by sum 200", s == 200, str(s) + " " + str(b))
rows = {r["key"]: r["value"] for r in b.get("rows", [])}
check("Won sum == 4000", abs(rows.get("Won", 0) - 4000) < 0.01, str(rows))
check("Discovery sum == 1500", abs(rows.get("Discovery", 0) - 1500) < 0.01, str(rows))

print("== 8. analytics: time_series leads ==")
s, b = call("POST", "/api/insights/query", {"object": "lead", "metric": "time_series", "bucket": "day", "days": 7})
check("time_series 200", s == 200, str(s) + " " + str(b))
total = sum(r["count"] for r in b.get("rows", []))
check("time_series total == 5", total == 5, str(total))

print("== 9. analytics: bad object -> 422 ==")
s, b = call("POST", "/api/insights/query", {"object": "nonexistent", "metric": "count"})
check("bad object 422", s == 422, str(s) + " " + str(b))

print("== 10. insights: object counts ==")
s, b = call("GET", "/api/insights/objects")
check("objects 200", s == 200, str(s))
lead_obj = next((o for o in b if o["slug"] == "lead"), None)
check("lead object present", lead_obj is not None, str([o["slug"] for o in b]))
if lead_obj:
    check("lead count == 5", lead_obj.get("count") == 5, str(lead_obj.get("count")))

print("== 11. hire agent + run a task for scorecard ==")
s, ag = call("POST", "/api/agents", {
    "name": "Ivy Analyst", "role": "Analyst", "icon": "📊",
    "ai_key_id": key_id, "permission_role": "member",
})
check("agent hired", s == 201, str(s) + " " + str(ag))
ag_id = ag.get("id")
s, t = call("POST", f"/api/agents/{ag_id}/tasks", {
    "agent_id": ag_id,
    "title": "Count the leads", "description": "How many leads do we have?",
})
check("task created", s == 201, str(s) + " " + str(t))
task_id = t.get("id")
s, b = call("POST", f"/api/agents/{ag_id}/tasks/{task_id}/run")
check("task run 200", s == 200, str(s) + " " + str(b.get("error", "")))

print("== 12. agent scorecard ==")
s, card = call("GET", f"/api/insights/agents/{ag_id}")
check("scorecard 200", s == 200, str(s) + " " + str(card))
check("scorecard name", card.get("name") == "Ivy Analyst", str(card.get("name")))
check("tasks total >= 1", card.get("tasks", {}).get("total", 0) >= 1, str(card.get("tasks")))
check("completion_rate present", "completion_rate" in card, str(card.keys()))

print("== 13. all scorecards ==")
s, cards = call("GET", "/api/insights/agents")
check("all scorecards 200", s == 200, str(s))
check("at least 1 card", len(cards) >= 1, str(len(cards)))

print("== 14. workspace overview ==")
s, ov = call("GET", "/api/insights/overview")
check("overview 200", s == 200, str(s) + " " + str(ov))
check("agents_total >= 1", ov.get("agents_total", 0) >= 1, str(ov))
check("tasks_total >= 1", ov.get("tasks_total", 0) >= 1, str(ov))

print("== 15. activity timeline ==")
s, tl = call("GET", "/api/insights/timeline?limit=50")
check("timeline 200", s == 200, str(s))
check("timeline non-empty", len(tl) >= 1, str(len(tl)))
kinds = {it.get("kind") for it in tl}
check("timeline has events", "event" in kinds, str(kinds))
types = {it.get("type") for it in tl}
check("timeline has record.created", "record.created" in types, str(types))

print("== 16. natural-language analytics via agent (kernel__analytics tool) ==")
s, chat = call("POST", "/api/ai/chat", {"message": "How many leads do we have in total?"})
check("chat 200", s == 200, str(s) + " " + str(chat.get("error", "")))
trace = chat.get("trace", [])
analytics_calls = [t for t in trace if t.get("tool") == "kernel__analytics"]
check("agent used analytics tool", len(analytics_calls) >= 1, str([t.get("tool") for t in trace]))
if analytics_calls:
    res = analytics_calls[0].get("result", {})
    check("analytics tool returned count", res.get("metric") == "count" and res.get("value") == 5, str(res))

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
