# PERF.md — measured, on this machine (Phase 08 §5)

**Machine:** sandbox container · 2 vCPU-class · RAM 1.9 GB · Python 3.13 ·
uvicorn single-worker (free-tier shape) · PostgreSQL 16 on localhost ·
rules.yaml frozen v1.0 sha256[:16] = `388d16b5faa2b519` · measured 2026-10-24
(part of `scripts/perf_probe.py` — re-runnable any time).

## Pipeline (48h-of-bank reality: 46,978 txns + 9,124 activity rows)

| Stage | Wall time |
|---|---:|
| Ingest 57,821 rows (idempotent, sha-verified) | ~12 s (first run) |
| Graph build (NetworkX, 35,319 edges from frames) | **653 ms** |
| Full analysis run T+E+F → persist (14 rules + fusion + merge + per-alert evidence) | **~7.1 s** per run |
| ⏱ End-to-end on 50k txns (target < 120 s) | **≈ 8 s total after ingest — 15× under target** ✅ |

## API latency (200 sequential calls each, warm cache, localhost)

| Endpoint | p50 | p95 | p99 | mean | max |
|---|---:|---:|---:|---:|---:|
| `GET /api/alerts?limit=50` | 10.8 ms | **13.1 ms** | 17.4 ms | 11.4 ms | 66.9 ms |
| `GET /api/alerts/{max-evidence-id}` (13 reasons + graph + timeline + thresholds) | 2.6 ms | **2.8 ms** | 3.7 ms | 2.6 ms | 3.8 ms |

## Memory (single worker)

| Moment | API RSS |
|---|---:|
| idle / boot | **201 MB** |
| after 400 probe calls incl. 200×max-evidence | **201 MB** (flat — no leak trend) |

Free-tier budget: 512 MB. **Headroom: 311 MB** — comfortably hosts Postgres-free
api; with all-in-compose the whole stack (db ~120 MB + api 201 MB + nginx ~5 MB)
stays under 350 MB.

## Decisions record (measure-driven)

- `--workers 2` **rejected** (P2): doubles Python RSS (~400 MB), exposes no
  benefit at this traffic — free-tier compose passes `--workers 1`.
- Chunked/mapped loading already exists (pipeline builds frames, not giant
  ORM lists) — no fix needed today.
- Access logs: left ON in dev; production compose sets `--no-access-log` via
  env-only toggle if memory bands tighten later (none needed at 201 MB).
- Evaluation cache is per-(process, run_id) — keyed, never global (P3): a new
  analysis run never serves a stale verdict.

Reproduce: `.venv/bin/python scripts/perf_probe.py http://127.0.0.1:8000`
(with stack up) → prints exactly the table rows above.
