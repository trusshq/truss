"""Phase Q smoke test: knowledge base — CRUD, publish, public help center, isolation.

Verifies:
- create article (draft by default), slug validation + collision
- list filters (category, status, full-text q)
- get / patch
- publish requires non-empty body; flips status
- public list/read scoped by tenant slug, NO auth
- cross-tenant isolation: tenant B's public KB never shows tenant A's articles
- unpublish hides from public
- delete (admin) + events

Idempotent: fresh tenants per run.
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


print("== Phase Q: knowledge base ==")
SUFFIX = str(int(time.time()))
SLUG_A = f"phaseq-{SUFFIX}"
email = f"phaseq-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase Q",
    "tenant_name": f"Phase Q {SUFFIX}", "tenant_slug": SLUG_A,
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create article (draft) ==")
s, art = call("POST", "/api/kb", {
    "title": "Getting started",
    "slug": f"getting-started-{SUFFIX}",
    "body": "# Welcome\nThis is how you start.",
    "category": "Guides",
    "tags": ["onboarding", "basics"],
}, token=TOK)
check("create 201", s == 201, f"{s} {art}")
AID = art.get("id")
ASLUG = art.get("slug")
check("has id", bool(AID), str(art))
check("draft by default", art.get("status") == "draft", str(art.get("status")))
check("tags stored", art.get("tags") == ["onboarding", "basics"], str(art.get("tags")))

print("== 2. validation ==")
s, res = call("POST", "/api/kb", {"title": "x", "slug": "Bad Slug!"}, token=TOK)
check("bad slug 422", s == 422, f"{s} {res}")
s, res = call("POST", "/api/kb", {"title": "dup", "slug": ASLUG}, token=TOK)
check("duplicate slug 409", s == 409, f"{s} {res}")

print("== 3. list filters ==")
# second article, different category, published later
s, art2 = call("POST", "/api/kb", {
    "title": "Billing FAQ", "slug": f"billing-faq-{SUFFIX}",
    "body": "Answers about billing.", "category": "Billing",
}, token=TOK)
check("second article created", s == 201, f"{s} {art2}")
s, res = call("GET", "/api/kb", token=TOK)
check("list all = 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/kb?category=Billing", token=TOK)
check("filter category", res.get("total") == 1 and res["items"][0]["slug"] == art2["slug"], str(res.get("total")))
s, res = call("GET", "/api/kb?q=Welcome", token=TOK)
check("full-text q", res.get("total") == 1 and res["items"][0]["id"] == AID, str(res.get("total")))
s, res = call("GET", "/api/kb?status=published", token=TOK)
check("filter status (none yet)", res.get("total") == 0, str(res.get("total")))

print("== 4. get + patch ==")
s, res = call("GET", f"/api/kb/{AID}", token=TOK)
check("get 200", s == 200 and res.get("title") == "Getting started", f"{s} {res.get('title')}")
check("get includes body", "Welcome" in res.get("body", ""), str(res.get("body"))[:60])
s, res = call("PATCH", f"/api/kb/{AID}", {"title": "Getting started v2", "category": "Onboarding"}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch title", res.get("title") == "Getting started v2", str(res.get("title")))
check("patch category", res.get("category") == "Onboarding", str(res.get("category")))

print("== 5. publish ==")
# empty article cannot publish
s, empty = call("POST", "/api/kb", {"title": "Empty", "slug": f"empty-{SUFFIX}", "body": "   "}, token=TOK)
check("empty article created", s == 201, f"{s} {empty}")
s, res = call("POST", f"/api/kb/{empty['id']}/publish", token=TOK)
check("publish empty 422", s == 422, f"{s} {res}")

s, res = call("POST", f"/api/kb/{AID}/publish", token=TOK)
check("publish 200", s == 200, f"{s} {res}")
check("status published", res.get("status") == "published", str(res.get("status")))

print("== 6. public help center (NO auth, tenant-scoped) ==")
s, res = call("GET", f"/api/public/kb/{SLUG_A}")  # no token
check("public list 200 unauthenticated", s == 200, f"{s} {res}")
check("public shows only published", res.get("total") == 1 and res["items"][0]["slug"] == ASLUG, str(res.get("total")))
check("public list omits body", "body" not in res["items"][0], str(res["items"][0].keys()))

s, res = call("GET", f"/api/public/kb/{SLUG_A}/{ASLUG}")  # no token
check("public read 200 unauthenticated", s == 200, f"{s} {res}")
check("public read has body", "Welcome" in res.get("body", ""), str(res.get("body"))[:60])

# draft article not publicly readable
s, res = call("GET", f"/api/public/kb/{SLUG_A}/{art2['slug']}")
check("draft not public 404", s == 404, f"{s} {res}")

print("== 7. cross-tenant isolation on public KB ==")
SLUG_B = f"phaseq2-{SUFFIX}"
email2 = f"phaseq2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase Q2",
    "tenant_name": f"Phase Q2 {SUFFIX}", "tenant_slug": SLUG_B,
})
check("tenant B signup", s in (200, 201), f"{s} {b2}")
# tenant B's public KB must NOT contain tenant A's published article
s, res = call("GET", f"/api/public/kb/{SLUG_B}")
check("tenant B public empty", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/public/kb/{SLUG_B}/{ASLUG}")
check("tenant B cannot read A's article", s == 404, f"{s} {res}")
# unknown workspace
s, res = call("GET", "/api/public/kb/no-such-workspace")
check("unknown workspace 404", s == 404, f"{s} {res}")

print("== 8. unpublish hides from public ==")
s, res = call("POST", f"/api/kb/{AID}/unpublish", token=TOK)
check("unpublish 200", s == 200, f"{s} {res}")
check("status draft again", res.get("status") == "draft", str(res.get("status")))
s, res = call("GET", f"/api/public/kb/{SLUG_A}/{ASLUG}")
check("unpublished not public 404", s == 404, f"{s} {res}")

print("== 9. delete + events ==")
s, res = call("DELETE", f"/api/kb/{AID}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/kb", token=TOK)
check("two remain (billing + empty)", res.get("total") == 2, str(res.get("total")))
s, events = call("GET", "/api/events?type=kb.article_deleted", token=TOK)
check("delete event emitted", len(events) >= 1, str(len(events)))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
