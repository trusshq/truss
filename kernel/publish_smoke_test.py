"""Phase J smoke test: plugin publishing pipeline — versioning, listing, unpublish.

Verifies:
- publish creates a plugin + installs it
- re-publish with SAME/LOWER version is rejected (409)
- re-publish with HIGHER version updates + bumps install version
- GET /api/marketplace/published lists it
- builtin ids cannot be shadowed
- unpublish removes it + disables installs (data preserved)

Idempotent: fresh tenant + unique plugin id per run.
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


def manifest(pid, version):
    return {
        "id": pid,
        "name": "Publish Test Plugin",
        "version": version,
        "description": "Phase J publish pipeline test",
        "author": "phase-j",
        "icon": "🚀",
        "objects": [
            {
                "slug": "gadget",
                "name": "Gadget",
                "name_plural": "Gadgets",
                "fields": [
                    {"slug": "name", "name": "Name", "type": "text", "required": True, "position": 0},
                    {"slug": "price", "name": "Price", "type": "currency", "position": 1},
                ],
            }
        ],
        "tools": [
            {
                "slug": "create_gadget",
                "name": "Create Gadget",
                "description": "Create a gadget",
                "action": "create_record",
                "object": "gadget",
                "params": [{"name": "name", "type": "string", "required": True}],
            }
        ],
        "ui": [{"slug": "gadgets-table", "label": "Gadgets", "view": "table", "object": "gadget"}],
    }


print("== Phase J: plugin publishing pipeline ==")
SUFFIX = str(int(time.time()))
email = f"phasej-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase J",
    "tenant_name": f"Phase J {SUFFIX}", "tenant_slug": f"phasej-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")
PID = f"pubtest-{SUFFIX}"

print("== 1. publish v1.0.0 ==")
s, res = call("POST", "/api/marketplace/publish", {"manifest": manifest(PID, "1.0.0"), "install": True}, token=TOK)
check("publish 201", s == 201, f"{s} {res}")
check("publish installed", res.get("installed") is True, str(res))
check("publish not update", res.get("updated") is False, str(res))

print("== 2. re-publish same version rejected ==")
s, res = call("POST", "/api/marketplace/publish", {"manifest": manifest(PID, "1.0.0"), "install": True}, token=TOK)
check("same version 409", s == 409, f"{s} {res}")

print("== 3. re-publish lower version rejected ==")
s, res = call("POST", "/api/marketplace/publish", {"manifest": manifest(PID, "0.9.0"), "install": True}, token=TOK)
check("lower version 409", s == 409, f"{s} {res}")

print("== 4. re-publish higher version updates ==")
s, res = call("POST", "/api/marketplace/publish", {"manifest": manifest(PID, "1.1.0"), "install": True}, token=TOK)
check("bump 201", s == 201, f"{s} {res}")
check("bump flagged update", res.get("updated") is True, str(res))
check("bump version 1.1.0", res.get("version") == "1.1.0", str(res))

# install row version bumped
s, catalog = call("GET", "/api/plugins/catalog", token=TOK)
inst = next((p for p in catalog if p.get("id") == PID), None)
check("catalog shows v1.1.0", inst is not None and inst.get("version") == "1.1.0", str(inst.get("version") if inst else None))

print("== 5. published listing ==")
s, res = call("GET", "/api/marketplace/published", token=TOK)
check("published 200", s == 200, str(s))
ids = {p["id"]: p for p in res.get("items", [])}
check("listed", PID in ids, str(list(ids)))
check("listed version", ids.get(PID, {}).get("version") == "1.1.0", str(ids.get(PID)))

print("== 6. builtin cannot be shadowed ==")
s, res = call("POST", "/api/marketplace/publish", {"manifest": manifest("truss-crm", "9.9.9"), "install": False}, token=TOK)
check("builtin shadow 409", s == 409, f"{s} {res}")

print("== 7. unpublish ==")
s, res = call("DELETE", f"/api/marketplace/publish/{PID}", token=TOK)
check("unpublish 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/marketplace/published", token=TOK)
check("gone from listing", PID not in {p["id"] for p in res.get("items", [])}, str(res.get("items")))
# manifest removed from discovery -> gone from catalog
s, catalog = call("GET", "/api/plugins/catalog", token=TOK)
check("gone from catalog", PID not in {p.get("id") for p in catalog}, str([p.get("id") for p in catalog]))
# BUT the materialized object + data are preserved (disable, not delete)
s, objs = call("GET", "/api/objects", token=TOK)
check("gadget object preserved", "gadget" in {o["slug"] for o in objs}, str([o["slug"] for o in objs]))

print("== 8. unpublish unknown/builtin guarded ==")
s, res = call("DELETE", "/api/marketplace/publish/nope-not-real", token=TOK)
check("unknown 404", s == 404, f"{s} {res}")
s, res = call("DELETE", "/api/marketplace/publish/truss-crm", token=TOK)
check("builtin unpublish 409", s == 409, f"{s} {res}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
