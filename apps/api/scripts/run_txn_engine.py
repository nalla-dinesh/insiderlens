"""Dev CLI: run the Phase-03 engine over the ingested DB and print per-rule hits.

    python scripts/run_txn_engine.py [--qa]

--qa  prints the (dev-only) overlap check against ground truth: planted patterns
MUST appear, legitimate traps (L1-L5) must NEVER appear. The engine itself stays
blind — this peek lives only in the dev harness.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.db.session import build_engine, build_session_factory
from app.engine.runner import run_transaction_rules
from app.services.rules_config import get_rules_config


def _print_hits(result) -> None:
    s = result.stats
    print(
        f"\ngraph: {s.nodes} nodes, {s.edges_total} legs ({s.edges_structural} pairs), build {s.build_ms} ms"
    )
    print(f"{'rule':<4} {'hits':>5} {'ms':>7}")
    for rid in ["T1", "T2", "T3", "T4", "T5", "T6"]:
        print(f"{rid:<4} {s.rule_hits.get(rid, 0):>5} {s.rule_ms.get(rid, 0):>7}")
    print(f"total hits: {len(result.hits)}, errors: {len(s.errors)}")
    for h in result.hits:
        print(f"  [{h.rule_id}] (+{h.base_points}) entities={h.entity_ids} :: {h.summary}")
    for err in s.errors:
        print(f"  !! {err}")


async def _qa(result, factory) -> None:
    # DEV-ONLY QA PEEK — the engine never imports ground_truth; this harness does.
    from sqlalchemy import select

    from app.models.ground_truth import GroundTruth

    async with factory() as s:
        rows = (await s.execute(select(GroundTruth))).scalars().all()

    susp, traps = {}, {}
    for r in rows:
        target = susp if r.is_suspicious else traps
        target.setdefault(r.scenario_id, set())
        target[r.scenario_id].update(int(i) for i in r.entity_ids)

    hit_entities = {e for h in result.hits for e in h.entity_ids}
    print("\n--- QA vs ground truth (dev-only peek) ---")
    all_ok = True
    for sid in sorted(susp):
        ids = susp[sid]
        found = bool(ids & hit_entities)
        mark = "HIT " if found else "MISS"
        if not found:
            all_ok = False
        print(f"  {sid}: {mark} (entities {sorted(ids)})")
    for sid in sorted(traps):
        leaked = traps[sid] & hit_entities
        mark = "CLEAN" if not leaked else f"LEAKED {sorted(leaked)}"
        if leaked:
            all_ok = False
        print(f"  {sid}: {mark} (entities {sorted(traps[sid])})")
    print(f"QA result: {'PASS' if all_ok else 'FAIL'}")


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    cfg = get_rules_config(str(settings.rules_config))
    engine = build_engine(settings.database_url)
    try:
        factory = build_session_factory(engine)
        async with factory() as session:
            import time

            t0 = time.perf_counter()
            result = await run_transaction_rules(session, cfg)
            total_ms = int((time.perf_counter() - t0) * 1000)
        _print_hits(result)
        print(f"total engine time: {total_ms} ms")
        if args.qa:
            await _qa(result, factory)
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
