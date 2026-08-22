"""Phase G smoke test: CRM first-party app — schema, tools, surfaces, app home data.

Verifies the CRM plugin (built purely on the plugin SDK) provides:
- 5 objects: company, contact, lead, deal, activity
- pipeline stages on deals + amount for pipeline value
- tools: create_lead, update_deal_stage, search_contacts, log_activity
- UI surfaces: crm-home (dashboard), tables, deals kanban
- the analytics queries the App Home view relies on (count, group_by sum)

Idempotent: fresh tenant per run.
"""
import json
import os
import time
import urllib.request
import uuid

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


print("== Phase G: CRM first-party app ==")
SUFFIX = str(int(time.time()))
email = f"crmg-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "CRM G",
    "tenant_name": f"CRM G {SUFFIX}", "tenant_slug": f"crmg-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. install CRM plugin ==")
s, plugins = call("GET", "/api/plugins/catalog", token=TOK)
crm = next((p for p in plugins if p.get("id") == "truss-crm"), None)
check("crm in catalog", crm is not None)
s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))

print("== 2. objects materialized ==")
s, objects = call("GET", "/api/objects", token=TOK)
slugs = {o["slug"] for o in objects}
for want in ("company", "contact", "lead", "deal", "activity"):
    check(f"object '{want}' exists", want in slugs, str(slugs))

print("== 3. deal has pipeline stage + amount fields ==")
deal = next((o for o in objects if o["slug"] == "deal"), None)
field_slugs = {f["slug"] for f in (deal or {}).get("fields", [])}
check("deal.stage field", "stage" in field_slugs, str(field_slugs))
check("deal.amount field", "amount" in field_slugs, str(field_slugs))
stage_field = next((f for f in deal["fields"] if f["slug"] == "stage"), None)
choices = (stage_field or {}).get("options", {}).get("choices", [])
check("pipeline stages", set(choices) >= {"Discovery", "Proposal", "Negotiation", "Won", "Lost"}, str(choices))

print("== 4. activity object fields ==")
act = next((o for o in objects if o["slug"] == "activity"), None)
act_fields = {f["slug"] for f in (act or {}).get("fields", [])}
check("activity.subject", "subject" in act_fields, str(act_fields))
check("activity.type", "type" in act_fields, str(act_fields))
check("activity.done boolean", "done" in act_fields, str(act_fields))

print("== 5. CRM tools registered ==")
s, installed = call("GET", "/api/plugins/catalog", token=TOK)
crm_inst = next((p for p in installed if p.get("id") == "truss-crm"), None)
check("crm installed+enabled flag", bool(crm_inst and crm_inst.get("installed")), str(crm_inst.get("installed") if crm_inst else None))
tool_slugs = {t["slug"] for t in (crm_inst or {}).get("tools", [])}
for want in ("create_lead", "update_deal_stage", "search_contacts", "log_activity"):
    check(f"tool '{want}'", want in tool_slugs, str(tool_slugs))

print("== 6. UI surfaces ==")
ui = (crm_inst or {}).get("ui", [])
ui_by_slug = {u["slug"]: u for u in ui}
check("crm-home dashboard surface", ui_by_slug.get("crm-home", {}).get("view") == "dashboard", str(ui_by_slug.get("crm-home")))
check("crm-home lists objects", set(ui_by_slug.get("crm-home", {}).get("config", {}).get("objects", [])) >= {"lead", "deal", "contact", "company"}, str(ui_by_slug.get("crm-home")))
check("deals kanban surface", ui_by_slug.get("deals-kanban", {}).get("view") == "kanban", str(ui_by_slug.get("deals-kanban")))
check("activities table surface", ui_by_slug.get("activities-table", {}).get("view") == "table", str(ui_by_slug.get("activities-table")))

print("== 7. seed records + app-home analytics ==")
# company + deals across stages with amounts
s, comp = call("POST", "/api/records/company", {"data": {"name": "Acme Corp", "industry": "Software"}}, token=TOK)
check("company created", s in (200, 201), str(s))
for name, stage, amount in [("Deal A", "Discovery", 1000), ("Deal B", "Proposal", 2500), ("Deal C", "Won", 5000)]:
    s, _ = call("POST", "/api/records/deal", {"data": {"name": name, "stage": stage, "amount": amount}}, token=TOK)
    check(f"deal '{name}' created", s in (200, 201), str(s))
s, _ = call("POST", "/api/records/activity", {"data": {"subject": "Intro call", "type": "Call", "done": False}}, token=TOK)
check("activity created", s in (200, 201), str(s))

# count query (used by App Home stat cards)
s, res = call("POST", "/api/insights/query", {"object": "deal", "metric": "count"}, token=TOK)
check("deal count = 3", s == 200 and res.get("value") == 3, f"{s} {res}")

# group_by sum of amount by stage (used by App Home pipeline breakdown)
s, res = call("POST", "/api/insights/query",
              {"object": "deal", "metric": "group_by", "field": "stage", "value_field": "amount"}, token=TOK)
rows = {r["key"]: r["value"] for r in res.get("rows", [])}
check("pipeline by stage", s == 200 and rows.get("Won") == 5000 and rows.get("Proposal") == 2500, f"{s} {rows}")
check("pipeline total = 8500", sum(rows.values()) == 8500, str(rows))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
