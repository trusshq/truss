"""CI runner: boots mock servers (and optionally the kernel), runs every suite.

Usage:
    python run_all_tests.py

Environment:
    TRUSS_TEST_BASE          kernel URL   (default http://127.0.0.1:8000)
    TRUSS_TEST_AI_BASE       mock AI URL  (default http://127.0.0.1:9999/v1)
    TRUSS_TEST_WEBHOOK_RX    mock webhook (default http://127.0.0.1:9998)
    TRUSS_TEST_SPAWN_KERNEL  "1" = spawn the kernel ourselves (CI mode: keeps
                             it alive in-process, immune to step/process-group
                             teardown between shell steps)

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
    procs = []

    # Optionally spawn the kernel in-process (CI mode). Using the venv's
    # uvicorn directly avoids `uv run` reinstalling the non-installable
    # local package.
    if os.environ.get("TRUSS_TEST_SPAWN_KERNEL") == "1":
        venv_uv = os.path.join(HERE, ".venv", "bin", "uvicorn")
        if os.name == "nt":
            venv_uv = os.path.join(HERE, ".venv", "Scripts", "uvicorn.exe")
        port = BASE.rsplit(":", 1)[-1].split("/", 1)[0]
        kernel_log = open(os.path.join(HERE, "kernel.log"), "w")
        procs.append(subprocess.Popen(
            [venv_uv, "truss_kernel.main:app", "--host", "127.0.0.1", "--port", port],
            cwd=HERE, stdout=kernel_log, stderr=subprocess.STDOUT,
        ))
        print(f"Spawned kernel (port {port}), log: kernel.log", flush=True)

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
