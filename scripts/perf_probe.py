"""Phase-08 performance probe — real measurements on THIS machine.

Usage (with API on :8000 against the seeded DB):
    .venv/bin/python scripts/perf_probe.py [base_url]

Measures:
  1. p50/p95/p99 latency over 200 sequential GET /api/alerts?limit=50
  2. the same for /api/alerts/{max-id} (heaviest evidence payload)
  3. RSS of the uvicorn process before/after the loop
  4. CPU/RAM of this machine, config hash of frozen rules.yaml
Pastable output lines are emitted directly.
"""
from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def bench(path: str, calls: int = 200) -> list[float]:
    timings = []
    for _ in range(calls):
        t0 = time.perf_counter()
        with urllib.request.urlopen(BASE + path, timeout=15) as r:
            r.read()
        timings.append((time.perf_counter() - t0) * 1000)
    return timings


def quote(ts: list[float]) -> str:
    ts = sorted(ts)
    p = lambda q: ts[min(int(len(ts) * q), len(ts) - 1)]
    return f"p50={p(.50):.1f}ms p95={p(.95):.1f}ms p99={p(.99):.1f}ms mean={statistics.mean(ts):.1f}ms max={max(ts):.1f}ms"


def total_ram_gb() -> float:
    with open("/proc/meminfo") as f:
        kb = int(f.readline().split()[1])
    return kb / 1_048_576


def api_rss_mb() -> float:
    out = subprocess.check_output(["bash", "-c", "pgrep -f 'uvicorn app.main' | xargs -I{} ps -o rss= -p {}"], text=True)
    vals = [int(l.strip()) for l in out.splitlines() if l.strip()]
    return sum(vals) / 1024


with open("infra/config/rules.yaml", "rb") as f:
    rules_sha = hashlib.sha256(f.read()).hexdigest()[:16]

alerts = json.loads(urllib.request.urlopen(BASE + "/api/alerts?limit=1", timeout=15).read())
max_id = alerts["items"][0]["alert_id"]
print(f"machine: {platform.processor()} · RAM {total_ram_gb():.1f} GB · python {platform.python_version()}")
print(f"rules.yaml sha256[:16] = {rules_sha} (frozen v1.0)")
print(f"api RSS BEFORE = {api_rss_mb():.0f} MB")

t = bench("/api/alerts?limit=50", 200)
print(f"GET /api/alerts?limit=50 ×200: {quote(t)}")

t = bench(f"/api/alerts/{max_id}", 200)
print(f"GET /api/alerts/{max_id} (max evidence) ×200: {quote(t)}")

print(f"api RSS AFTER  = {api_rss_mb():.0f} MB  (target: < 450 MB with 1 worker)")
