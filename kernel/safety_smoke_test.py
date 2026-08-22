"""Phase A3 smoke test: safety rails — versioning, trash/restore, validation
rules, and field-level permissions."""
import json
import os
import sys
import time

RUN = str(int(time.time()))[-6:]
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    tk = token or TOKEN
    if auth and tk:
        req.add_header("Authorization", f"Bearer {tk}")
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


print("== 0. signup fresh tenant (safety-test) ==")
s, b = call("POST", "/api/auth/signup", {
    "email": f"safety-owner-{RUN}@test.dev",
    "password": "password123",
    "full_name": "Safety Owner",
    "tenant_name": "Safety Test Co",
    "tenant_slug": f"safety-co-{RUN}",
}, auth=False)
if s == 409:
    s, b = call("POST", "/api/auth/login", {"email": f"safety-owner-{RUN}@test.dev", "password": "password123"}, auth=False)
check("auth ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access" + "_token")

print("== 1. create object with rules + hidden field ==")
s, obj = call("POST", "/api/objects", {
    "slug": "employee",
    "name": "Employee",
    "fields": [
        {"slug": "name", "name": "Name", "type": "text", "required": True,
         "options": {"rules": {"min": 2, "max": 50}}},
        {"slug": "email", "name": "Email", "type": "email",
         "options": {"rules": {"unique": True, "pattern": "^[^@]+@[^@]+$"}}},
        {"slug": "salary", "name": "Salary", "type": "currency",
         "options": {"rules": {"min": 0}, "hidden_roles": ["viewer"]}},
        {"slug": "age", "name": "Age", "type": "number",
         "options": {"rules": {"min": 16, "max": 120}}},
    ],
})
if s == 409:
    s, obj = call("GET", "/api/objects/employee")
check("object created", s in (200, 201), f"{s} {obj}")

print("== 2. validation rules: min/max/pattern ==")
s, b = call("POST", "/api/records/employee", {"data": {"name": "A", "email": f"a-{RUN}@x.com"}})
check("name too short -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/records/employee", {"data": {"name": "Alice", "email": "not-an-email"}})
check("bad email pattern -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/records/employee", {"data": {"name": "Alice", "email": f"alice-{RUN}@x.com", "age": 15}})
check("age below min -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/records/employee", {"data": {"name": "Alice", "email": f"alice-{RUN}@x.com", "age": 30, "salary": 50000}})
check("valid record created", s == 201, f"{s} {b}")
rec_id = b.get("id")

print("== 3. unique rule ==")
s, b = call("POST", "/api/records/employee", {"data": {"name": "Alice2", "email": f"alice-{RUN}@x.com"}})
check("duplicate email -> 422", s == 422, f"{s} {b}")

print("== 4. versioning: history on create + update ==")
s, hist = call("GET", f"/api/records/employee/{rec_id}/history")
check("history has v1", s == 200 and len(hist) == 1 and hist[0]["version"] == 1, f"{s} {hist}")
check("v1 actor_type=user", hist[0].get("actor_type") == "user", str(hist[0]))
s, b = call("PATCH", f"/api/records/employee/{rec_id}", {"data": {"salary": 60000}})
check("update ok", s == 200, f"{s} {b}")
s, hist = call("GET", f"/api/records/employee/{rec_id}/history")
check("history has v2", len(hist) == 2 and hist[0]["version"] == 2, f"{len(hist)}")
check("v2 captured new salary", hist[0]["data"].get("salary") == 60000, str(hist[0]["data"]))
check("v1 still has old salary", hist[1]["data"].get("salary") == 50000, str(hist[1]["data"]))

print("== 5. soft delete -> trash ==")
s, b = call("DELETE", f"/api/records/employee/{rec_id}")
check("delete 204", s == 204, f"{s}")
s, b = call("GET", f"/api/records/employee/{rec_id}")
check("record hidden after delete", s == 404, f"{s}")
s, b = call("GET", "/api/records/employee")
check("not in list", b.get("total", 0) == 0, f"{s} {b}")
s, trash = call("GET", "/api/records/trash")
check("in trash", s == 200 and any(t["id"] == rec_id for t in trash), f"{s} {trash}")
check("trash shows object slug", trash[0].get("object") == "employee", str(trash[0]))

print("== 6. restore ==")
s, b = call("POST", f"/api/records/trash/{rec_id}/restore")
check("restore ok", s == 200, f"{s} {b}")
s, b = call("GET", f"/api/records/employee/{rec_id}")
check("record back", s == 200, f"{s}")

print("== 7. purge (admin) ==")
s, _ = call("DELETE", f"/api/records/employee/{rec_id}")
s, b = call("DELETE", f"/api/records/trash/{rec_id}/purge")
check("purge 204", s == 204, f"{s} {b}")
s, trash = call("GET", "/api/records/trash")
check("gone from trash", not any(t["id"] == rec_id for t in trash), f"{trash}")

print("== 8. field-level permissions: viewer sees masked salary ==")
# invite a viewer and accept as a new account
s, inv = call("POST", "/api/workspace/invites", {f"email": "safety-viewer-{RUN}@test.dev", "role": "viewer"})
check("invite created", s in (200, 201), f"{s} {inv}")
vtok = inv.get("token")
s, acc = call("POST", "/api/workspace/invites/accept", {
    "token": vtok, "password": "password123", "full_name": "Safety Viewer",
}, auth=False)
check("viewer accepted", s in (200, 201) and "access_token" in acc, f"{s} {acc}")
viewer_token = acc.get("access" + "_token")

# owner creates a record with salary
s, b = call("POST", "/api/records/employee", {"data": {"name": "Bob", "email": f"bob-{RUN}@x.com", "salary": 90000}})
check("record with salary created", s == 201, f"{s} {b}")
bob_id = b.get("id")

# owner sees salary
s, b = call("GET", f"/api/records/employee/{bob_id}")
check("owner sees salary", b.get("data", {}).get("salary") == 90000, str(b.get("data")))

# viewer sees masked salary
s, b = call("GET", f"/api/records/employee/{bob_id}", token=viewer_token)
check("viewer read ok", s == 200, f"{s}")
check("viewer salary masked", b.get("data", {}).get("salary") == "•••••", str(b.get("data")))

# viewer list also masked
s, b = call("GET", "/api/records/employee", token=viewer_token)
items = b.get("items", [])
check("viewer list masked", all(i["data"].get("salary") == "•••••" for i in items), str(items))

# viewer history also masked
s, hist = call("GET", f"/api/records/employee/{bob_id}/history", token=viewer_token)
check("viewer history masked", all(h["data"].get("salary") == "•••••" for h in hist), str(hist))

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
