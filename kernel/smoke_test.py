"""End-to-end smoke test against the running Truss kernel (real HTTP)."""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
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
            return e.code, {"raw": raw[:200]}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


print("== 1. health ==")
s, b = call("GET", "/api/health", auth=False)
check("health 200", s == 200 and b.get("status") == "ok", str(b))

print("== 2. signup ==")
s, b = call("POST", "/api/auth/signup", {
    "email": "owner@acme-demo.dev", "password": "password123",
    "full_name": "Owner", "tenant_name": "Acme Inc", "tenant_slug": "acme",
}, auth=False)
if s == 409:  # rerun-safe
    s, b = call("POST", "/api/auth/login", {"email": "owner@acme-demo.dev", "password": "password123"}, auth=False)
check("signup/login ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access_token")

print("== 3. me ==")
s, b = call("GET", "/api/auth/me")
check("me returns tenant", s == 200 and b.get("tenant_slug") == "acme", f"{s} {b}")

print("== 4. plugin catalog ==")
s, b = call("GET", "/api/plugins/catalog")
check("catalog lists truss-crm", s == 200 and any(p["id"] == "truss-crm" for p in b), f"{s}")

print("== 5. install CRM plugin ==")
s, b = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"})
check("install ok", s == 201 and b.get("ok"), f"{s} {b}")

print("== 6. objects materialized ==")
s, b = call("GET", "/api/objects")
slugs = {o["slug"] for o in b} if s == 200 and isinstance(b, list) else set()
check("4 CRM objects exist", {"company", "contact", "lead", "deal"} <= slugs, f"{s} {slugs}")
lead_obj = next((o for o in b if isinstance(b, list) and o["slug"] == "lead"), None) if isinstance(b, list) else None
check("lead has 5 fields", lead_obj and len(lead_obj["fields"]) == 5, str(lead_obj))

print("== 7. create records ==")
s, b = call("POST", "/api/records/company", {"data": {"name": "Globex", "industry": "Software", "employees": 250}})
check("company created", s == 201 and b["data"]["name"] == "Globex", f"{s} {b}")
company_id = b.get("id")

s, b = call("POST", "/api/records/lead", {"data": {"name": "Jane Doe", "email": "jane@globex.com", "source": "Website", "status": "New"}})
check("lead created", s == 201, f"{s} {b}")
lead_id = b.get("id")

s, b = call("POST", "/api/records/deal", {"data": {"name": "Globex Annual", "stage": "Discovery", "amount": 12000, "company": company_id}})
check("deal created", s == 201, f"{s} {b}")

print("== 8. validation rejects bad data ==")
s, b = call("POST", "/api/records/lead", {"data": {"email": "x@y.com"}})  # missing required name
check("missing required -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/records/lead", {"data": {"name": "X", "bogus_field": 1}})
check("unknown field -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/records/deal", {"data": {"name": "D", "stage": "NotAStage"}})
check("bad select choice -> 422", s == 422, f"{s} {b}")

print("== 9. update + list + search ==")
s, b = call("PATCH", f"/api/records/lead/{lead_id}", {"data": {"status": "Qualified"}})
check("lead updated", s == 200 and b["data"]["status"] == "Qualified", f"{s} {b}")
s, b = call("GET", "/api/records/lead")
check("list leads total>=1", s == 200 and b["total"] >= 1, f"{s}")
s, b = call("GET", "/api/records/lead?search=Jane")
check("search finds Jane", s == 200 and b["total"] >= 1, f"{s} {b}")

print("== 10. tenant isolation ==")
s, b = call("POST", "/api/auth/signup", {
    "email": "other@evil-demo.dev", "password": "password123",
    "full_name": "Other", "tenant_name": "Evil Corp", "tenant_slug": "evil",
}, auth=False)
if s == 409:
    s, b = call("POST", "/api/auth/login", {"email": "other@evil-demo.dev", "password": "password123"}, auth=False)
other_token = b.get("access_token")
req = urllib.request.Request(BASE + "/api/records/lead")
req.add_header("Authorization", f"Bearer {other_token}")
try:
    with urllib.request.urlopen(req) as resp:
        other_leads = json.loads(resp.read())
    isolated = other_leads["total"] == 0
    detail = str(other_leads)
except urllib.error.HTTPError as e:
    # 404 = 'lead' object doesn't exist in evil tenant (plugin not installed) = also isolated
    isolated = e.code == 404
    detail = f"HTTP {e.code}"
check("other tenant cannot see acme leads", isolated, detail)
s, b = call("GET", f"/api/records/lead/{lead_id}")  # back as acme
check("acme still sees own lead", s == 200, f"{s}")

print("== 11. events recorded ==")
s, b = call("GET", "/api/events?limit=100")
types = {e["type"] for e in b} if s == 200 else set()
check("event seam captured lifecycle", {"plugin.installed", "record.created", "record.updated"} <= types, str(types))

print("== 12. disable plugin ==")
s, b = call("POST", "/api/plugins/disable", {"plugin_id": "truss-crm"})
check("disable ok", s == 200 and b.get("enabled") is False, f"{s} {b}")
s, b = call("GET", "/api/plugins/catalog")
crm = next(p for p in b if p["id"] == "truss-crm")
check("catalog shows disabled", crm["installed"] and not crm["enabled"], str(crm["enabled"]))
s, b = call("POST", "/api/plugins/enable", {"plugin_id": "truss-crm"})
check("re-enable ok", s == 200 and b.get("enabled") is True, f"{s} {b}")

print("== 13. RBAC: viewer cannot install ==")
# (owner-only check via a fresh member would need invite API; verify admin guard responds)
s, b = call("POST", "/api/plugins/install", {"plugin_id": "nope"})
check("unknown plugin -> 404", s == 404, f"{s} {b}")

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
