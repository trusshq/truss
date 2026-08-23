"""Phase Z smoke test: purchase orders — CRUD, lifecycle, receive-into-inventory.

Verifies:
- create PO referencing products (auto number PO-0001, total computed, bad product 404)
- list filters (status, vendor search)
- get/patch (only draft editable, recomputes total)
- lifecycle: send (draft only), cancel (draft/sent), receive (sent only), 409 guards
- receive applies stock 'in' adjustments and bumps product quantities
- events emitted
- delete (admin)
- tenant isolation

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


print("== Phase Z: purchase orders ==")
SUFFIX = str(int(time.time()))
email = f"phasez-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase Z",
    "tenant_name": f"Phase Z {SUFFIX}", "tenant_slug": f"phasez-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. seed products ==")
s, p1 = call("POST", "/api/inventory/products", {
    "name": "Widget A", "sku": f"WA-{SUFFIX}", "price_cents": 5000, "quantity": 10}, token=TOK)
check("product A created", s == 201, f"{s} {p1}")
s, p2 = call("POST", "/api/inventory/products", {
    "name": "Widget B", "sku": f"WB-{SUFFIX}", "price_cents": 8000, "quantity": 5}, token=TOK)
check("product B created", s == 201, f"{s} {p2}")

print("== 2. create PO ==")
s, po = call("POST", "/api/purchase-orders", {
    "vendor_name": "Supplier Co",
    "expected_date": "2026-10-01",
    "line_items": [
        {"product_id": p1["id"], "quantity": 20, "unit_cost_cents": 3000},
        {"product_id": p2["id"], "quantity": 10, "unit_cost_cents": 6000},
    ],
}, token=TOK)
check("PO created 201", s == 201, f"{s} {po}")
POID = po.get("id")
check("number PO-0001", po.get("number") == "PO-0001", str(po.get("number")))
check("status draft", po.get("status") == "draft", str(po.get("status")))
# 20*3000 + 10*6000 = 60000 + 60000 = 120000
check("total 120000", po.get("total_cents") == 120000, str(po.get("total_cents")))
check("description auto from product", po["line_items"][0]["description"] == "Widget A", str(po["line_items"][0].get("description")))

print("== 3. bad product rejected ==")
s, _ = call("POST", "/api/purchase-orders", {
    "vendor_name": "X", "line_items": [{"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]}, token=TOK)
check("unknown product 404", s == 404, str(s))

print("== 4. list + filters ==")
s, res = call("GET", "/api/purchase-orders", token=TOK)
check("list total 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/purchase-orders?vendor=Supplier", token=TOK)
check("vendor search finds it", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/purchase-orders?status=draft", token=TOK)
check("status filter draft", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/purchase-orders?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 5. patch draft ==")
s, upd = call("PATCH", f"/api/purchase-orders/{POID}", {
    "vendor_name": "Supplier Co", "line_items": [
        {"product_id": p1["id"], "quantity": 5, "unit_cost_cents": 3000}]}, token=TOK)
check("patch 200", s == 200, f"{s} {upd}")
check("total recomputed 15000", upd.get("total_cents") == 15000, str(upd.get("total_cents")))

print("== 6. lifecycle guards ==")
# can't receive a draft
s, _ = call("POST", f"/api/purchase-orders/{POID}/receive", {}, token=TOK)
check("receive draft 409", s == 409, str(s))
# send it
s, sent = call("POST", f"/api/purchase-orders/{POID}/send", {}, token=TOK)
check("send 200", s == 200, str(s))
check("status sent", sent.get("status") == "sent", str(sent.get("status")))
# can't re-send
s, _ = call("POST", f"/api/purchase-orders/{POID}/send", {}, token=TOK)
check("re-send 409", s == 409, str(s))
# can't edit sent
s, _ = call("PATCH", f"/api/purchase-orders/{POID}", {"vendor_name": "Y", "line_items": []}, token=TOK)
check("edit sent 409", s == 409, str(s))

print("== 7. receive into inventory ==")
s, rec = call("POST", f"/api/purchase-orders/{POID}/receive", {}, token=TOK)
check("receive 200", s == 200, f"{s} {rec}")
check("status received", rec.get("status") == "received", str(rec.get("status")))
check("received_at set", bool(rec.get("received_at")), str(rec.get("received_at")))
recv = {r["product_id"]: r for r in rec.get("received", [])}
check("received product A qty 5", recv.get(p1["id"], {}).get("quantity") == 5, str(recv.get(p1["id"])))
check("product A new qty 15 (10+5)", recv.get(p1["id"], {}).get("new_quantity") == 15, str(recv.get(p1["id"])))
# verify product quantity actually bumped
s, prod = call("GET", f"/api/inventory/products/{p1['id']}", token=TOK)
check("product A quantity now 15", prod.get("quantity") == 15, str(prod.get("quantity")))
# stock adjustment recorded
s, adjs = call("GET", f"/api/inventory/products/{p1['id']}/adjustments", token=TOK)
adj_items = adjs.get("items", adjs if isinstance(adjs, list) else [])
po_adj = [a for a in adj_items if "PO-0001" in a.get("reason", "")]
check("stock adjustment recorded for PO", len(po_adj) == 1, str(len(po_adj)))
check("adjustment kind in", po_adj[0].get("kind") == "in" if po_adj else False, str(po_adj))
# can't receive twice
s, _ = call("POST", f"/api/purchase-orders/{POID}/receive", {}, token=TOK)
check("double receive 409", s == 409, str(s))

print("== 8. cancel path on second PO ==")
s, po2 = call("POST", "/api/purchase-orders", {"vendor_name": "Other", "line_items": [
    {"product_id": p2["id"], "quantity": 1, "unit_cost_cents": 100}]}, token=TOK)
check("second PO PO-0002", po2.get("number") == "PO-0002", str(po2.get("number")))
s, can = call("POST", f"/api/purchase-orders/{po2['id']}/cancel", {}, token=TOK)
check("cancel draft 200", s == 200, str(s))
check("status cancelled", can.get("status") == "cancelled", str(can.get("status")))
# can't send cancelled
s, _ = call("POST", f"/api/purchase-orders/{po2['id']}/send", {}, token=TOK)
check("send cancelled 409", s == 409, str(s))

print("== 9. events + delete + isolation ==")
for ev in ("purchase_order.created", "purchase_order.sent", "purchase_order.received", "purchase_order.cancelled"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/purchase-orders/{po2['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/purchase-orders", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phasez2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase Z2",
    "tenant_name": f"Phase Z2 {SUFFIX}", "tenant_slug": f"phasez2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/purchase-orders", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/purchase-orders/{POID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
