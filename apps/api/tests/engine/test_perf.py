"""Perf law P1: full engine over a ~50k-leg bundle must finish < 60s.

Path A (preferred): read the Phase-02-ingested main DB via DATABASE_URL.
Path B (fallback):  synthetic 50k-leg frame — the law is enforced either way.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pandas as pd

from app.engine.graph import EngineFrames
from app.engine.runner import run_rules, run_transaction_rules
from app.services.rules_config import get_rules_config
from tests.conftest import RULES_YAML

PERF_BUDGET_S = 60
MIN_REAL_LEGS = 40_000


def _synthetic_frames(n: int = 50_000, seed: int = 7) -> EngineFrames:
    rng = np.random.default_rng(seed)
    src = rng.integers(1, 5_001, n)
    dst = rng.integers(1, 5_001, n)
    mask = src == dst
    dst[mask] = (dst[mask] % 5_000) + 1
    base = pd.Timestamp("2026-07-01T00:00:00Z")
    tx = pd.DataFrame(
        {
            "txn_id": np.arange(1, n + 1),
            "from_acc": src,
            "to_acc": dst,
            "amount": rng.lognormal(10, 1.2, n).round(2),
            "ts": base + pd.to_timedelta(rng.integers(0, 60 * 24 * 3600, n), unit="s"),
            "channel": rng.choice(["IMPS", "NEFT", "UPI"], n),
            "purpose": rng.choice(["TRANSFER", "PAYMENT", "SALARY"], n, p=[0.8, 0.15, 0.05]),
        }
    )
    accs = pd.DataFrame(
        {
            "acc_id": np.arange(1, 5_001),
            "cust_id": np.arange(1, 5_001),
            "type": "SAVINGS",
            "branch": "B1",
            "status": "ACTIVE",
        }
    )
    custs = pd.DataFrame(
        {
            "cust_id": np.arange(1, 5_001),
            "declared_income": 30_000.0,
            "occupation": "Clerk",
            "phone": [f"98{i:08d}" for i in range(1, 5_001)],
        }
    )
    return EngineFrames(tx=tx, accounts=accs, customers=custs)


async def _run_real_db(cfg):
    from app.config import get_settings
    from app.db.session import build_engine, build_session_factory

    eng = build_engine(get_settings().database_url)
    try:
        factory = build_session_factory(eng)
        async with factory() as s:
            from sqlalchemy import text

            n = (await s.execute(text("select count(*) from transactions"))).scalar_one()
            if n < MIN_REAL_LEGS:
                return None, 0.0, n
            t0 = time.perf_counter()
            result = await run_transaction_rules(s, cfg)
            return result, time.perf_counter() - t0, n
    finally:
        await eng.dispose()


def test_perf_under_budget():
    cfg = get_rules_config(str(RULES_YAML))
    try:
        result, dt, n = asyncio.run(_run_real_db(cfg))
    except Exception:
        result, n = None, 0
    if result is not None:
        print(f"\n[perf] REAL BUNDLE ({n} legs): build+rules={dt:.1f}s budget={PERF_BUDGET_S}s")
    else:
        frames = _synthetic_frames()
        t0 = time.perf_counter()
        pairs = frames.tx.groupby(["from_acc", "to_acc"], sort=False).size()
        import networkx as nx

        g = nx.DiGraph()
        g.add_edges_from(pairs.index)
        result = run_rules(g, frames, cfg)
        dt = time.perf_counter() - t0
        print(f"\n[perf] SYNTHETIC 50k (main DB not ingested): {dt:.1f}s budget={PERF_BUDGET_S}s")
    assert dt < PERF_BUDGET_S, f"engine took {dt:.1f}s > {PERF_BUDGET_S}s"
    assert result.stats.errors == [], f"loud failures leaked: {result.stats.errors}"

    # sanity: whichever path ran, the stats bookkeeping is coherent
    assert set(result.stats.rule_hits) == {"T1", "T2", "T3", "T4", "T5", "T6"}
    assert set(result.stats.rule_ms) == {"T1", "T2", "T3", "T4", "T5", "T6"}
