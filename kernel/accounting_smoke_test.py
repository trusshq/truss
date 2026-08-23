"""Major Phase 8 smoke test: accounting/GL — accounts, journal, trial balance.

Verifies:
- accounts: create (type validation, code unique), list filters
  (account_type, status), get/patch, delete (blocked while lines exist)
- journal entries: create requires >= 2 lines, each line non-zero and
  not both debit+credit, entry must balance, archived account rejected
- entry lifecycle: draft editable/deletable, post (admin, balanced),
  posted immutable (edit/delete/post again rejected)
- trial balance: posted entries only, per-account totals, as_of filter,
  balanced flag
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


print("== Major Phase 8: accounting / GL ==")
SUFFIX = str(int(time.time()))
email = f"phase8-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase 8",
    "tenant_name": f"Phase 8 {SUFFIX}", "tenant_slug": f"phase8-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

print("== 1. accounts ==")
s, cash = call("POST", "/api/accounting/accounts", {
    "code": "1000", "name": "Cash", "account_type": "asset",
}, token=TOK)
check("account cash created 201", s == 201, f"{s} {cash}")
CASH = cash.get("id")
s, rev = call("POST", "/api/accounting/accounts", {
    "code": "4000", "name": "Revenue", "account_type": "revenue",
}, token=TOK)
REV = rev.get("id")
check("account revenue created", s == 201, str(s))
s, exp = call("POST", "/api/accounting/accounts", {
    "code": "6000", "name": "Rent Expense", "account_type": "expense",
}, token=TOK)
EXP = exp.get("id")
# duplicate code
s, _ = call("POST", "/api/accounting/accounts", {"code": "1000", "name": "Dup", "account_type": "asset"}, token=TOK)
check("duplicate code 409", s == 409, str(s))
# bad type
s, _ = call("POST", "/api/accounting/accounts", {"code": "9999", "name": "X", "account_type": "bogus"}, token=TOK)
check("bad account_type 400", s == 400, str(s))
# list + filters
s, res = call("GET", "/api/accounting/accounts", token=TOK)
check("accounts total 3", res.get("total") == 3, str(res.get("total")))
s, res = call("GET", "/api/accounting/accounts?account_type=asset", token=TOK)
check("type filter asset", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/accounting/accounts?account_type=bogus", token=TOK)
check("bad type filter 400", s == 400, str(s))
# patch
s, pa = call("PATCH", f"/api/accounting/accounts/{EXP}", {"description": "Office rent"}, token=TOK)
check("patch account 200", s == 200, str(s))
check("description set", pa.get("description") == "Office rent", str(pa.get("description")))

print("== 2. journal entry validation ==")
# needs >= 2 lines
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01", "lines": [{"account_id": CASH, "debit_cents": 100}],
}, token=TOK)
check("single line 400", s == 400, str(s))
# unbalanced
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01",
    "lines": [{"account_id": CASH, "debit_cents": 100}, {"account_id": REV, "credit_cents": 50}],
}, token=TOK)
check("unbalanced 400", s == 400, str(s))
# line with both debit and credit
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01",
    "lines": [{"account_id": CASH, "debit_cents": 100, "credit_cents": 100}, {"account_id": REV, "credit_cents": 100}],
}, token=TOK)
check("both debit+credit 400", s == 400, str(s))
# zero line
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01",
    "lines": [{"account_id": CASH, "debit_cents": 0}, {"account_id": REV, "credit_cents": 0}],
}, token=TOK)
check("zero line 400", s == 400, str(s))
# bad source
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01", "source": "bogus",
    "lines": [{"account_id": CASH, "debit_cents": 100}, {"account_id": REV, "credit_cents": 100}],
}, token=TOK)
check("bad source 400", s == 400, str(s))

print("== 3. balanced entry + lifecycle ==")
# revenue received: debit cash 100000, credit revenue 100000
s, e1 = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-01", "memo": "August revenue", "source": "invoice",
    "lines": [
        {"account_id": CASH, "debit_cents": 100000, "memo": "cash in"},
        {"account_id": REV, "credit_cents": 100000, "memo": "earned"},
    ],
}, token=TOK)
check("entry created 201", s == 201, f"{s} {e1}")
E1 = e1.get("id")
check("status draft", e1.get("status") == "draft", str(e1.get("status")))
check("2 lines", len(e1.get("lines", [])) == 2, str(len(e1.get("lines", []))))
check("total debit", e1.get("total_debit_cents") == 100000, str(e1.get("total_debit_cents")))
check("total credit", e1.get("total_credit_cents") == 100000, str(e1.get("total_credit_cents")))
# draft editable
s, pe = call("PATCH", f"/api/accounting/entries/{E1}", {"memo": "August revenue (final)"}, token=TOK)
check("patch draft 200", s == 200, str(s))
check("memo updated", pe.get("memo") == "August revenue (final)", str(pe.get("memo")))
# post
s, posted = call("POST", f"/api/accounting/entries/{E1}/post", token=TOK)
check("post 200", s == 200, str(s))
check("status posted", posted.get("status") == "posted", str(posted.get("status")))
# posted immutable
s, _ = call("PATCH", f"/api/accounting/entries/{E1}", {"memo": "nope"}, token=TOK)
check("edit posted 409", s == 409, str(s))
s, _ = call("POST", f"/api/accounting/entries/{E1}/post", token=TOK)
check("repost 409", s == 409, str(s))
s, _ = call("DELETE", f"/api/accounting/entries/{E1}", token=TOK)
check("delete posted 409", s == 409, str(s))

print("== 4. second entry + trial balance ==")
# rent paid: debit expense 30000, credit cash 30000 (later date)
s, e2 = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-08-15", "memo": "August rent", "source": "expense",
    "lines": [
        {"account_id": EXP, "debit_cents": 30000},
        {"account_id": CASH, "credit_cents": 30000},
    ],
}, token=TOK)
E2 = e2.get("id")
check("entry 2 created", s == 201, str(s))
s, _ = call("POST", f"/api/accounting/entries/{E2}/post", token=TOK)
check("post entry 2", s == 200, str(s))
# trial balance (all posted)
s, tb = call("GET", "/api/accounting/trial-balance", token=TOK)
check("trial balance 200", s == 200, str(s))
check("balanced", tb.get("balanced") is True, str(tb.get("balanced")))
check("total debit 130000", tb.get("total_debit_cents") == 130000, str(tb.get("total_debit_cents")))
check("total credit 130000", tb.get("total_credit_cents") == 130000, str(tb.get("total_credit_cents")))
rows = {r["code"]: r for r in tb.get("rows", [])}
check("cash net 70000", rows.get("1000", {}).get("net_cents") == 70000, str(rows.get("1000", {}).get("net_cents")))
check("revenue credit 100000", rows.get("4000", {}).get("credit_cents") == 100000, str(rows.get("4000", {}).get("credit_cents")))
check("expense debit 30000", rows.get("6000", {}).get("debit_cents") == 30000, str(rows.get("6000", {}).get("debit_cents")))
# as_of before rent: only revenue entry
s, tb2 = call("GET", "/api/accounting/trial-balance?as_of=2026-08-10", token=TOK)
check("as_of total debit 100000", tb2.get("total_debit_cents") == 100000, str(tb2.get("total_debit_cents")))
check("as_of balanced", tb2.get("balanced") is True, str(tb2.get("balanced")))

print("== 5. draft delete + account guards + events + isolation ==")
# draft entry deletable
s, e3 = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-09-01",
    "lines": [{"account_id": CASH, "debit_cents": 1}, {"account_id": REV, "credit_cents": 1}],
}, token=TOK)
E3 = e3.get("id")
s, _ = call("DELETE", f"/api/accounting/entries/{E3}", token=TOK)
check("delete draft 200", s == 200, str(s))
# account delete blocked while lines exist
s, _ = call("DELETE", f"/api/accounting/accounts/{CASH}", token=TOK)
check("delete account w/ lines 409", s == 409, str(s))
# archived account rejected for new lines
s, arch = call("POST", "/api/accounting/accounts", {"code": "9000", "name": "Old", "account_type": "asset"}, token=TOK)
ARCH = arch.get("id")
s, _ = call("PATCH", f"/api/accounting/accounts/{ARCH}", {"status": "archived"}, token=TOK)
s, _ = call("POST", "/api/accounting/entries", {
    "entry_date": "2026-09-01",
    "lines": [{"account_id": ARCH, "debit_cents": 1}, {"account_id": REV, "credit_cents": 1}],
}, token=TOK)
check("archived account line 409", s == 409, str(s))
# archived account deletable (no lines)
s, _ = call("DELETE", f"/api/accounting/accounts/{ARCH}", token=TOK)
check("delete unused account 200", s == 200, str(s))
# entry list filters
s, res = call("GET", "/api/accounting/entries?status=posted", token=TOK)
check("entry status filter posted", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/accounting/entries?source=invoice", token=TOK)
check("entry source filter", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", "/api/accounting/entries?status=bogus", token=TOK)
check("entry bad status 400", s == 400, str(s))
for ev in ("accounting.account_created", "accounting.entry_created", "accounting.entry_posted"):
    s, events = call("GET", f"/api/events?type={ev}", token=TOK)
    check(f"{ev} emitted", len(events) >= 1, f"{s} {len(events) if isinstance(events, list) else events}")
# other tenant sees nothing
email2 = f"phase8b-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase 8b",
    "tenant_name": f"Phase 8b {SUFFIX}", "tenant_slug": f"phase8b-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/accounting/accounts", token=TOK2)
check("other tenant accounts empty", s == 200 and res.get("total") == 0, str(res.get("total")))
s, _ = call("GET", f"/api/accounting/entries/{E1}", token=TOK2)
check("cross-tenant get 404", s == 404, str(s))
s, tb3 = call("GET", "/api/accounting/trial-balance", token=TOK2)
check("other tenant tb empty", s == 200 and tb3.get("total_debit_cents") == 0, str(tb3.get("total_debit_cents")))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
