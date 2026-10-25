"""One-shot demo seeder — unpacks the committed bundle gzip and drives the API
through its REAL ingestion endpoint (+ one analysis run so the board has data
the moment the UI loads).

Zero dependencies beyond Python stdlib — no httpx/requests install, image stays
tiny. Wait-for-API until /health answers (compose depends_on already orders us,
health-aware), then POST /api/ingest?data_dir=... and POST /api/analysis/run.
"""
from __future__ import annotations

import json
import os
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

API = os.environ.get("API_BASE", "http://api:8000").rstrip("/")
BUNDLE_GZ = Path("/seed/bundle.tar.gz")
WORK = Path(os.environ.get("SEED_DIR", "/tmp/bundle"))
API_DATA_DIR = os.environ.get("API_DATA_DIR", "/tmp/bundle")
MAX_WAIT_S = 180


def _post(path: str) -> dict:
    req = urllib.request.Request(API + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _get(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=15) as r:
        return json.loads(r.read().decode())


def main() -> int:
    READY_DEADLINE = time.time() + MAX_WAIT_S
    while True:
        try:
            if _get("/health").get("status") == "ok":
                break
        except Exception:
            pass
        if time.time() > READY_DEADLINE:
            print("seeder: API never became healthy — aborting", file=sys.stderr)
            return 2
        time.sleep(2)

    WORK.mkdir(parents=True, exist_ok=True)
    with tarfile.open(BUNDLE_GZ, "r:gz") as tar:
        tar.extractall(WORK)

    rep = _post(f"/api/ingest?data_dir={API_DATA_DIR}")
    print(f"seeder: ingested total={rep.get('total_inserted')} checksum_ok={rep.get('checksum_ok')}")

    run = _post("/api/analysis/run")
    print(f"seeder: analysis run {run.get('run_id')} {run.get('status')} "
          f"alerts={run.get('alerts_by_band')} duration_ms={run.get('duration_ms')}")

    alerts = _get("/api/alerts?limit=1")
    print(f"seeder: queue now holds {alerts.get('total')} alerts — demo ready at http://localhost:8080")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
