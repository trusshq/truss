"""CI runner: boots mock servers, waits for the kernel, runs every smoke suite.

Usage (kernel must already be running, e.g. via docker compose or uvicorn):
    python run_all_tests.py

Environment:
    TRUSS_TEST_BASE       kernel URL   (default http://127.0.0.1:8000)
    TRUSS_TEST_AI_BASE    mock AI URL  (default http://127.0.0.1:9999/v1)
    TRUSS_TEST_WEBHOOK_RX mock webhook (default http://127.0.0.1:9998)

Exits non-zero if any suite fails.
"""
import os
import re
import subprocess
import sys
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


def main() -> int:
    # Boot mock servers (stdlib http.server, quiet logs)
    mocks = [
        subprocess.Popen([sys.executable, os.path.join(HERE, "mock_openai.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([sys.executable, os.path.join(HERE, "mock_webhook.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]

    try:
        print(f"Waiting for kernel at {BASE} …", flush=True)
        if not wait_for_kernel():
            print("FATAL: kernel did not become healthy in time", flush=True)
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
        for m in mocks:
            m.terminate()


if __name__ == "__main__":
    sys.exit(main())
