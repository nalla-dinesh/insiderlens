# Phase 04 — Insider Rules (E1–E5), Fusion (F1–F3), Explainable Scoring

Status: ✅ complete. **141 tests pass** (engine + API suites), `ruff check` clean,
`ruff format --check` clean. Sandbox Postgres 47k-txn seeded bundle.

## New modules (all deliverables in place)

| File | Role |
|---|---|
| `app/engine/rules_emp.py` | E1 off-hours (IST re-derived), E2 RBAC, E3 dual-baseline spike, E4 config change, E5 canonical-window burst |
| `app/engine/fusion.py` | F1 action→pattern-START (72h), F2 alert suppression, F3 cross-branch rogue approver — triple-dedupe law |
| `app/engine/merger.py` | union-find (shared entity AND overlapping windows), 6-rule cap → overflow documented with zero points, 20-entity cap → split at widest temporal gap |
| `app/engine/scoring.py` | IRON LAW: `score = Σ reason.pts` (score is *derived* from reasons, never computed separately) |
| `app/services/evidence.py` | one code path → graph + timeline + thresholds + records for stored evidence AND `/api/timeline` |
| `app/services/pipeline.py` | runs row always closed (COMPLETED/FAILED), alert-vs-signal persistence policy |
| `app/routers/analysis.py`, `app/routers/alerts.py` | POST run, runs list, alerts list (band/status/rule + pagination), detail, PATCH status, timeline |
| `scripts/run_full_pipeline.py` | dev CLI: full run + band histogram + full S5-alert JSON + `--qa` trap peek |

## Live calibration (seeded bundle, latest completed run)

- **Band histogram: LOW 23 · MEDIUM 98 · HIGH 1 · CRITICAL 1** — every band non-empty ✓
- Per-rule hits: T-rules from Phase 03 unchanged; E-hits ~100 solo blips correctly dropped to
  **signals** (327 in run 30), never opening analyst-queue alerts.
- **S5 showcase: alert CRITICAL, score 150 ∈ [130,170], rule_set = {T1, E1, E2, E4, F1, F3},
  entities {1017, 200071, 200072, 200073}.** Full reason chain:
  `[T1] 3-hop ₹1,728,960 in 2.0d, 92% retained (+40)` · `[F1] KYC_EDIT → T1 started 34.5h later (+25)` ·
  `[E2] LIMIT_INCREASE outside OFFICER perms (+20)` · `[E4] 2 config changes (+15)` ·
  `[E1] night window 22:00–06:00 IST (+10)` · `[F3] Nagpur-East != Mumbai-Andheri (+10)` ·
  `amount>₹5L (+10)` · `cross_branch (+10)` · `repeat_pattern (+10 on re-runs — recidivism glows by design)`.
- **T5 dormant-reactivation: NEVER on the ACTIVE S5 ring** (property test).
- **Traps: L1–L5 CLEAN** (QA peek, dev-only script; engine never reads ground_truth).
- No alert with >20 entities (cardinality query: NONE).
- Iron law on 3 samples: 150/70/60 — score == Σpts exactly; property test covers ALL alerts.

## Laws reaffirmed

- Every score component is a reason with `pts` and a sentence that carries the numbers.
- `off_hours` / `role_violation` CSV flags are NEVER trusted (tests hand them wrong values on purpose).
- 72h fusion window is ACTION→PATTERN-START (P2), tested at 73h and reversed order.
- Zero magic numbers: every gate in evidence points at `rules.yaml`.
- Seeded-DB tests skip loudly when Postgres is unreachable — never fake GREEN.
