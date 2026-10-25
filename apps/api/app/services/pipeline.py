"""Run pipeline — the Phase-04 end-to-end: graph -> T -> E -> F -> merge ->
score -> persist alerts -> run bookkeeping.

Guarantees:
- a Run row is ALWAYS closed (COMPLETED or FAILED) — an analyst can audit every
  execution from the DB alone;
- only the alert-vs-signal policy (scoring.should_persist) decides what lands in
  the analyst queue — solo low-signal blips drop to 'signals' (run stats only);
- every persisted alert is schema-complete BEFORE commit (reasons[] + evidence),
  and the DB's CHECK constraints are the second line of defense.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.engine.graph import GraphBuilder
from app.engine.merger import merge_hits
from app.engine.runner import run_all
from app.engine.scoring import score_group, should_persist
from app.models.alert import Alert
from app.models.run import Run
from app.services.evidence import build_evidence
from app.services.rules_config import RulesConfig

logger = get_logger(__name__)


def _entity_type(entity_ids: list[int], acc_ids: set[int], emp_ids: set[int]) -> str:
    has_acc = any(e in acc_ids for e in entity_ids)
    has_emp = any(e in emp_ids for e in entity_ids)
    if has_acc and has_emp:
        return "MIXED"
    if has_acc:
        return "ACCOUNT"
    if has_emp:
        return "EMPLOYEE"
    return "CUSTOMER"


async def run_analysis(session: AsyncSession, cfg: RulesConfig, rules_path: str) -> dict:
    started = datetime.now(UTC)
    run = Run(
        started_at=started,
        status="RUNNING",
        config={
            "rules_config": rules_path,
            "rules_sha256": hashlib.sha256(Path(rules_path).read_bytes()).hexdigest()[:16],
        },
    )
    session.add(run)
    await session.flush()  # run_id allocated, row visible for FK
    run_id = int(run.run_id)
    t0 = time.perf_counter()
    try:
        g, frames, build_ms = await GraphBuilder(session).load()
        result, t_hits, e_hits = run_all(g, frames, cfg, build_ms=build_ms)

        # prior-run entities (repeat_pattern modifier)
        prior_rows = (
            (await session.execute(select(Alert.entity_ids).where(Alert.run_id < run_id))).scalars().all()
        )
        prior_entities = {int(e) for row in prior_rows for e in row}

        groups = merge_hits(result.hits, cfg)
        scored = [score_group(grp, cfg, frames, prior_entities) for grp in groups]
        persistable = [s for s in scored if should_persist(s, cfg)]
        signals_dropped = len(scored) - len(persistable)

        acc_ids = set(frames.accounts["acc_id"].astype(int).tolist())
        emp_ids = set(frames.employees["emp_id"].astype(int).tolist())
        for s in persistable:
            acc_entities = sorted(e for e in s.entity_ids if e in acc_ids)
            evidence = await build_evidence(session, s.group.hits, acc_entities)
            if s.group.overflow_rules:
                evidence["overflow_rules"] = s.group.overflow_rules
                evidence["overflow_note"] = (
                    f"Merged group exceeded {cfg.fusion.max_rules_per_alert} rules; "
                    "these rules contributed context but no points."
                )
            session.add(
                Alert(
                    run_id=run_id,
                    rule_set=s.rule_set,
                    entity_type=_entity_type(s.entity_ids, acc_ids, emp_ids),
                    entity_ids=s.entity_ids,
                    score=s.score,
                    band=s.band,
                    reasons=s.reasons,
                    evidence=evidence,
                    status="OPEN",
                )
            )

        run.status = "FAILED" if result.stats.errors else "COMPLETED"
        run.finished_at = datetime.now(UTC)
        run.txn_count = len(frames.tx)
        run.alert_count = len(persistable)
        run.config["stats"] = {
            "per_rule_hits": result.stats.rule_hits,
            "rule_ms": result.stats.rule_ms,
            "errors": result.stats.errors,
        }
        await session.commit()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        bands = Counter(s.band for s in persistable)
        logger.info(
            "pipeline_done",
            run_id=run_id,
            alerts=len(persistable),
            signals_dropped=signals_dropped,
            duration_ms=duration_ms,
            status=run.status,
        )
        return {
            "run_id": run_id,
            "status": run.status,
            "alerts_by_band": {b: bands.get(b, 0) for b in ("LOW", "MEDIUM", "HIGH", "CRITICAL")},
            "duration_ms": duration_ms,
            "per_rule_hits": result.stats.rule_hits,
            "signals_dropped": signals_dropped,
            "errors": result.stats.errors,
        }
    except Exception:
        await session.rollback()
        # run-row auditability: mark FAILED in a fresh tiny transaction
        async with session.begin():
            row = await session.get(Run, run_id)
            if row is not None:
                row.status = "FAILED"
                row.finished_at = datetime.now(UTC)
        await session.commit()
        logger.exception("pipeline_failed", run_id=run_id)
        raise
