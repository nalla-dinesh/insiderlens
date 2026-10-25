# InsiderLens — Phase 07 (evaluation harness & threshold tuning) notes

Phase 07 makes the system PROVE itself: scenario-level precision/recall/F1/FPR
against ground truth, honestly computed, journal-tuned, and the engine stays
*provably blind* to truth the whole time.

## What was built

### 1. Evaluation service (the only truth reader, besides ingestion)
`app/services/evaluation.py`:
- Scenario-level law (spec §2): for each s∈S1..S7 → TP iff ≥1 alert of the run
  overlaps ≥1 tagged entity; traps l∈L1..L5 → FP iff overlapped, else TN.
- **One verdict per `scenario_id`** — GT stores 16 rows for S3; they collapse
  (entity universe = row union). The metric universe is exactly 7+5, never 32+8.
- Overlap in **SQL** (`alerts.entity_ids && gt.entity_ids` via `ColumnElement`
  `overlap` — P1: never hydrate alert rows into collections).
- **Unverified alerts** (no overlap with ANY tagged entity) reported separately
  — NEVER inflating FP (P2). Baseline: 103 unverified vs 20 on-susp vs 0 on-trap.
- Every ratio keeps raw counts (`TP 7 · FP 0 · FN 0 · TN 5`) — P5.
- Cache per (process, run_id) — `evaluate_cached()`, keyed invalidation (P3).

### 2. API
| Method | Path | What |
|---|---|---|
| GET | `/api/evaluation/{run_id}` | full EvaluationReport JSON (counts, P/R/F1/FPR, target gates, 12 scenario rows with notes) |
| GET | `/api/evaluation/compare?run_a&run_b` | side-by-side metrics + deltas; same pair → 422 `same_run_compare`; unknown run → 404 `run_not_found` |

### 3. Architecture guard test (spec §3 — AST, not grep)
`tests/test_guard_no_truth_in_engine.py`: walks the real import tree of every
file under `app/engine/`; any `ground_truth*`, `evaluation*` import fails the
test. The engine cannot see the answer sheet.

### 4. `/evaluation` page (sidebar un-gated)
- Run dropdown (any COMPLETED run) + **⟳ Recompute** (fires a real analysis
  run, then evaluates it).
- 4 metric cards (green when goal met, red otherwise; caption shows the goal) +
  Raw-counts card + 2×2 confusion matrix with %-labels.
- **Scenario table**: S1–S7 first (orange SUSPICIOUS chips), then L1–L5 (shaded
  TRAP rows) with HIT/silence verdict, clickable alert ids → alert detail, and
  the evidence note = the alert's **verbatim top reason** (never paraphrased).
- **Compare panel**: two-run picker → `/api/evaluation/compare` rendered with
  ▲/▼ deltas (↑ on FPR is red — direction-aware).

### 5. Tuning journal — `docs/TUNING.md` (spec §5)
Runner: `scripts/tuning_iterations.py` — one knitted knob per iteration
(edit applied to a parsed-YAML clone, unique path per iteration, real
`pipeline.run_analysis` + `EvaluationService` — same production code path).
12 rows incl. 3 deliberate degradations; machine-readable twin at
`docs/TUNING_iterations.json` (per-rule hit counts, signal drops, per-run
rules sha256).

Honesty highlights (from real numbers):
- iter09: relaxing T1 retention 0.70→0.50 *alone* changes nothing — the
  ₹40k leg floor + shape guards do the real pruning.
- iter10: removing legitimacy guards tripled T2 hits (1→3) but traps still
  dodged — the extras were unverified merchant consolidations (+2 alerts).
- iter11: **guards removed + T1 window 14d → L2 triangle TRAP FIRES**:
  FP=1/5, FPR 0.20, precision 0.875, ❌ targets failed — the demo's proof
  that legitimacy guards are load-bearing.
- **Frozen v1.0 = blueprint defaults** (no iteration beat them with margin);
  `infra/config/rules.yaml` carries the `# frozen v1.0` header.

## Verification (sandbox)

| Gate | Result |
|---|---|
| `pytest -q` | **154 passed** (incl. 6 evaluation API tests + AST guard) |
| `ruff check` + `ruff format` | clean |
| `npm run lint` + `npm run build` | 0 errors, built 3.56s |
| Live `curl /api/evaluation/19` | **P=1.0 R=1.0 F1=1.0 FPR=0.0 · TP7/FP0/FN0/TN5 · targets.passed=true** — FULL JSON in the phase response |
| Compare endpoint | baseline(run 1) vs frozen(run 19): all deltas 0.0 ✓ |
| Browser audit | `scripts/audit_web.py` → **43/43 PASS** (4 new /evaluation checks incl. UI == API recall) |
| Screenshot | `phase7_shots/evaluation.png` |

Laptop quick-start unchanged — after the zip drop: restart API (rules header
only changes sha), `.-Evaluation` sidebar now live; **Recompute** button does
the whole proof in one click.
