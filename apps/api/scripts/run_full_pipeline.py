"""Dev CLI: full detection pipeline on the ingested DB.

    python scripts/run_full_pipeline.py [--qa]

Prints the band histogram + per-rule hits + run duration, then the FULL JSON of
the alert containing S5's employee (1017). --qa adds the dev-only ground-truth
peek (traps must never leak into persisted alerts).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import select

from app.config import get_settings
from app.db.session import build_engine, build_session_factory
from app.models.alert import Alert
from app.services.pipeline import run_analysis
from app.services.rules_config import get_rules_config

EMP_S5 = 1017  # scenario constants live ONLY in this dev harness, engine stays blind


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
            report = await run_analysis(session, cfg, str(settings.rules_config))
        print("\n=== RUN REPORT ===")
        print(json.dumps(report, indent=2, default=str))

        async with factory() as session:
            rows = (await session.execute(select(Alert).order_by(Alert.score.desc()))).scalars().all()
            s5 = [a for a in rows if EMP_S5 in list(a.entity_ids)]
            if s5:
                a = s5[0]
                print("\n=== S5-EMPLOYEE ALERT (full JSON) ===")
                print(
                    json.dumps(
                        {
                            "alert_id": a.alert_id,
                            "band": a.band,
                            "score": a.score,
                            "rule_set": a.rule_set,
                            "entity_ids": a.entity_ids,
                            "reasons": a.reasons,
                            "evidence_keys": sorted(a.evidence.keys()),
                            "evidence_records": a.evidence.get("records"),
                            "evidence_thresholds": a.evidence.get("thresholds"),
                            "timeline_events": len(a.evidence.get("timeline", [])),
                            "graph_nodes": len(a.evidence.get("graph", {}).get("nodes", [])),
                            "graph_edges": len(a.evidence.get("graph", {}).get("edges", [])),
                        },
                        indent=2,
                        default=str,
                    )
                )
            else:
                print("\nNO alert contains employee 1017 — S5 showcase BROKEN")

            if args.qa:
                from app.models.ground_truth import GroundTruth

                traps = (
                    (await session.execute(select(GroundTruth).where(GroundTruth.is_suspicious.is_(False))))
                    .scalars()
                    .all()
                )
                print("\n--- QA: trap entities in persisted alerts (dev peek) ---")
                alert_entities = {int(e) for a in rows for e in a.entity_ids}
                ok = True
                for t in traps:
                    leaked = sorted(set(int(i) for i in t.entity_ids) & alert_entities)
                    if leaked:
                        ok = False
                    print(
                        f"  {t.scenario_id} {t.entity_type} {t.entity_ids}: "
                        f"{'LEAKED ' + str(leaked) if leaked else 'CLEAN'}"
                    )
                print(f"QA result: {'PASS' if ok else 'FAIL'}")
                print(f"\ntotal persisted alerts: {len(rows)}")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
