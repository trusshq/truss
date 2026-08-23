"""CI runner: boots mock servers (and optionally the kernel), runs every suite.

Usage:
    python run_all_tests.py

Environment:
    TRUSS_TEST_BASE          kernel URL   (default http://127.0.0.1:8000)
    TRUSS_TEST_AI_BASE       mock AI URL  (default http://127.0.0.1:9999/v1)
    TRUSS_TEST_WEBHOOK_RX    mock webhook (default http://127.0.0.1:9998)
    TRUSS_TEST_SPAWN_KERNEL  "1" = run the kernel in-process on a daemon thread
                             (CI mode: no subprocess lifecycle, immune to
                             process-group teardown between shell steps)

Exits non-zero if any suite fails.
"""
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

BASE = os.environ.get("TRUSS_TEST_BASE", "http://127.0.0.1:8000")
HERE = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    "smoke_test.py",
    "phase4_smoke_test.py",
    "automation_smoke_test.py",
    "connector_smoke_test.py",
    "ai_smoke_test.py",
    "marketplace_smoke_test.py",
    "workspace_smoke_test.py",
    "agent_smoke_test.py",
    "safety_smoke_test.py",
    "a4_smoke_test.py",
    "org_smoke_test.py",
    "orchestration_smoke_test.py",
    "insights_smoke_test.py",
    "devplatform_smoke_test.py",
    "chatcontrol_smoke_test.py",
    "crm_app_smoke_test.py",
    "aidepth_smoke_test.py",
    "publish_smoke_test.py",
    "audit_smoke_test.py",
    "billing_smoke_test.py",
    "reports_smoke_test.py",
    "forms_smoke_test.py",
    "files_smoke_test.py",
    "calendar_smoke_test.py",
    "kb_smoke_test.py",
    "time_smoke_test.py",
    "expenses_smoke_test.py",
    "projects_smoke_test.py",
    "inventory_smoke_test.py",
    "hr_smoke_test.py",
    "dashboard_smoke_test.py",
    "approvals_smoke_test.py",
    "quotes_smoke_test.py",
    "purchase_orders_smoke_test.py",
    "contracts_smoke_test.py",
    "tickets_smoke_test.py",
]


def wait_for_kernel(timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _check_db(url: str) -> str:
    """Try a raw TCP connect to the Postgres host:port. Returns a diagnostic."""
    import re
    m = re.search(r"@([^:/]+):(\d+)/", url)
    if not m:
        return f"could not parse host:port from {url!r}"
    host, port = m.group(1), int(m.group(2))
    import socket
    try:
        with socket.create_connection((host, port), timeout=5):
            return f"TCP connect to {host}:{port} OK"
    except Exception as e:  # noqa: BLE001
        return f"TCP connect to {host}:{port} FAILED: {e!r}"


def start_kernel_in_thread(port: int) -> None:
    """Run uvicorn in a daemon thread. Startup logs are teed to kernel.log so
    the on-failure CI step can surface them; any startup error is captured and
    re-raised in the main thread so CI sees it immediately."""
    import logging
    import uvicorn

    # Tee uvicorn + app logs into kernel.log (the CI failure step tails this).
    fh = logging.FileHandler(os.path.join(HERE, "kernel.log"), mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "truss_kernel", ""):
        lg = logging.getLogger(name)
        lg.addHandler(fh)
        lg.setLevel(logging.INFO)

    errors: list[BaseException] = []

    def run() -> None:
        try:
            uvicorn.run(
                "truss_kernel.main:app",
                host="127.0.0.1",
                port=port,
                log_level="info",
            )
        except BaseException as e:  # noqa: BLE001 — surface ANY startup failure
            errors.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Give the thread a moment to fail fast (bad import/config), then let the
    # health poll below do the real waiting.
    time.sleep(2)
    if errors:
        raise RuntimeError(f"kernel failed to start: {errors[0]!r}") from errors[0]
    print(f"Kernel thread started on port {port}", flush=True)


def main() -> int:
    procs = []

    # Optionally run the kernel in-process (CI mode).
    if os.environ.get("TRUSS_TEST_SPAWN_KERNEL") == "1":
        db_url = os.environ.get("TRUSS_DATABASE_URL", "")
        print(f"DB pre-check: {_check_db(db_url)}", flush=True)
        port = int(BASE.rsplit(":", 1)[-1].split("/", 1)[0])
        start_kernel_in_thread(port)

    # Boot mock servers (stdlib http.server, quiet logs)
    procs += [
        subprocess.Popen([sys.executable, os.path.join(HERE, "mock_openai.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([sys.executable, os.path.join(HERE, "mock_webhook.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]

    try:
        print(f"Waiting for kernel at {BASE} …", flush=True)
        if not wait_for_kernel():
            print("FATAL: kernel did not become healthy in time", flush=True)
            log_path = os.path.join(HERE, "kernel.log")
            if os.path.exists(log_path):
                print("--- kernel.log (last 60 lines) ---", flush=True)
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    for line in f.readlines()[-60:]:
                        print(line.rstrip(), flush=True)
            return 2
        print("Kernel healthy. Running suites…\n", flush=True)

        total_pass = total_fail = 0
        results = []
        for suite in SUITES:
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, suite)],
                capture_output=True, text=True, cwd=HERE, timeout=600,
            )
            m = re.search(r"RESULT:\s*(\d+)\s*passed,\s*(\d+)\s*failed", proc.stdout)
            if m:
                p, f = int(m.group(1)), int(m.group(2))
                total_pass += p
                total_fail += f
                results.append((suite, p, f, proc.returncode))
                print(f"  {suite}: {p} passed, {f} failed", flush=True)
                if f or proc.returncode != 0:
                    # surface the failing lines for CI logs
                    for line in proc.stdout.splitlines():
                        if "FAIL" in line:
                            print(f"    {line}", flush=True)
            else:
                results.append((suite, 0, 0, proc.returncode or 1))
                total_fail += 1
                print(f"  {suite}: NO RESULT (rc={proc.returncode})", flush=True)
                print(proc.stdout[-2000:], flush=True)
                print(proc.stderr[-2000:], flush=True)

        print(f"\nTOTAL: {total_pass} passed, {total_fail} failed across {len(SUITES)} suites", flush=True)
        return 1 if total_fail else 0
    finally:
        for m in procs:
            m.terminate()


if __name__ == "__main__":
    sys.exit(main())
