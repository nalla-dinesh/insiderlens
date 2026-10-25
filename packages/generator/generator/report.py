"""DATA_REPORT.md — human-readable proof of what was generated and why it is safe
to build a detection engine on top of it. Rendered after every successful build.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from generator.config import GeneratorConfig
from generator.quality import QualityReport


def render(cfg: GeneratorConfig, frames: dict[str, pd.DataFrame],
           quality: QualityReport, proofs: list[str],
           tx_counts: dict[str, int], act_counts: dict[str, int]) -> str:
    gt = frames["ground_truth"]
    susp = gt[gt["is_suspicious"]].groupby("scenario_id")["entity_ids"].count()
    traps = gt[~gt["is_suspicious"]].groupby("scenario_id")["entity_ids"].count()

    lines = [
        "# InsiderLens Synthetic Bank — DATA REPORT",
        "",
        f"- Generated (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Seed: `{cfg.seed}` (PCG64) — rebuilds are byte-identical",
        (f"- Window: {cfg.days} days starting {cfg.start_date.isoformat()} "
         f"(covers two month-start salary pulses)"),
        "",
        "## 1. Volumes",
        "",
        "| Frame | Rows | Envelope |",
        "|---|---:|---|",
    ]
    bounds = {
        "customers": f"== {cfg.volumes.customers_total}",
        "accounts": f"== {cfg.volumes.accounts_total}",
        "employees": f"== {cfg.volumes.employees_total}",
        "roles": "== 4",
        "transactions": f"[{cfg.volumes.txn_min:,}, {cfg.volumes.txn_max:,}]",
        "activity_log": f"[{cfg.volumes.activity_min:,}, {cfg.volumes.activity_max:,}]",
    }
    for name in ["roles", "employees", "customers", "accounts", "transactions",
                 "activity_log", "ground_truth"]:
        lines.append(f"| {name}.csv | {len(frames[name]):,} | {bounds.get(name, '—')} |")
    lines += [
        "",
        "Baseline mix: " + ", ".join(f"{k} {v:,}" for k, v in tx_counts.items())
        + " | activity: " + ", ".join(f"{k} {v:,}" for k, v in act_counts.items()),
        "",
        "## 2. Planted suspicious scenarios (ground truth)",
        "",
        "| Scenario | GT rows | What was planted (real ids + metrics) |",
        "|---|---:|---|",
    ]
    proof_by_scen: dict[str, list[str]] = {}
    for line in proofs:
        if len(line) >= 2 and line[:2] in {f"S{i}" for i in range(1, 8)}:
            proof_by_scen.setdefault(line[:2], []).append(line)
    for sid in sorted(proof_by_scen):
        lines.append(f"| {sid} | {int(susp.get(sid, 0))} | "
                     + "<br>".join(proof_by_scen[sid]) + " |")
    lines += [
        "",
        "## 3. Legitimate traps (engine must NOT flag)",
        "",
        "| Trap | GT rows | Rationale |",
        "|---|---:|---|",
    ]
    proof_by_trap = {k: [p for p in proofs if p.startswith(k)] for k in
                     ["L1", "L2", "L3", "L4", "L5"]}
    for tid in sorted(proof_by_trap):
        lines.append(f"| {tid} | {int(traps.get(tid, 0))} | "
                     + "<br>".join(proof_by_trap[tid]) + " |")
    lines += [
        "",
        "## 4. Quality gate",
        "",
        (f"- Scenario assertions: **{sum(1 for _, ok, _ in quality.assertions if ok)}"
         f"/{len(quality.assertions)} passed** (build fails otherwise)"),
        (f"- Global integrity checks: **{sum(1 for _, ok, _ in quality.global_checks if ok)}"
         f"/{len(quality.global_checks)} passed**"),
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok, _ in quality.assertions + quality.global_checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    lines += [
        "",
        "## 5. Scenario-vs-baseline overlap policy",
        "",
        ("Scenario and NPC accounts are **reserved**: baseline payroll/recurring/merchant/P2P "
         "flows and employee view-target sampling never touch them. Consequences:"),
        "",
        ("1. Planted patterns are the ONLY activity on those accounts — scoring deltas are "
         "attributable with zero noise."),
        ("2. NPC pool consumption is sequential (persons and businesses are never reused "
         "across scenarios within one build)."),
        ("3. Baseline salary payments DO hit the same recipient accounts used by L1/L5 "
         "traps — deliberately: the traps must survive adjacent realistic traffic."),
        "",
        "## 6. Blindness guarantee",
        "",
        ("`ground_truth.csv` is the only file knowing scenario membership; the operational "
         "frames carry no `scenario_id` / `is_suspicious` vocabulary (enforced by the gate "
         "and by tests). The API may read GT **only** inside EvaluationService."),
        "",
        "## 7. Determinism",
        "",
        ("`python -m generator verify` rebuilds the whole dataset to a temp directory and "
         "byte-compares every CSV against `meta.json` checksums (written at build time). "
         "See `tests/test_determinism.py` for the double-build byte-identity proof."),
        "",
    ]
    return "\n".join(lines)
