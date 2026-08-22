"""Phase E smoke test: developer platform — SDK validation, publish flow,
typed dev endpoints (OpenAPI + reference).

Idempotent: fresh tenant per run; published plugin id is unique per run.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
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
email = "dev-owner-" + SUFFIX + "@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email,
    "password": "password123",
    "full_name": "Dev Owner",
    "tenant_name": "Dev Test Co",
    "tenant_slug": "dev-test-" + SUFFIX,
}, auth=False)
check("auth ok", s in (200, 201) and ("access" + "_token") in b, str(s) + " " + str(b))
TOKEN = b.get("access" + "_token")

print("== 1. dev: OpenAPI spec endpoint ==")
s, spec = call("GET", "/api/dev/openapi.json")
check("openapi 200", s == 200, str(s))
check("openapi has paths", isinstance(spec.get("paths"), dict) and len(spec["paths"]) > 10, str(len(spec.get("paths", {}))))
check("openapi version", spec.get("openapi", "").startswith("3."), str(spec.get("openapi")))

print("== 2. dev: markdown reference ==")
req = urllib.request.Request(BASE + "/api/dev/reference")
req.add_header("Authorization", "Bearer " + TOKEN)
with urllib.request.urlopen(req) as resp:
    ref = resp.read().decode()
check("reference 200", True)
check("reference mentions records", "/api/records" in ref, ref[:100])
check("reference mentions publish", "/api/marketplace/publish" in ref, ref[:100])

print("== 3. validate: good manifest ==")
good_manifest = {
    "id": "dev-plugin-" + SUFFIX,
    "name": "Dev Plugin",
    "version": "1.0.0",
    "description": "A test plugin",
    "author": "dev-test",
    "icon": "🧪",
    "permissions": ["objects:write", "records:write"],
    "objects": [
        {
            "slug": "widget",
            "name": "Widget",
            "name_plural": "Widgets",
            "icon": "🧪",
            "fields": [
                {"slug": "name", "name": "Name", "type": "text", "required": True, "position": 0},
                {"slug": "qty", "name": "Qty", "type": "number", "position": 1},
            ],
        }
    ],
    "tools": [
        {
            "slug": "create_widget",
            "name": "Create Widget",
            "description": "Create a widget",
            "action": "create_record",
            "object": "widget",
            "params": [{"name": "name", "type": "string", "required": True}],
        }
    ],
    "ui": [{"slug": "widgets-table", "label": "Widgets", "view": "table", "object": "widget"}],
}
s, b = call("POST", "/api/marketplace/validate", good_manifest)
check("validate 200", s == 200, str(s) + " " + str(b))
check("validate ok", b.get("ok") is True, str(b))
check("validate counts", b.get("objects") == 1 and b.get("tools") == 1, str(b))

print("== 4. validate: bad manifest returns errors ==")
bad_manifest = {
    "id": "Bad-ID",
    "name": "Bad",
    "version": "1.0",
    "objects": [{"slug": "x", "name": "X", "fields": [{"slug": "f", "name": "F", "type": "bogus"}]}],
    "tools": [{"slug": "t", "name": "T", "description": "d", "action": "create_record"}],
}
s, b = call("POST", "/api/marketplace/validate", bad_manifest)
check("validate bad 200", s == 200, str(s))
check("validate bad ok=false", b.get("ok") is False, str(b))
errs = b.get("errors", [])
check("errors mention version", any("version" in e for e in errs), str(errs))
check("errors mention field type", any("bogus" in e for e in errs), str(errs))
check("errors mention tool object", any("object" in e for e in errs), str(errs))

print("== 5. publish: valid plugin ==")
s, b = call("POST", "/api/marketplace/publish", {"manifest": good_manifest, "install": True})
check("publish 201", s == 201, str(s) + " " + str(b))
check("publish ok", b.get("ok") is True, str(b))
check("publish installed", b.get("installed") is True, str(b))
check("publish version", b.get("version") == "1.0.0", str(b.get("version")))

print("== 6. published plugin is usable ==")
s, objs = call("GET", "/api/objects")
check("objects 200", s == 200, str(s))
widget = next((o for o in objs if o["slug"] == "widget"), None)
check("widget object materialized", widget is not None, str([o["slug"] for o in objs]))
if widget:
    s, rec = call("POST", "/api/records/widget", {"data": {"name": "Test Widget", "qty": "5"}})
    check("create widget record", s == 201, str(s) + " " + str(rec))

print("== 7. publish: duplicate id rejected ==")
s, b = call("POST", "/api/marketplace/publish", {"manifest": good_manifest, "install": False})
check("duplicate 409", s == 409, str(s) + " " + str(b))

print("== 8. publish: builtin id rejected ==")
builtin_manifest = dict(good_manifest)
builtin_manifest["id"] = "truss-crm"
s, b = call("POST", "/api/marketplace/publish", {"manifest": builtin_manifest, "install": False})
check("builtin collision 409", s == 409, str(s) + " " + str(b))

print("== 9. publish: invalid manifest rejected 422 ==")
s, b = call("POST", "/api/marketplace/publish", {"manifest": bad_manifest, "install": False})
check("invalid publish 422", s == 422, str(s) + " " + str(b))

print("== 10. published plugin appears in registry catalog ==")
s, plugins = call("GET", "/api/plugins/catalog")
check("catalog 200", s == 200, str(s))
ids = [p.get("id") for p in (plugins if isinstance(plugins, list) else plugins.get("items", []))]
check("published plugin listed", ("dev-plugin-" + SUFFIX) in ids, str(ids))

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
