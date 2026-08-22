"""Phase 1 smoke test: BYOK AI vault + agent loop against a mock provider.

Idempotent: signs up a fresh tenant each run so no leftover AI keys can
interfere with the "no key -> 400" assertion.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
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


print("== 0. signup fresh tenant (ai-test) ==")
email = "ai-owner-" + SUFFIX + "@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email,
    "password": "password123",
    "full_name": "AI Owner",
    "tenant_name": "AI Test Co",
    "tenant_slug": "ai-test-" + SUFFIX,
}, auth=False)
check("auth ok", s in (200, 201) and ("access" + "_token") in b, str(s) + " " + str(b))
TOKEN = b.get("access" + "_token")

print("== 0b. install CRM plugin (gives the agent tools) ==")
s, b = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"})
if s == 409 or (isinstance(b, dict) and b.get("ok")):
    s = 201
check("crm installed", s in (200, 201), str(s) + " " + str(b))

print("== 1. create AI key (BYOK) ==")
s, b = call("POST", "/api/ai/keys", {
    "name": "mock-provider",
    "provider": "openai-compatible",
    "base_url": AI_BASE,
    "model": "mock-model",
    "api_key": "test-key-123",
    "is_default": True,
})
check("key created", s in (200, 201) and b.get("name") == "mock-provider", str(s) + " " + str(b))
key_id = b.get("id")

print("== 2. key is masked in list ==")
s, keys = call("GET", "/api/ai/keys")
mk = next((k for k in keys if k["name"] == "mock-provider"), None)
check("masked key shown", mk and mk.get("api_key_masked") and "test-key-123" not in json.dumps(mk), str(mk))

print("== 3. agent chat: tool-calling loop ==")
s, b = call("POST", "/api/ai/chat", {
    "message": "Create a lead named AI Test Lead with email ai-test@example.com from Website",
    "key_id": key_id,
})
check("chat 200", s == 200, str(s) + " " + str(b))
check("agent made tool call", isinstance(b.get("trace"), list) and len(b["trace"]) >= 1, str(b.get("trace")))
if b.get("trace"):
    t0 = b["trace"][0]
    check("tool was create_lead", "create_lead" in t0.get("tool", ""), str(t0))
    check("tool succeeded", "created" in t0.get("result", {}), str(t0.get("result")))
check("final reply present", bool(b.get("reply")), str(b.get("reply")))
check("steps == 2", b.get("steps") == 2, str(b.get("steps")))

print("== 4. record actually created in DB ==")
s, b = call("GET", "/api/records/lead?search=" + urllib.parse.quote("AI Test Lead"))
check("lead exists via agent", s == 200 and b.get("total", 0) >= 1, str(s) + " " + str(b))

print("== 5. agent query tool ==")
s, b = call("POST", "/api/ai/chat", {
    "message": "Search contacts for Jane",
    "key_id": key_id,
})
# mock always calls create_lead first; that's fine — we just verify the loop completes
check("query chat completes", s == 200 and "reply" in b, str(s))

print("== 6. no key -> 400 ==")
# delete key then try chat (fresh tenant => no other keys to fall back to)
s, _ = call("DELETE", "/api/ai/keys/" + str(key_id))
check("key deleted", s == 204, str(s))
s, b = call("POST", "/api/ai/chat", {"message": "hello"})
check("chat without key -> 400", s == 400, str(s) + " " + str(b))

print("\n" + "=" * 40 + "\nRESULT: " + str(PASS) + " passed, " + str(FAIL) + " failed")
sys.exit(1 if FAIL else 0)
