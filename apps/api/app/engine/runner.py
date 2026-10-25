"""Engine runner — graph build + rule loop with loud-failure isolation (P4).

    result = await run_transaction_rules(session, cfg)

NOTE: scoring/merging/persistence is Phase 04 — this phase returns RuleHit list
(+ stats) and writes NOTHING to the DB.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.engine import rules_txn
from app.engine.graph import BuildStats, EngineFrames, GraphBuilder
from app.engine.types import RuleHit
from app.services.rules_config import RulesConfig

logger = get_logger(__name__)


@dataclass
class EngineResult:
    hits: list[RuleHit]
    stats: BuildStats = field(default_factory=BuildStats)

    @property
    def hit_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for h in self.hits:
            out[h.rule_id] = out.get(h.rule_id, 0) + 1
        return out


RULES: list[tuple[str, str]] = [
    ("T1", "t1_circular"),
    ("T2", "t2_structuring"),
    ("T3", "t3_fanin"),
    ("T4", "t4_passthrough"),
    ("T5", "t5_dormant"),
    ("T6", "t6_profile"),
]

E_RULES: list[tuple[str, str]] = [
    ("E1", "e1_offhours"),
    ("E2", "e2_rbac"),
    ("E3", "e3_spike"),
    ("E4", "e4_highrisk"),
    ("E5", "e5_burst"),
]


def _run_named(
    module, rule_ids: list[tuple[str, str]], fn_args_builder, stats: BuildStats, hits: list[RuleHit]
) -> None:
    """Per-rule loud-isolation loop (P4: one rule's crash never kills the run)."""
    for rid, fname in rule_ids:
        t0 = time.perf_counter()
        try:
            fn = getattr(module, fname)
            found = fn(*fn_args_builder(rid))
            ms = int((time.perf_counter() - t0) * 1000)
            stats.rule_ms[rid] = ms
            stats.rule_hits[rid] = len(found)
            logger.info("rule_done", rule=rid, hits=len(found), ms=ms)
            hits.extend(found)
        except Exception as e:  # noqa: BLE001 - loud, isolated failure
            stats.rule_hits[rid] = stats.rule_hits.get(rid, 0)
            stats.errors.append(f"{rid}: {type(e).__name__}: {e}")
            logger.exception("rule_failed", rule=rid, error=str(e))


def run_rules(
    g: nx.DiGraph,
    frames: EngineFrames,
    cfg: RulesConfig,
    build_ms: int = 0,
    n_nodes: int = 0,
    n_edges: int = 0,
) -> EngineResult:
    stats = BuildStats(
        nodes=n_nodes or int(g.number_of_nodes()),
        edges_total=len(frames.tx),
        edges_structural=n_edges or int(g.number_of_edges()),
        build_ms=build_ms,
    )
    hits: list[RuleHit] = []
    _run_named(rules_txn, RULES, lambda rid: (g, frames, cfg) if rid == "T1" else (frames, cfg), stats, hits)
    return EngineResult(hits=hits, stats=stats)


async def run_transaction_rules(session: AsyncSession, cfg: RulesConfig) -> EngineResult:
    g, frames, build_ms = await GraphBuilder(session).load()
    return run_rules(
        g, frames, cfg, build_ms=build_ms, n_nodes=g.number_of_nodes(), n_edges=g.number_of_edges()
    )


def run_all(
    g: nx.DiGraph, frames: EngineFrames, cfg: RulesConfig, build_ms: int = 0
) -> tuple[EngineResult, list[RuleHit], list[RuleHit]]:
    """Phase-04 full rule pipeline: T1-T6, then E1-E5, then F1-F3 fusion on the
    SAME run's hits. Returns (result_with_all_hits, t_hits, e_hits)."""
    from app.engine import fusion, rules_emp

    stats = BuildStats(
        nodes=g.number_of_nodes(),
        edges_total=len(frames.tx),
        edges_structural=g.number_of_edges(),
        build_ms=build_ms,
    )
    t_hits: list[RuleHit] = []
    e_hits: list[RuleHit] = []
    _run_named(
        rules_txn, RULES, lambda rid: (g, frames, cfg) if rid == "T1" else (frames, cfg), stats, t_hits
    )
    _run_named(rules_emp, E_RULES, lambda rid: (frames, cfg), stats, e_hits)

    t0 = time.perf_counter()
    f_hits: list[RuleHit] = []
    try:
        f_hits = fusion.fusion_rules(t_hits, e_hits, frames, cfg)
        for fid in ("F1", "F2", "F3"):
            stats.rule_hits[fid] = sum(1 for h in f_hits if h.rule_id == fid)
        stats.rule_ms["F*"] = int((time.perf_counter() - t0) * 1000)
        logger.info("fusion_done", hits=len(f_hits))
    except Exception as e:  # noqa: BLE001
        stats.errors.append(f"F*: {type(e).__name__}: {e}")
        logger.exception("fusion_failed", error=str(e))
    return EngineResult(hits=t_hits + e_hits + f_hits, stats=stats), t_hits, e_hits
