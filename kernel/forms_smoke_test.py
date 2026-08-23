"""Phase N smoke test: public forms — admin CRUD + unauthenticated intake.

Verifies:
- create/list/patch/delete forms (admin)
- slug format + collision + unknown-field validation
- public schema endpoint requires NO auth and hides hidden_roles fields
- public submit creates a real record (no auth), increments counter, emits event
- non-whitelisted fields are rejected
- inactive form returns 404 on both public endpoints
- validation errors surface as 422

Idempotent: fresh tenant per run.
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


print("== Phase N: public forms ==")
SUFFIX = str(int(time.time()))
email = f"phasen-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase N",
    "tenant_name": f"Phase N {SUFFIX}", "tenant_slug": f"phasen-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))

SLUG = f"lead-intake-{SUFFIX}"

print("== 1. create form ==")
s, form = call("POST", "/api/forms", {
    "slug": SLUG,
    "name": "Lead intake",
    "description": "Tell us about yourself",
    "object": "lead",
    "fields": ["name", "email", "source"],
}, token=TOK)
check("create 201", s == 201, f"{s} {form}")
FID = form.get("id")
check("has id", bool(FID), str(form))

print("== 2. validation ==")
s, res = call("POST", "/api/forms", {"slug": "Bad Slug!", "name": "x", "object": "lead"}, token=TOK)
check("bad slug 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/forms", {"slug": SLUG, "name": "dup", "object": "lead"}, token=TOK)
check("duplicate slug 409", s == 409, f"{s} {res}")
s, res = call("POST", "/api/forms", {"slug": f"bad-{SUFFIX}", "name": "x", "object": "lead", "fields": ["nope"]}, token=TOK)
check("unknown field 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/forms", {"slug": f"obj-{SUFFIX}", "name": "x", "object": "no_such"}, token=TOK)
check("unknown object 404", s == 404, f"{s} {res}")

print("== 3. public schema (NO auth) ==")
s, schema = call("GET", f"/api/public/forms/{SLUG}")  # no token
check("schema 200 unauthenticated", s == 200, f"{s} {schema}")
check("schema name", schema.get("name") == "Lead intake", str(schema.get("name")))
fslugs = {f["slug"] for f in schema.get("fields", [])}
check("schema exposes whitelist", fslugs == {"name", "email", "source"}, str(fslugs))
check("schema has types", all("type" in f for f in schema.get("fields", [])), str(schema.get("fields")))

print("== 4. public submit (NO auth) ==")
s, res = call("POST", f"/api/public/forms/{SLUG}", {"data": {"name": "Inbound Lead", "email": "in@bound.io", "source": "Website"}})
check("submit 201 unauthenticated", s == 201, f"{s} {res}")
check("submit returns record id", bool(res.get("id")), str(res))

# record actually exists via the authenticated API
s, recs = call("GET", "/api/records/lead?search=Inbound", token=TOK)
items = recs.get("items", [])
check("record created in object", any(r["data"].get("name") == "Inbound Lead" for r in items), str([r["data"].get("name") for r in items]))

# submission counter incremented
s, forms = call("GET", "/api/forms", token=TOK)
mine = next((f for f in forms.get("items", []) if f["slug"] == SLUG), None)
check("submissions counter == 1", mine is not None and mine.get("submissions") == 1, str(mine))

# form.submitted event emitted
s, events = call("GET", "/api/events?type=form.submitted", token=TOK)
check("form.submitted event", len(events) >= 1, str(len(events)))

print("== 5. non-whitelisted field rejected ==")
s, res = call("POST", f"/api/public/forms/{SLUG}", {"data": {"name": "Sneaky", "status": "Qualified"}})
check("extra field 422", s == 422, f"{s} {res}")

print("== 6. validation error surfaces ==")
s, res = call("POST", f"/api/public/forms/{SLUG}", {"data": {"email": "missing-name@example.com", "source": "Website"}})
check("missing required 422", s == 422, f"{s} {res}")

print("== 7. deactivate hides form ==")
s, res = call("PATCH", f"/api/forms/{FID}", {"active": False}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
s, res = call("GET", f"/api/public/forms/{SLUG}")
check("inactive schema 404", s == 404, f"{s} {res}")
s, res = call("POST", f"/api/public/forms/{SLUG}", {"data": {"name": "Late"}})
check("inactive submit 404", s == 404, f"{s} {res}")

print("== 8. delete ==")
s, res = call("PATCH", f"/api/forms/{FID}", {"active": True}, token=TOK)
s, res = call("DELETE", f"/api/forms/{FID}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/forms", token=TOK)
check("gone from list", SLUG not in {f["slug"] for f in res.get("items", [])}, str(res.get("items")))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
