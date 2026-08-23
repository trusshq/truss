"""Phase O smoke test: file storage & attachments — upload, list, download, delete.

Verifies:
- multipart upload creates a StoredFile + writes bytes to disk
- optional attachment to object + record
- list filters by object / record_id
- download streams the exact bytes back with content type
- oversize upload rejected (413)
- delete removes row + disk file, emits event
- tenant isolation: another tenant can't see/download the file

Idempotent: fresh tenants per run.
"""
import io
import json
import os
import time
import urllib.request
import urllib.error
import uuid

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
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode()) if raw else {}
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode())
        except Exception:
            return e.code, raw


def upload(path, filename, content, content_type, token, fields=None):
    """Multipart/form-data upload via urllib."""
    boundary = "----trussboundary" + uuid.uuid4().hex
    buf = io.BytesIO()

    def part(name, value):
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(value.encode() if isinstance(value, str) else value)
        buf.write(b"\r\n")

    for k, v in (fields or {}).items():
        part(k, v)
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    buf.write(f"Content-Type: {content_type}\r\n\r\n".encode())
    buf.write(content)
    buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(BASE + path, data=buf.getvalue(), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


print("== Phase O: file storage ==")
SUFFIX = str(int(time.time()))
email = f"phaseo-{SUFFIX}@test.dev"
s, b = call("POST", "/api/auth/signup", {
    "email": email, "password": "password123", "full_name": "Phase O",
    "tenant_name": f"Phase O {SUFFIX}", "tenant_slug": f"phaseo-{SUFFIX}",
})
check("signup ok", s in (200, 201) and "access_token" in b, f"{s} {b}")
TOK = b.get("access_token")

s, _ = call("POST", "/api/plugins/install", {"plugin_id": "truss-crm"}, token=TOK)
check("crm installed", s in (200, 201), str(s))

# a record to attach to
s, rec = call("POST", "/api/records/company", {"data": {"name": "FileCo"}}, token=TOK)
check("company created", s in (200, 201), f"{s} {rec}")
RECID = rec.get("id")

print("== 1. upload (unattached) ==")
CONTENT = b"hello truss file storage\n" * 10
s, f = upload("/api/files", "notes.txt", CONTENT, "text/plain", TOK)
check("upload 201", s == 201, f"{s} {f}")
FID = f.get("id")
check("has id", bool(FID), str(f))
check("size recorded", f.get("size") == len(CONTENT), f"{f.get('size')} != {len(CONTENT)}")
check("content type", f.get("content_type") == "text/plain", str(f.get("content_type")))

print("== 2. upload attached to record ==")
s, f2 = upload("/api/files", "contract.pdf", b"%PDF-1.4 fake", "application/pdf", TOK,
               fields={"object": "company", "record_id": RECID})
check("attached upload 201", s == 201, f"{s} {f2}")
FID2 = f2.get("id")
check("object set", f2.get("object") == "company", str(f2.get("object")))
check("record_id set", f2.get("record_id") == RECID, str(f2.get("record_id")))

print("== 3. list + filters ==")
s, res = call("GET", "/api/files", token=TOK)
check("list 200", s == 200, str(s))
check("two files listed", res.get("total") == 2, str(res.get("total")))
s, res = call("GET", "/api/files?object=company", token=TOK)
check("filter by object", res.get("total") == 1 and res["items"][0]["id"] == FID2, str(res.get("total")))
s, res = call("GET", f"/api/files?record_id={RECID}", token=TOK)
check("filter by record", res.get("total") == 1, str(res.get("total")))

print("== 4. download returns exact bytes ==")
s, data = call("GET", f"/api/files/{FID}/download", token=TOK)
check("download 200", s == 200, str(s))
check("bytes match", data == CONTENT, f"len {len(data) if isinstance(data, bytes) else '?'} != {len(CONTENT)}")

print("== 5. oversize rejected ==")
big = b"x" * (26 * 1024 * 1024)  # 26 MB > 25 MB limit
s, res = upload("/api/files", "big.bin", big, "application/octet-stream", TOK)
check("oversize 413", s == 413, f"{s} {res}")

print("== 6. tenant isolation ==")
email2 = f"phaseo2-{SUFFIX}@test.dev"
s, b2 = call("POST", "/api/auth/signup", {
    "email": email2, "password": "password123", "full_name": "Phase O2",
    "tenant_name": f"Phase O2 {SUFFIX}", "tenant_slug": f"phaseo2-{SUFFIX}",
})
TOK2 = b2.get("access_token")
s, res = call("GET", "/api/files", token=TOK2)
check("other tenant sees none", res.get("total") == 0, str(res.get("total")))
s, res = call("GET", f"/api/files/{FID}/download", token=TOK2)
check("other tenant download 404", s == 404, f"{s}")

print("== 7. delete ==")
s, res = call("DELETE", f"/api/files/{FID}", token=TOK)
check("delete 200", s == 200, f"{s} {res}")
s, res = call("GET", "/api/files", token=TOK)
check("one file remains", res.get("total") == 1, str(res.get("total")))
s, res = call("GET", f"/api/files/{FID}/download", token=TOK)
check("deleted download 404", s == 404, f"{s}")
# file.deleted event emitted
s, events = call("GET", "/api/events?type=file.deleted", token=TOK)
check("file.deleted event", len(events) >= 1, str(len(events)))

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
raise SystemExit(1 if FAIL else 0)
