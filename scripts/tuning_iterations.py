"""Phase-07 tuning harness (scripts/) — runs ONE-KNOB-AT-A-TIME experiments
from spec §5 against the same DB, each iteration = own YAML file (fresh parse,
no lru_cache collision) + own analysis run + own evaluation.

Usage (from apps/api):
    ../../.venv/bin/python ../../scripts/tuning_iterations.py

Writes: docs/TUNING_iterations.json (machine-readable journal evidence).
Emits: one table row per iteration to stdout — pasted into docs/TUNING.md.

Fairness rules:
- Exactly ONE rule knob differs from baseline per iteration (spec §5).
- The deliberate degradation row REMOVES a legitimacy guard (T1 retention 0.50
  = purpose guards stay but cycles need only keep half the seed + T4 with 3
  occurrences) so the FPR climb is attributable, not murky.
- scenarios/ground truth/inputs are NEVER touched (spec: forbidden).
"""

import asyncio
import json
import time
from pathlib import Path

from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.services.evaluation import EvaluationService
from app.services.ingestion import IngestionService
from app.services.pipeline import run_analysis
from app.services.rules_config import get_rules_config

DB_URL = "postgresql+asyncpg://insider:insider@127.0.0.1:5432/insiderlens"
ROOT = Path(__file__).resolve().parents[1]
BASE_YAML = ROOT / "infra" / "config" / "rules.yaml"
TMPDIR = ROOT / "infra" / "config" / ".tuning_tmp"

# (label, [(keypath, newvalue), ...]) — dotted path edits on the parsed YAML.
# Safe even with inline comments (no regex on YAML source text).
ITERATIONS: list[tuple[str, list[tuple[tuple[str, ...], object]]]] = [
    ("baseline (blueprint defaults)", []),
    ("t1_retention 0.70->0.75", [(("thresholds", "t1_circular", "min_retention"), 0.75)]),
    ("t1_retention 0.70->0.80", [(("thresholds", "t1_circular", "min_retention"), 0.80)]),
    ("t1_window 10d->7d", [(("thresholds", "t1_circular", "window_days"), 7)]),
    ("t1_window 10d->14d", [(("thresholds", "t1_circular", "window_days"), 14)]),
    ("t4_occurrences 5->4", [(("thresholds", "t4_passthrough", "min_occurrences"), 4)]),
    ("t4_occurrences 5->3", [(("thresholds", "t4_passthrough", "min_occurrences"), 3)]),
    ("t4_forward_ratio 0.80->0.85", [(("thresholds", "t4_passthrough", "forward_ratio"), 0.85)]),
    ("t2_window 7d->5d", [(("thresholds", "t2_structuring", "window_days"), 5)]),
    (
        "DEGRADATION-A (t1_retention 0.5 + t4_occurrences 3)",
        [
            (("thresholds", "t1_circular", "min_retention"), 0.50),
            (("thresholds", "t4_passthrough", "min_occurrences"), 3),
        ],
    ),
    (
        "DEGRADATION-B (legitimacy guards REMOVED: exempt_purposes=[])",
        [(("legitimacy_guards", "exempt_purposes"), [])],
    ),
    (
        "DEGRADATION-C (guards REMOVED + t1_window 14d)",
        [
            (("legitimacy_guards", "exempt_purposes"), []),
            (("thresholds", "t1_circular", "window_days"), 14),
        ],
    ),
]


def render(src: str, edits: list[tuple[tuple[str, ...], object]]) -> str:
    """Apply dotted-path edits to the parsed YAML; tmp files need no comments."""
    import yaml  # already a runtime dep (rules_config)

    doc = yaml.safe_load(src)
    for path, value in edits:
        node = doc
        for key in path[:-1]:
            if key not in node:
                msg = f"yaml path missing: {'.'.join(path)}"
                raise RuntimeError(msg)
            node = node[key]
        old = node.get(path[-1], "<missing>")
        node[path[-1]] = value
        print(f"    edit {'.'.join(path)}: {old} -> {value}")
    return yaml.safe_dump(doc, sort_keys=False)


async def main() -> None:
    TMPDIR.mkdir(exist_ok=True)
    eng = build_engine(DB_URL)
    sf = build_session_factory(eng)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ingest once (idempotent service: second call skips every row via PK dedup)
    rep = await IngestionService(sf, ROOT / "data" / "generated").run()
    print(f"INGEST rows={rep.total_inserted} skipped={sum(t.skipped for t in rep.tables.values())}")

    base_src = BASE_YAML.read_text(encoding="utf-8")
    journal: list[dict] = []
    for idx, (label, subs) in enumerate(ITERATIONS):
        yaml_path = TMPDIR / f"rules_iter{idx:02d}.yaml"
        yaml_path.write_text(render(base_src, subs), encoding="utf-8")
        t0 = time.perf_counter()
        cfg = get_rules_config(str(yaml_path))
        async with sf() as s:
            rep = await run_analysis(s, cfg, str(yaml_path))
            await s.commit()
            ev = await EvaluationService(s).evaluate(rep["run_id"])
        ms = int((time.perf_counter() - t0) * 1000)
        c = ev.counts
        row = {
            "iteration": idx,
            "per_rule_hits": rep["per_rule_hits"],
            "signals_dropped": rep["signals_dropped"],
            "label": label,
            "run_id": rep["run_id"],
            "alerts": ev.alert_count,
            "tp": c.tp,
            "fp": c.fp,
            "fn": c.fn,
            "tn": c.tn,
            "precision": ev.precision,
            "recall": ev.recall,
            "f1": ev.f1,
            "fpr": ev.fpr,
            "targets_passed": ev.targets.passed,
            "unverified_alerts": ev.alerts_unverified,
            "duration_ms": ms,
        }
        journal.append(row)
        flag = "PASS" if ev.targets.passed else "FAIL"
        print(
            f"iter{idx:02d} [{flag}] {label:44s} alerts={ev.alert_count:>3} "
            f"TP={c.tp}/7 FP={c.fp}/5 P={ev.precision:<5} R={ev.recall:<5} F1={ev.f1:<5} FPR={ev.fpr:<5} "
            f"unv={ev.alerts_unverified:>3} ({ms}ms)"
        )
        hits = rep["per_rule_hits"]
        print(
            f"    hits T1={hits.get('T1')} T2={hits.get('T2')} T3={hits.get('T3')} "
            f"T4={hits.get('T4')} T6={hits.get('T6')} dropped={rep['signals_dropped']}"
        )

    (ROOT / "docs" / "TUNING_iterations.json").write_text(json.dumps(journal, indent=2))
    print("\nwrote docs/TUNING_iterations.json")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
