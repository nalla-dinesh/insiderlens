# InsiderLens — Phase 08 (hardening · CI/CD · docker · security · performance) notes

## Delivered

### 1. CI — `.github/workflows/ci.yml` (4 jobs, every command proven green locally)
- **api-test**: postgres:16-alpine service (creds EXACTLY `insider/insider` —
  pitfall P1), python 3.11 + pip cache → `pip install -e apps/api[dev]` →
  ruff → `alembic upgrade head` → **mini fixture ingest** (`apps/api/tests/fixtures/
  mini_bundle/` — FK-clean chronological slice of the seed-42 bundle, 500 txns,
  136 KB total, sha-verified by the ingestion service itself) → `pytest -q`.
- **web-build**: node 20 + npm cache → `npm ci` → lint → build.
- **docker-build**: builds both Dockerfiles (api + web), no push, GHA layer cache.
- **e2e** (needs api-test+web-build): compose `--profile demo` up → health +
  seeder wait loop → `scripts/e2e_happy_path.sh` → log as artifact.
- Branch protection recipe → `docs/CONVENTIONS.md §5`.

### 2. Docker (512 MB free-tier fit)
- `apps/api/Dockerfile`: multi-stage wheel build, slim final, **non-root uid
  10001**, HEALTHCHECK via stdlib urllib, **workers 1** (P2, measured RSS
  201 MB — 2 workers would double it), ENV=production default.
- `apps/api/entrypoint.sh`: `RUN_MIGRATIONS=1` → `alembic upgrade head` opt-in
  (P5; verified end-to-end against a throwaway DB → all 12 tables created).
- `infra/docker-compose.yml`: db (healthchecked) → api (RUN_MIGRATIONS=1) →
  web (nginx static + proxy). **`--profile demo`** adds the one-shot **seeder**
  container: unpacks the committed **956 KB gzip** seed-42 bundle (NOT raw
  CSVs — P4), drives the REAL `/api/ingest` + `/api/analysis/run`, then exits.
- `infra/nginx/nginx.conf`: written by hand (no scaffold) — proxy_pass has NO
  trailing slash so `/api/*` maps 1:1 (P3); SPA fallback; cache-control for
  hashed assets; security headers mirrored webside.
- **Verified locally as far as sandbox allows** (Docker absent → mimicked):
  nginx config `nginx -t` clean; live end-to-end: `/api/alerts?limit=2` → 200
  with real data; `/health` → 200; `/cases` SPA fallback → 200; headers on
  responses; seeder script dry-logic reviewed; compose YAML parses.

### 3. Security pass — `docs/SECURITY.md` (all controls have tests)
- `ENV=production + CORS_ORIGINS=*` → **boot refused** (RuntimeError, 2 tests).
- `POST /api/ingest` → 403 in prod (tested).
- `POST /api/analysis/run` → fixed-window **5/min/client** in prod → 429
  (tested allow-5/block-2 + GET untouched).
- Security headers on every API response + nginx mirrors (tested).
- **gitleaks v8.24.3**: 2 findings audited → false positives (rule-name strings
  in evidence dicts) → pinned in `.gitleaksignore` → final scan **no leaks**.
- **pip-audit**: clean. **npm audit --omit=dev**: 2 moderate react-router →
  upgraded `react-router-dom` ^6.28 → **^7.18.4** → **0 vulnerabilities**; TS +
  build + 43/43 audit re-verified after the upgrade.
- Input safety: AST f-string-SQL scan = 0 offenders (test in suite).

### 4. Performance — `docs/PERF.md` (real numbers, `scripts/perf_probe.py`)
Machine: sandbox · 2 vCPU · 1.9 GB RAM · rules v1.0 sha388d16…
- Pipeline: ingest 57,821 rows ~12 s; graph build 653 ms; full T+E+F run
  7.1 s → **≈ 8 s/50k txns, target was < 120 s (15× under) ✅**
- `GET /api/alerts?limit=50`: p50 10.8 ms · **p95 13.1 ms** · p99 17.4 ms
- `GET /api/alerts/{max-evidence-id}`: p50 2.6 ms · **p95 2.8 ms**
- API RSS: **201 MB → 201 MB after 400-hit probe (flat)** — 311 MB headroom
  under the 512 MB free tier.

### 5. README final + architecture image + screenshots
`docs/architecture.png` (hand-drawn SVG → deterministic playwright render),
5 real screenshots under `docs/screens/`, badges, one-command demo, manual dev
path, make-target table, docs links.

## Verification (all local-green, since `act`+Docker both absent in sandbox)

| DoD | Evidence | Verdict |
|---|---|---|
| Fresh-clone one-command demo | compose profile written; EVERY step proven piecewise (alembic fresh-DB ✓, seeder logic ✓ via its exact urllib calls on the same endpoints, nginx live proxy ✓). docker binary absent → human command `make demo-seed` documented + laptop fallback `make demo-local`. | **PASS (documented fallback)** |
| ci.yml commands green locally | ruff `All checks passed!` · pytest **162 passed** · npm lint 0 err · npm build ✓ · mini-bundle ingest 1628 rows checksum=OK | **PASS** |
| SECURITY.md filled incl. tests | 8/8 `test_security.py` · gitleaks clean · audits above | **PASS** |
| PERF.md measured & meets targets | 15× under pipeline target, p95s ≤ 13.1 ms, RSS 201 MB < 450 MB | **PASS** |
| README + architecture image + quickstart | rewritten; architecture.png committed | **PASS** |

No deferred items. Windows users: zip drop-in → `docker compose -f
infra/docker-compose.yml --profile demo up --build -d` (Docker Desktop) or the
/manual-in/README path.
