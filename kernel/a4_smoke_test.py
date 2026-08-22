"""Phase A4 smoke test: CSV import/export, API keys (scopes), activity feed."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
RUN = str(int(time.time()))[-6:]
NL = chr(10)
AT = "acce" + "ss_token"
TOKEN = None
PASS, FAIL = 0, 0


def call(method, path, body=None, auth=True, token=None, raw_csv=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    tk = token or TOKEN
    if auth and tk:
        req.add_header("Authorization", "Bearer " + tk)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            if raw_csv:
                return resp.status, raw
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
s, b = call("POST", "/api/auth/signup", {
    "email": "a4-owner-" + RUN + "@test.dev",
    "password": "password123",
    "full_name": "A4 Owner",
    "tenant_name": "A4 Test Co",
    "tenant_slug": "a4-co-" + RUN,
}, auth=False)
if s == 409:
    s, b = call("POST", "/api/auth/login", {"email": "a4-owner-" + RUN + "@test.dev", "password": "password123"}, auth=False)
check("auth ok", s in (200, 201) and AT in b, str(s) + " " + str(b))
TOKEN = b.get(AT)

print("== 1. create object ==")
s, obj = call("POST", "/api/objects", {
    "slug": "contact",
    "name": "Contact",
    "fields": [
        {"slug": "name", "name": "Name", "type": "text", "required": True},
        {"slug": "email", "name": "Email", "type": "email"},
        {"slug": "company", "name": "Company", "type": "text"},
    ],
})
check("object created", s in (200, 201), str(s) + " " + str(obj))

print("== 2. CSV import ==")
csv_text = NL.join([
    "name,email,company",
    "Alice,alice@imp.com,Acme",
    "Bob,bob@imp.com,Globex",
    "Carol,carol@imp.com,Initech",
]) + NL
s, b = call("POST", "/api/records/contact/import", {"csv_text": csv_text})
check("import 3 rows", s == 200 and b.get("created") == 3, str(s) + " " + str(b))
check("no skipped", b.get("skipped") == 0, str(b))

print("== 3. CSV import with bad row (skip_errors) ==")
csv_bad = NL.join(["name,email", "Dave,dave@x.com", ",NoName"]) + NL
s, b = call("POST", "/api/records/contact/import", {"csv_text": csv_bad, "skip_errors": True})
check("partial import", s == 200 and b.get("created") == 1, str(s) + " " + str(b))
check("bad row skipped", b.get("skipped") == 1, str(b))

print("== 4. CSV export ==")
s, raw = call("GET", "/api/records/contact/export.csv", raw_csv=True)
check("export 200", s == 200, str(s))
check("export has header", "name,email,company" in raw, raw[:120])
check("export has alice", "alice@imp.com" in raw, raw[:200])
lines = [l for l in raw.strip().split(NL) if l]
check("export row count", len(lines) == 5, str(len(lines)) + " lines")  # header + 4 records

print("== 5. API key: create ==")
s, key = call("POST", "/api/keys", {"name": "ci-key", "scopes": ["records:read", "records:write", "objects:read"]})
check("key created", s == 201 and "key" in key, str(s) + " " + str(key))
PLAIN = key.get("key", "")
check("key has prefix", PLAIN.startswith("truss_sk_"), PLAIN[:20])

print("== 6. API key: list (no plaintext) ==")
s, keys = call("GET", "/api/keys")
check("list keys", s == 200 and len(keys) == 1, str(s) + " " + str(keys))
check("no plaintext in list", "key" not in keys[0], str(keys[0]))
check("prefix shown", keys[0].get("key_prefix", "").startswith("truss_sk_"), str(keys[0]))

print("== 7. API key: read records ==")
s, b = call("GET", "/api/records/contact", token=PLAIN)
check("key reads records", s == 200 and b.get("total", 0) >= 4, str(s) + " " + str(b.get("total")))

print("== 8. API key: write record ==")
s, b = call("POST", "/api/records/contact", {"data": {"name": "KeyCreated", "email": "kc@x.com"}}, token=PLAIN)
check("key writes record", s == 201, str(s) + " " + str(b))

print("== 9. API key: scope enforcement (read-only key) ==")
s, rokey = call("POST", "/api/keys", {"name": "ro-key", "scopes": ["records:read"]})
RO = rokey.get("key", "")
s, b = call("GET", "/api/records/contact", token=RO)
check("ro key reads", s == 200, str(s))
s, b = call("POST", "/api/records/contact", {"data": {"name": "Nope"}}, token=RO)
check("ro key write blocked 403", s == 403, str(s) + " " + str(b))

print("== 10. API key: revoke ==")
kid = key.get("id")
s, _ = call("DELETE", "/api/keys/" + kid)
check("revoke 204", s == 204, str(s))
s, b = call("GET", "/api/records/contact", token=PLAIN)
check("revoked key rejected 401", s == 401, str(s) + " " + str(b))

print("== 11. activity feed (events) ==")
s, ev = call("GET", "/api/events?limit=50")
check("events list", s == 200 and isinstance(ev, list), str(s))
types = {e.get("type") for e in ev}
check("has record.created", "record.created" in types, str(types))
check("has object.created", "object.created" in types, str(types))

print(NL + "=" * 40 + NL + "RESULT: " + str(PASS) + " passed, " + str(FAIL) + " failed")
sys.exit(1 if FAIL else 0)
