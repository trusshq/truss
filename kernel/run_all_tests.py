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


def start_kernel_in_thread(port: int) -> None:
    """Run uvicorn in a daemon thread. Any startup error is captured and
    re-raised in the main thread so CI sees it immediately."""
    import uvicorn

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
