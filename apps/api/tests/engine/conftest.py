"""Engine test fixtures: pure in-memory mini banks — NO database needed for rule
semantics (perf test handles DB separately)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.engine.graph import EngineFrames
from app.engine.types import RuleHit  # noqa: F401  (convenient re-import)
from app.services.rules_config import RulesConfig, get_rules_config
from tests.conftest import RULES_YAML

BASE = pd.Timestamp("2026-07-01T00:00:00Z")


def mk_tx(rows: list[tuple]) -> pd.DataFrame:
    """rows: (txn_id, from, to, amount, day, hour, channel, purpose)"""
    recs = []
    for txn_id, frm, to, amount, day, hour, channel, purpose in rows:
        recs.append(
            {
                "txn_id": txn_id,
                "from_acc": frm,
                "to_acc": to,
                "amount": float(amount),
                "ts": BASE + pd.Timedelta(days=day, hours=hour),
                "channel": channel,
                "purpose": purpose,
            }
        )
    return pd.DataFrame(recs)


def frames_of(
    tx: pd.DataFrame, accounts: dict[int, dict] | None = None, customers: dict[int, dict] | None = None
) -> EngineFrames:
    ids = sorted(set(tx["from_acc"]) | set(tx["to_acc"]))
    accounts = accounts or {}
    customers = customers or {}
    acc_rows, cust_rows = [], {}
    for a in ids:
        o = accounts.get(a, {})
        acc_rows.append(
            {
                "acc_id": a,
                "cust_id": o.get("cust_id", 900_000 + a),
                "type": o.get("type", "SAVINGS"),
                "branch": o.get("branch", "Pune-Main"),
                "status": o.get("status", "ACTIVE"),
            }
        )
    cust_ids = sorted({r["cust_id"] for r in acc_rows})
    for c in cust_ids:
        o = customers.get(c, {})
        cust_rows[c] = {
            "cust_id": c,
            "declared_income": float(o.get("declared_income", 30_000)),
            "occupation": o.get("occupation", "Clerk"),
            "phone": o.get("phone", f"97{cust_ids.index(c):08d}"),
        }
    return EngineFrames(
        tx=tx,
        accounts=pd.DataFrame(acc_rows),
        customers=pd.DataFrame(cust_rows.values()),
    )


@pytest.fixture(scope="session")
def rules_cfg() -> RulesConfig:
    return get_rules_config(str(RULES_YAML))
