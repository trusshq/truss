"""Phase Y smoke test: quotes & proposals — CRUD, lifecycle, convert-to-invoice.

Verifies:
- create quote with line items (auto number QT-0001, totals computed)
- list filters (status, customer search)
- get/patch (recomputes totals; only draft/sent editable)
- lifecycle: send (draft only), accept/decline (sent only), 409 on bad transitions
- convert accepted quote -> invoice record (requires truss-invoices plugin)
- delete (admin)
- events emitted
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


print("== Phase Y: quotes ==")
SUFFIX = str(int(time.time()))
email = f"phasey-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase Y",
    "tenant_name": f"Phase Y {SUFFIX}", "tenant_slug": f"phasey-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. create quote with line items ==")
s, q = call("POST", "/api/quotes", {
    "customer_name": "Acme Corp",
    "title": "Website redesign",
    "currency": "USD",
    "valid_until": "2026-12-31",
    "line_items": [
        {"description": "Design", "quantity": 10, "unit_price_cents": 15000},
        {"description": "Development", "quantity": 20, "unit_price_cents": 20000},
    ],
}, token=TOK)
check("quote created 201", s == 201, f"{s} {q}")
QID = q.get("id")
check("number QT-0001", q.get("number") == "QT-0001", str(q.get("number")))
check("status draft", q.get("status") == "draft", str(q.get("status")))
# 10*15000 + 20*20000 = 150000 + 400000 = 550000
check("subtotal 550000", q.get("subtotal_cents") == 550000, str(q.get("subtotal_cents")))
check("total 550000", q.get("total_cents") == 550000, str(q.get("total_cents")))

print("== 2. list + filters ==")
s, res = call("GET", "/api/quotes", token=TOK)
check("list total 1", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/quotes?customer=Acme", token=TOK)
check("customer search finds it", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/quotes?customer=Nope", token=TOK)
check("customer search miss", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", "/api/quotes?status=draft", token=TOK)
check("status filter draft", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/quotes?status=bogus", token=TOK)
check("bad status 400", s == 400, str(s))

print("== 3. get + patch recomputes totals ==")
s, got = call("GET", f"/api/quotes/{QID}", token=TOK)
check("get 200", s == 200, str(s))
s, upd = call("PATCH", f"/api/quotes/{QID}", {
    "customer_name": "Acme Corp",
    "title": "Website redesign v2",
    "line_items": [{"description": "Design", "quantity": 5, "unit_price_cents": 10000}],
}, token=TOK)
check("patch 200", s == 200, f"{s} {upd}")
check("totals recomputed 50000", upd.get("total_cents") == 50000, str(upd.get("total_cents")))

print("== 4. lifecycle transitions ==")
# can't accept a draft
s, _ = call("POST", f"/api/quotes/{QID}/accept", {}, token=TOK)
check("accept draft 409", s == 409, str(s))
# send it
s, sent = call("POST", f"/api/quotes/{QID}/send", {}, token=TOK)
check("send 200", s == 200, str(s))
check("status sent", sent.get("status") == "sent", str(sent.get("status")))
# can't re-send
s, _ = call("POST", f"/api/quotes/{QID}/send", {}, token=TOK)
check("re-send 409", s == 409, str(s))
# can't convert before accept
s, _ = call("POST", f"/api/quotes/{QID}/convert", {}, token=TOK)
check("convert sent 409", s == 409, str(s))
# accept it
s, acc = call("POST", f"/api/quotes/{QID}/accept", {}, token=TOK)
check("accept 200", s == 200, str(s))
check("status accepted", acc.get("status") == "accepted", str(acc.get("status")))
# accepted quote can't be edited
s, _ = call("PATCH", f"/api/quotes/{QID}", {"customer_name": "X", "line_items": []}, token=TOK)
check("edit accepted 409", s == 409, str(s))

print("== 5. convert to invoice (needs truss-invoices plugin) ==")
# without plugin -> 409
s, res = call("POST", f"/api/quotes/{QID}/convert", {}, token=TOK)
check("convert w/o plugin 409", s == 409, str(s))
# install invoices plugin
s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-invoices"}, token=TOK)
check("invoices plugin installed", s in (200, 201), str(s))
# now convert
s, conv = call("POST", f"/api/quotes/{QID}/convert", {}, token=TOK)
check("convert 200", s == 200, f"{s} {conv}")
check("status converted", conv.get("status") == "converted", str(conv.get("status")))
check("invoice_record_id set", bool(conv.get("invoice_record_id")), str(conv.get("invoice_record_id")))
# can't convert twice
s, _ = call("POST", f"/api/quotes/{QID}/convert", {}, token=TOK)
check("double convert 409", s == 409, str(s))
# invoice record exists with mapped fields
s, inv = call("GET", f"/api/records/invoice/{conv['invoice_record_id']}", token=TOK)
check("invoice record 200", s == 200, str(s))
inv_data = inv.get("data", {})
check("invoice number INV-QT-0001", inv_data.get("number") == "INV-QT-0001", str(inv_data.get("number")))
check("invoice customer Acme", inv_data.get("customer") == "Acme Corp", str(inv_data.get("customer")))
check("invoice amount 500.0", abs(float(inv_data.get("amount", 0)) - 500.0) < 0.01, str(inv_data.get("amount")))

print("== 6. decline path on a second quote ==")
s, q2 = call("POST", "/api/quotes", {"customer_name": "Beta", "line_items": [
    {"description": "Item", "quantity": 1, "unit_price_cents": 100}]}, token=TOK)
check("second quote QT-0002", q2.get("number") == "QT-0002", str(q2.get("number")))
call("POST", f"/api/quotes/{q2['id']}/send", {}, token=TOK)
s, dec = call("POST", f"/api/quotes/{q2['id']}/decline", {}, token=TOK)
check("decline 200", s == 200, str(s))
check("status declined", dec.get("status") == "declined", str(dec.get("status")))

print("== 7. events + delete + isolation ==")
for ev in ("quote.created", "quote.sent", "quote.accepted", "quote.converted", "quote.declined"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
s, _ = call("DELETE", f"/api/quotes/{q2['id']}", token=TOK)
check("delete 200", s == 200, str(s))
s, res = call("GET", "/api/quotes", token=TOK)
check("one remains after delete", res.get("total") == 1, str(res.get("total")))
# other tenant sees nothing
email2 = f"phasey2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase Y2",
    "tenant_name": f"Phase Y2 {SUFFIX}", "tenant_slug": f"phasey2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/quotes", token=TOK2)
check("other tenant empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/quotes/{QID}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
