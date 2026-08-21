"""Phase 1 smoke test: BYOK AI vault + agent loop against a mock provider."""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
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
            return e.code, {"raw": raw[:300]}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


print("== 0. login as acme owner ==")
s, b = call("POST", "/api/auth/login", {"email": "owner@acme-demo.dev", "password": "password123"}, auth=False)
check("login ok", s == 200 and "access_token" in b, f"{s} {b}")
TOKEN = b.get("access_token")

print("== 1. create AI key (BYOK) ==")
s, b = call("POST", "/api/ai/keys", {
    "name": "mock-provider",
    "provider": "openai-compatible",
    "base_url": "http://127.0.0.1:9999/v1",
    "model": "mock-model",
    "api_key": "test-key-123",
    "is_default": True,
})
if s == 409:
    # already exists from prior run — list and find it
    s2, keys = call("GET", "/api/ai/keys")
    b = next((k for k in keys if k["name"] == "mock-provider"), {})
    s = 200
check("key created", s in (200, 201) and b.get("name") == "mock-provider", f"{s} {b}")
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
check("chat 200", s == 200, f"{s} {b}")
check("agent made tool call", isinstance(b.get("trace"), list) and len(b["trace"]) >= 1, str(b.get("trace")))
if b.get("trace"):
    t0 = b["trace"][0]
    check("tool was create_lead", "create_lead" in t0.get("tool", ""), str(t0))
    check("tool succeeded", "created" in t0.get("result", {}), str(t0.get("result")))
check("final reply present", bool(b.get("reply")), str(b.get("reply")))
check("steps == 2", b.get("steps") == 2, str(b.get("steps")))

print("== 4. record actually created in DB ==")
s, b = call("GET", "/api/records/lead?search=" + urllib.parse.quote("AI Test Lead"))
check("lead exists via agent", s == 200 and b.get("total", 0) >= 1, f"{s} {b}")

print("== 5. agent query tool ==")
s, b = call("POST", "/api/ai/chat", {
    "message": "Search contacts for Jane",
    "key_id": key_id,
})
# mock always calls create_lead first; that's fine — we just verify the loop completes
check("query chat completes", s == 200 and "reply" in b, f"{s}")

print("== 6. no key -> 400 ==")
# delete key then try chat
s, _ = call("DELETE", f"/api/ai/keys/{key_id}")
check("key deleted", s == 204, f"{s}")
s, b = call("POST", "/api/ai/chat", {"message": "hello"})
check("chat without key -> 400", s == 400, f"{s} {b}")

print(f"\n{'='*40}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
