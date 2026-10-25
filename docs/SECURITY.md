# SECURITY.md — Phase 08 security pass (findings + fixes + outputs)

All controls have **code paths + tests** — nothing here is policy-only.

## 1. CORS — production refuses the wildcard

`ENV=production` + `CORS_ORIGINS=*` (or empty) → the API **refuses to boot**
(RuntimeError naming the config), tested in
`tests/test_security.py::test_cors_wildcard_refused_in_production`
(and `_when_empty_` variant). Named origins boot fine; docs are dark in prod
(`docs_url=None`).

## 2. Production request gates

- `POST /api/ingest` → **403 `forbidden_in_production`** when `ENV=production`
  (test: `test_ingest_forbidden_in_production`) — ingestion is a dev/demo tool.
- `POST /api/analysis/run` → **fixed-window 5/min per client** in production
  (429 `rate_limited`) — in-memory limiter, suited to single-instance free tier.
  Tested on both 5-allow/2-block and on GET endpoints being untouched.

## 3. HTTP security headers (every API response)

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
```
`SecurityHeadersMiddleware` at the ASGI ring; nginx sets the same headers on the
web container (belt & suspenders). Test: `test_security_headers_on_every_response`.

## 4. Secret scan — gitleaks v8.24.3

```
$ gitleaks detect --source . --no-git
scanned ~6417828 bytes (6.42 MB) in 390ms
no leaks found
```
Two initial findings were audited as **false positives** (rule-name string
literals inside evidence reason dicts — `"key": "t1_circular.min_retention"` is
a THRESHOLD REFERENCE, not a credential). Fingerprints are pinned in
`.gitleaksignore` with a rationale comment, so future scans stay noiseless.

Secrets hygiene: real `.env*` files excluded from zips/git (grep-verified 0
hits); only `.env.example` templates ship. `.dockerignore` also blocks them.

## 5. Dependency audits

| Tool | Result |
|---|---|
| `pip-audit` over the runtime env | **No known vulnerabilities found** (insiderlens-api = local app, skipped by design) |
| `npm audit --omit=dev` (before) | 2 moderate — react-router ≤7.17 open-redirect (CVE-2025-68470-bypass, CWE-601) |
| `npm audit --omit=dev` (after) | **0 vulnerabilities** — upgraded `react-router-dom` ^6.28 → ^7.18.4 (TS+build reverified; router API unchanged for our usage) |

## 6. Input safety spot-check (static)

- **Zero raw f-string SQL**: AST scan of `app/` — any
  `session.execute(f"...")` on a JoinedStr would fail
  `test_zero_fstring_sql_spot_check`; all SQLAlchemy calls go through typed
  expressions / `text()` with bound params.
- Path/query ids are typed `int` — Pydantic coercion; a non-int hits the 422
  model, never the SQL layer.
- Case-export ZIPs: built purely in-memory (`BytesIO`); the only remote input
  is the optional PNG dataURL (decoded then size-guarded client-side).
- Engine blindness is a hard law: AST guard test — nothing under `app/engine/`
  may import ground-truth or evaluation code (Phase 07, still green).

## 7. Non-goals / honest boundaries

- No authN/AuthZ yet — single-tenant internal analyst tool for the demo; the
  threat model starts Phase 09 (deploy behind a private network/auth proxy).
- Rate limiter is per-process (in-memory) — multi-instance prod would back it
  with Redis; documented.
- Ingestion remains dev-profile only; production feeds flow via the connectors
  pipeline (future phase).
