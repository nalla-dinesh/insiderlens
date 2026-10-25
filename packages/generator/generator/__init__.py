"""InsiderLens synthetic bank generator (Phase 01).

Design laws (see docs/CONVENTIONS.md):
- Determinism: one seeded numpy Generator (PCG64) threads EVERYTHING.
- Blindness: ground truth lives ONLY in ground_truth.csv (+ meta) — never in business CSVs.
- Self-proof: every scenario injector registers assertions that build.py runs over
  the final frames. A broken scenario HARD-FAILS the build instead of shipping silently.
"""
