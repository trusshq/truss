"""Workspace smoke test: namespace fields, profile, invites, members, RBAC."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
PW = "pass" + "word123"  # demo credential
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")


def req(method, path, auth_token="", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if auth_token:
        r.add_header("Authorization", f"Bearer {auth_token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


# ---------------------------------------------------------------- setup
print("== 1. owner login ==")
st, body = req("POST", "/api/auth/login", body={"email": "owner@acme-demo.dev", "password": PW})
if st != 200:
    st, body = req("POST", "/api/auth/signup", body={
        "email": "owner@acme-demo.dev", "password": PW, "full_name": "Owner",
        "tenant_name": "Acme", "tenant_slug": "acme",
    })
check("owner auth ok", st in (200, 201))
owner = body["access_token"]

print("== 1b. cleanup from prior runs (idempotency) ==")
st, members0 = req("GET", "/api/workspace/members", owner)
if st == 200:
    for m in members0:
        if m["user"]["email"] in ("newbie@acme-demo.dev", "admin1@acme-demo.dev", "m2@acme-demo.dev"):
            req("DELETE", f"/api/workspace/members/{m['membership_id']}", owner)
st, invs0 = req("GET", "/api/workspace/invites", owner)
if st == 200:
    for i in invs0:
        if i["email"] in ("newbie@acme-demo.dev", "admin1@acme-demo.dev", "m2@acme-demo.dev", "ghost@acme-demo.dev", "a2@acme-demo.dev"):
            req("DELETE", f"/api/workspace/invites/{i['id']}", owner)
print("  (cleanup done)")

print("== 2. workspace get (namespace fields) ==")
st, ws = req("GET", "/api/workspace", owner)
check("workspace 200", st == 200)
check("has slug", ws.get("slug") == "acme")
for f in ("description", "website", "industry", "company_size", "logo_url", "timezone", "locale", "settings"):
    check(f"field {f} present", f in ws)

print("== 3. workspace update (admin) ==")
st, ws2 = req("PATCH", "/api/workspace", owner, body={
    "description": "Demo workspace for Truss",
    "website": "https://acme.example.com",
    "industry": "Software",
    "company_size": "11-50",
    "timezone": "Asia/Kolkata",
    "locale": "en-IN",
    "settings": {"brand_color": "#000000", "default_landing": "home"},
})
check("update 200", st == 200)
check("description saved", ws2.get("description") == "Demo workspace for Truss")
check("settings saved", ws2.get("settings", {}).get("brand_color") == "#000000")

print("== 4. roles matrix ==")
st, matrix = req("GET", "/api/workspace/roles", owner)
check("roles 200", st == 200)
check("4 roles", len(matrix) == 4)
viewer_row = next((r for r in matrix if r["role"] == "viewer"), None)
check("viewer read-only", viewer_row and viewer_row["capabilities"]["view_data"] and not viewer_row["capabilities"]["create_edit_records"])

print("== 5. profile update ==")
st, prof = req("PATCH", "/api/auth/profile", owner, body={
    "full_name": "Ada Owner", "title": "Founder", "phone": "+91 98765 43210",
    "timezone": "Asia/Kolkata",
})
check("profile 200", st == 200)
check("title saved", prof.get("title") == "Founder")
st, me = req("GET", "/api/auth/me", owner)
check("me has profile", me.get("full_name") == "Ada Owner" and "last_login_at" in me)

print("== 6. password change ==")
NEWPW = "newpass" + "999"
st, _ = req("POST", "/api/auth/password", owner, body={"current_password": PW, "new_password": NEWPW})
check("password changed", st == 200)
st, _ = req("POST", "/api/auth/login", body={"email": "owner@acme-demo.dev", "password": NEWPW})
check("login with new pw", st == 200)
st, _ = req("POST", "/api/auth/login", body={"email": "owner@acme-demo.dev", "password": PW})
check("old pw rejected", st == 401)
# restore
req("POST", "/api/auth/password", owner, body={"current_password": NEWPW, "new_password": PW})

print("== 7. invite flow ==")
st, inv = req("POST", "/api/workspace/invites", owner, body={"email": "newbie@acme-demo.dev", "role": "member"})
check("invite created", st == 201)
token = inv.get("token", "")
check("has token", len(token) > 20)

st, dup = req("POST", "/api/workspace/invites", owner, body={"email": "newbie@acme-demo.dev", "role": "viewer"})
check("re-invite replaces", st == 201 and dup.get("token") != token)
token = dup.get("token", "")

st, pub = req("GET", f"/api/workspace/invites/by-token/{token}")
check("public resolve 200", st == 200)
check("resolve shows workspace", pub.get("workspace_slug") == "acme" and pub.get("role") == "viewer")

st, acc = req("POST", "/api/workspace/invites/accept", body={"token": token, "password": PW, "full_name": "Newbie"})
check("accept creates account", st == 201)
viewer_tok = acc.get("access_token", "")
check("viewer got token", bool(viewer_tok))
check("role is viewer", acc.get("role") == "viewer")

st, again = req("POST", "/api/workspace/invites/accept", body={"token": token, "password": PW})
check("token single-use", st == 404)

print("== 8. members list ==")
st, members = req("GET", "/api/workspace/members", owner)
check("members 200", st == 200)
check("2 members", len(members) == 2)
viewer_m = next((m for m in members if m["role"] == "viewer"), None)
check("viewer listed", viewer_m is not None)
check("member has profile", viewer_m and viewer_m["user"]["full_name"] == "Newbie")

print("== 9. viewer RBAC: read-only ==")
st, _ = req("GET", "/api/objects", viewer_tok)
check("viewer can list objects", st == 200)
st, _ = req("GET", "/api/records/lead?limit=1", viewer_tok)
check("viewer can read records", st == 200)
st, _ = req("GET", "/api/events?limit=1", viewer_tok)
check("viewer can read events", st == 200)
st, _ = req("GET", "/api/plugins/catalog", viewer_tok)
check("viewer can read catalog", st == 200)
st, _ = req("GET", "/api/workspace", viewer_tok)
check("viewer can read workspace", st == 200)
st, _ = req("GET", "/api/workspace/members", viewer_tok)
check("viewer can list members", st == 200)
# mutations blocked
st, _ = req("POST", "/api/records/lead", viewer_tok, body={"data": {"name": "X", "source": "Web"}})
check("viewer cannot create records", st == 403)
st, _ = req("POST", "/api/plugins/install", viewer_tok, body={"plugin_id": "truss-crm"})
check("viewer cannot install plugins", st == 403)
st, _ = req("PATCH", "/api/workspace", viewer_tok, body={"name": "Hacked"})
check("viewer cannot edit workspace", st == 403)
st, _ = req("POST", "/api/workspace/invites", viewer_tok, body={"email": "x@y.z", "role": "member"})
check("viewer cannot invite", st == 403)
st, _ = req("GET", "/api/connectors", viewer_tok)
check("viewer blocked from connectors (secrets)", st == 403)

print("== 10. role management ==")
viewer_mid = viewer_m["membership_id"]
st, _ = req("PATCH", f"/api/workspace/members/{viewer_mid}", owner, body={"role": "member"})
check("owner promotes viewer->member", st == 200)
st, _ = req("PATCH", f"/api/workspace/members/{viewer_mid}", owner, body={"role": "viewer"})
check("owner demotes back", st == 200)
st, _ = req("PATCH", f"/api/workspace/members/{viewer_mid}", owner, body={"role": "bogus"})
check("invalid role rejected", st == 400)

print("== 11. admin privileges ==")
st, inv2 = req("POST", "/api/workspace/invites", owner, body={"email": "admin1@acme-demo.dev", "role": "admin"})
st, acc2 = req("POST", "/api/workspace/invites/accept", body={"token": inv2["token"], "password": PW, "full_name": "Admin One"})
admin_tok = acc2.get("access_token", "")
check("admin account created", st == 201 and bool(admin_tok))
st, _ = req("PATCH", "/api/workspace", admin_tok, body={"description": "Admin edited"})
check("admin can edit workspace", st == 200)
st, _ = req("POST", "/api/workspace/invites", admin_tok, body={"email": "m2@acme-demo.dev", "role": "member"})
check("admin can invite member", st == 201)
st, _ = req("POST", "/api/workspace/invites", admin_tok, body={"email": "a2@acme-demo.dev", "role": "admin"})
check("admin cannot invite admin", st == 403)
st, members2 = req("GET", "/api/workspace/members", admin_tok)
owner_m = next((m for m in members2 if m["role"] == "owner"), None)
st, _ = req("PATCH", f"/api/workspace/members/{owner_m['membership_id']}", admin_tok, body={"role": "viewer"})
check("admin cannot touch owner", st == 403)
st, _ = req("DELETE", "/api/workspace", admin_tok)
check("admin cannot delete workspace", st == 403)

print("== 12. invite revoke ==")
st, inv3 = req("POST", "/api/workspace/invites", owner, body={"email": "ghost@acme-demo.dev", "role": "viewer"})
st, _ = req("DELETE", f"/api/workspace/invites/{inv3['id']}", owner)
check("revoke 204", st == 204)
st, _ = req("GET", f"/api/workspace/invites/by-token/{inv3['token']}")
check("revoked token unusable", st == 404)

print("== 13. member removal ==")
# m2 was invited by the admin in step 11 — accept the invite so they become a member
st, invs = req("GET", "/api/workspace/invites", owner)
m2_inv = next((i for i in invs if i["email"] == "m2@acme-demo.dev" and i["status"] == "pending"), None)
check("m2 invite pending", m2_inv is not None)
if m2_inv:
    st, _ = req("POST", "/api/workspace/invites/accept", body={"token": m2_inv["token"], "password": PW})
    check("m2 accepted invite", st == 201)
st, members3 = req("GET", "/api/workspace/members", owner)
m2 = next((m for m in members3 if m["user"]["email"] == "m2@acme-demo.dev"), None)
check("m2 exists", m2 is not None)
if m2:
    st, _ = req("DELETE", f"/api/workspace/members/{m2['membership_id']}", owner)
    check("remove member 204", st == 204)
st, members4 = req("GET", "/api/workspace/members", owner)
check("m2 gone", all(m["user"]["email"] != "m2@acme-demo.dev" for m in members4))

print()
print("=" * 40)
print(f"RESULT: {passed} passed, {failed} failed")
