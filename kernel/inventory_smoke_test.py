"""Phase U smoke test: inventory & products — CRUD, stock adjustments, low stock.

Verifies:
- create product (SKU collision 409, initial stock recorded as adjustment)
- list filters (category, low_stock, active, q search)
- get/patch/delete
- stock adjustments: in/out/set with validation
  - 'in' adds, 'out' subtracts (over-withdraw 409), 'set' absolute
  - negative/zero delta rejected per kind
- adjustment audit trail (resulting_quantity snapshots, ordered desc)
- low_stock flag + inventory.low_stock event when at/below reorder point
- events emitted; tenant isolation

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


print("== Phase U: inventory ==")
SUFFIX = str(int(time.time()))
email = f"phaseu-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase U",
    "tenant_name": f"Phase U {SUFFIX}", "tenant_slug": f"phaseu-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create product ==")
s, p = call("POST", "/api/inventory/products", {
    "name": "Wireless Mouse", "sku": "WM-001", "category": "Electronics",
    "price_cents": 2500, "currency": "usd", "quantity": 50, "reorder_point": 10,
}, token=TOK)
check("create 201", s == 201, f"{s} {p}")
PID = p.get("id")
check("currency uppercased", p.get("currency") == "USD", str(p.get("currency")))
check("quantity 50", p.get("quantity") == 50, str(p.get("quantity")))
check("not low stock", p.get("low_stock") is False, str(p.get("low_stock")))

s, res = call("POST", "/api/inventory/products", {"name": "dup", "sku": "WM-001"}, token=TOK)
check("SKU collision 409", s == 409, f"{s} {res}")

print("== 2. initial stock recorded as adjustment ==")
s, res = call("GET", f"/api/inventory/products/{PID}/adjustments", token=TOK)
check("one initial adjustment", res.get("total") == 1, str(res.get("total")))
check("initial is set kind", res["items"][0]["kind"] == "set", str(res["items"][0].get("kind")))
check("initial resulting 50", res["items"][0]["resulting_quantity"] == 50, str(res["items"][0].get("resulting_quantity")))

print("== 3. more products for filters ==")
s, p2 = call("POST", "/api/inventory/products", {
    "name": "USB Cable", "sku": "UC-002", "category": "Electronics",
    "price_cents": 800, "quantity": 5, "reorder_point": 20,
}, token=TOK)
check("second product (low stock)", s == 201, f"{s} {p2}")
PID2 = p2.get("id")
check("low stock flagged", p2.get("low_stock") is True, str(p2.get("low_stock")))
s, p3 = call("POST", "/api/inventory/products", {
    "name": "Notebook", "sku": "NB-003", "category": "Stationery", "price_cents": 300, "quantity": 100,
}, token=TOK)
check("third product", s == 201, f"{s} {p3}")

print("== 4. list filters ==")
s, res = call("GET", "/api/inventory/products", token=TOK)
check("list all = 3", res.get("total") == 3, str(res.get("total")))
s, res = call("GET", "/api/inventory/products?category=Electronics", token=TOK)
check("filter category = 2", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/inventory/products?low_stock=true", token=TOK)
check("filter low_stock = 1", res.get("total") == 1 and res["items"][0]["id"] == PID2, str(res.get("total")))
s, res = call("GET", "/api/inventory/products?q=mouse", token=TOK)
check("search q = 1", res.get("total") == 1 and res["items"][0]["id"] == PID, str(res.get("total")))

print("== 5. stock adjustments ==")
s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "in", "delta": 20, "reason": "restock"}, token=TOK)
check("adjust in 201", s == 201, f"{s} {res}")
check("in -> 70", res["product"]["quantity"] == 70, str(res["product"].get("quantity")))

s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "out", "delta": 30, "reason": "order #123"}, token=TOK)
check("adjust out 201", s == 201, f"{s} {res}")
check("out -> 40", res["product"]["quantity"] == 40, str(res["product"].get("quantity")))

s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "out", "delta": 999}, token=TOK)
check("over-withdraw 409", s == 409, f"{s} {res}")

s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "set", "delta": 100, "reason": "stocktake"}, token=TOK)
check("adjust set 201", s == 201, f"{s} {res}")
check("set -> 100", res["product"]["quantity"] == 100, str(res["product"].get("quantity")))

s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "in", "delta": -5}, token=TOK)
check("negative in 422", s == 422, f"{s} {res}")
s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "out", "delta": 0}, token=TOK)
check("zero out 422", s == 422, f"{s} {res}")
s, res = call("POST", f"/api/inventory/products/{PID}/adjust", {"kind": "bogus", "delta": 1}, token=TOK)
check("bad kind 422", s == 422, f"{s} {res}")

print("== 6. adjustment audit trail ==")
s, res = call("GET", f"/api/inventory/products/{PID}/adjustments", token=TOK)
check("4 adjustments total", res.get("total") == 4, str(res.get("total")))
kinds = [a["kind"] for a in res["items"]]
check("ordered desc (set last op first)", kinds[0] == "set", str(kinds))
check("resulting snapshots", res["items"][0]["resulting_quantity"] == 100, str(res["items"][0].get("resulting_quantity")))

print("== 7. low stock event ==")
# bring PID2 (already low) down further to trigger low_stock event
s, res = call("POST", f"/api/inventory/products/{PID2}/adjust", {"kind": "out", "delta": 2, "reason": "sold"}, token=TOK)
check("low stock adjust 201", s == 201, f"{s} {res}")
s, events = call("GET", "/api/events?type=inventory.low_stock", token=TOK)
check("low_stock event emitted", len(events) >= 1, str(len(events)))
s, events = call("GET", "/api/events?type=inventory.stock_adjusted", token=TOK)
check("stock_adjusted event emitted", len(events) >= 1, str(len(events)))

print("== 8. patch + delete + isolation ==")
s, res = call("PATCH", f"/api/inventory/products/{PID}", {"price_cents": 2999, "reorder_point": 15}, token=TOK)
check("patch 200", s == 200, f"{s} {res}")
check("patch price", res.get("price_cents") == 2999, str(res.get("price_cents")))
check("patch reorder_point", res.get("reorder_point") == 15, str(res.get("reorder_point")))

s, res = call("DELETE", f"/api/inventory/products/{p3['id']}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/inventory/products", token=TOK)
check("two remain", res.get("total") == 2, str(res.get("total")))

email2 = f"phaseu2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase U2",
    "tenant_name": f"Phase U2 {SUFFIX}", "tenant_slug": f"phaseu2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/inventory/products", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/inventory/products/{PID}", token=TOK2)
check("other tenant get 404", s == 404, f"{s}")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
