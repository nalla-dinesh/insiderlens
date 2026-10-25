# TUNING.md — Phase 07 tuning journal (numbers, not vibes)

Environment: sandbox, PostgreSQL (landlord ≠ GPU-free complaint), seed-42 bundle
(46,978 txns / 9,124 activity rows), 15 analysis runs, one-per-iteration,
*exactly one knob changed per iteration* (spec §5). Ground truth, scenarios,
and baseline data were NEVER modified (spec: forbidden — verified: every run
ingests the byte-identical bundle; sha-verified by the engine).

Metric definitions per spec §2 — scenario-level verdicts (7 suspicious + 5 legit
trap scenarios; ratio denominators are small → raw counts are always beside ratios).

Knob candidates measured (all legal per spec §5):
`T1 min_retention 0.70/0.75/0.80 · T1 window 7/10/14d · T4 occurrences 3/4/5 ·
T4 forward_ratio 0.80/0.85 · T2 window 5/7d` + 3 deliberate degradations.

## Iteration table (run × knob → metrics)

| iter | knob (vs baseline) | rules_sha256 | alerts | TP/7 | FP/5 | P | R | F1 | FPR | unv | verdict |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| iter00 | **baseline (blueprint defaults)** | a46262fa26 | 123 | 7 | 0 | **1.0000** | **1.0000** | **1.0000** | **0.0000** | 103 | ✅ targets pass |
| iter01 | T1 min_retention → 0.75 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter02 | T1 min_retention → 0.80 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter03 | T1 window_days → 7 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter04 | T1 window_days → 14 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter05 | T4 min_occurrences → 4 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter06 | T4 min_occurrences → 3 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter07 | T4 forward_ratio → 0.85 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter08 | T2 window_days → 5 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ no delta |
| iter09 | **DEGRADATION-A**: T1 retention 0.50 + T4 occ 3 | — | 123 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 103 | ✅ (surprising — see why below) |
| iter10 | **DEGRADATION-B**: legitimacy guards off (`exempt_purposes=[]`) | — | 125 | 7 | 0 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 105 | ✅ but +2 alerts on unverified entities |
| iter11 | **DEGRADATION-C**: guards off + T1 window 14d | — | 126 | 7 | **1** | **0.8750** | 1.0000 | 0.9333 | **0.2000** | 105 | ❌ **FPR climbs — honesty proof row** |

(rules_sha256 per run is stored in `runs.config.rules_sha256`; full row data in
`docs/TUNING_iterations.json` including per-rule hit counts and signal drops.)

## Interpretation (one line per row — honest, not flattering)

1. **iter01–02** (retention 0.75/0.80): all rings keep 85–97% retention, so the
   floor has a large *credence margin* — no hits change. Looseening to 0.50 (iter09)
   also does nothing by itself: the *seed-drain* shape, not the floor value, is
   what separates cycles from noise. Keep **0.70** (blueprint).
2. **iter03–04** (T1 window 7/14d): identical. With `min_leg_amount=₹40k`+
   exempt-leg pruning ON, random p2p never forms a ≥3-hop ≥40k cycle — **the
   window is not the working frontier; the guards are** (confirmed by iter11).
3. **iter05–06** (T4 occurrences 4/3): L4's trap is *by construction* 1
   occurrence, the churn corridor guard (route_share, fraction_std) keeps
   background noise out even at 3 occurrences → keep **5** for its legibility
   (fewer analyst-complexity, identical metrics).
4. **iter07** (T4 ratio 0.85): S4's forwards are 88–96% of inflow; the 80→85
   shift only narrows the safety band — **no benefit on this kill set**, keep
   0.80 (margin to L4's single 80%-forward is real).
5. **iter08** (T2 window 5d): S3's 17 deposits sit inside 6d — tight. 5d
   would work today but leaves ~zero arrival drift headroom. Keep **7d**.
6. **iter09 (DEGRADATION-A)**: surprising! Retention⇓+occurrences⇓ did **not**
   break anything alone — because T1 gates ALSO on `min_leg_amount≥₹40k`
   (prunes p2p 3-cycles) and T4 gates on discriminator guards (route_share,
   fraction_std). Single-number thresholds are *backed by shape guards*;
   it takes **removing legitimacy guards** to push the frontier.
7. **iter10 (DEGRADATION-B)**: guards off → input volume-math now sees
   SALARY/BONUS/PROPERTY... T2 hits *triple* (1→3) — but both extras land on
   **unverified** untagged entities (merchant consolidations), not the traps;
   precision unaffected, alert volume ↑2. The traps dodge via their OTHER
   design properties (L1 bulk hours, L2 spans).
8. **iter11 (HONESTY ROW)**: guards off + window 14d → L2's triangle cycles
   (spans >10d by design, ≥2 exempt legs) finally enter the T1 kill zone →
   **one trap fires** (FP=1/5, FPR 0.20), precision 0.875, targets FAIL.
   This is the demo's honesty proof: the legitimacy guards are load-bearing;
   remove them and the *same* thresholds step over the L2 trap by exactly
   the days the trap was built to dodge.

## Decision — frozen v1.0

No knob change **beats** the blueprint defaults on this evidence; several
equal them; iteration rows above show the defaults sit on a broad flat
optimum (defensible in an STR). Final config = blueprint defaults,
frozen as **rules.yaml v1.0** (see header comment in the file).

Final frozen-config metrics (spec §7 step 3, measured on the fresh v1.0 run):

| Metric | Value | Target | Verdict |
|---|---:|---:|:---:|
| Precision | **1.0000 (TP 7/7)** | ≥ 0.85 | ✅ |
| Recall | **1.0000 (7/7)** | ≥ 0.90 | ✅ |
| F1 | **1.0000** | — | ✅ |
| FPR | **0.0000 (0/5)** | ≤ 0.05 | ✅ |

Compare-view wiring: `GET /api/evaluation/compare?run_a=<iter00 run>&run_b=<frozen run>`
renders identical-to-baseline deltas (all 0.0) — the frozen config is the
blueprint; the tunings only *proved* that, with margins, on data.
