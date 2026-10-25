"""Evidence assembly — ONE code path for stored evidence AND /api/timeline.

Contract per alert (DB CHECK requires non-empty):
  {
    "graph":      {"nodes": [...], "edges": [...], "truncated": bool},
    "timeline":   [{"ts", "kind": "EMPLOYEE"|"TXN", "label", "ref_id"}...] chronological,
    "thresholds": {"<rule>.<key>": {"observed", "limit", "source": "rules.yaml"}...},
    "records":    {"txn_ids": [...], "log_ids": [...]},
  }
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.types import RuleHit
from app.repositories.graph_repo import ego_graph

MAX_TIMELINE = 400
MAX_EGO_ACCOUNTS = 8


def _hit_records(hits: Iterable[RuleHit]) -> tuple[list[int], list[int]]:
    txn_ids: set[int] = set()
    log_ids: set[int] = set()
    for h in hits:
        rec = h.evidence.get("records", {})
        txn_ids.update(int(t) for t in rec.get("txn_ids", []))
        log_ids.update(int(i) for i in rec.get("log_ids", []))
    return sorted(txn_ids), sorted(log_ids)


def _hit_thresholds(hits: Iterable[RuleHit]) -> dict:
    out: dict = {}
    for h in hits:
        for gate in h.evidence.get("gates", []):
            out[f"{h.rule_id}.{gate['key']}"] = {
                "observed": gate["observed"],
                "limit": gate["limit"],
                "source": gate.get("source", "rules.yaml"),
            }
    return out


async def _timeline(session: AsyncSession, txn_ids: list[int], log_ids: list[int]) -> list[dict]:
    from app.models.activity_log import ActivityLog
    from app.models.transaction import Transaction

    events: list[dict] = []
    if txn_ids:
        rows = (
            (await session.execute(select(Transaction).where(Transaction.txn_id.in_(txn_ids[:MAX_TIMELINE]))))
            .scalars()
            .all()
        )
        for t in rows:
            events.append(
                {
                    "ts": t.ts.isoformat(),
                    "kind": "TXN",
                    "ref_id": t.txn_id,
                    "label": f"₹{float(t.amount):,.0f} {t.channel} "
                    f"{t.from_acc}→{t.to_acc} ({t.purpose or 'n/a'})",
                }
            )
    if log_ids:
        rows = (
            (await session.execute(select(ActivityLog).where(ActivityLog.log_id.in_(log_ids[:MAX_TIMELINE]))))
            .scalars()
            .all()
        )
        for log in rows:
            tgt = f" on a/c {log.target_acc}" if log.target_acc else ""
            events.append(
                {
                    "ts": log.ts.isoformat(),
                    "kind": "EMPLOYEE",
                    "ref_id": log.log_id,
                    "label": f"Employee {log.emp_id} ran {log.action}{tgt}",
                }
            )
    events.sort(key=lambda e: (e["ts"], e["kind"] != "EMPLOYEE", e["ref_id"]))
    return events[:MAX_TIMELINE]


async def build_evidence(session: AsyncSession, hits: list[RuleHit], account_entities: list[int]) -> dict:
    """Full evidence payload for one merged alert group."""
    txn_ids, log_ids = _hit_records(hits)

    nodes: dict[int, dict] = {}
    edges: dict[int, dict] = {}
    truncated = False
    for acc in account_entities[:MAX_EGO_ACCOUNTS]:
        acct_rows, tx_rows, trunc = await ego_graph(session, acc, depth=1)
        truncated = truncated or trunc
        for a in acct_rows:
            nodes.setdefault(
                a.acc_id,
                {
                    "id": a.acc_id,
                    "label": f"A/C {a.acc_id}",
                    "branch": a.branch,
                    "type": a.type,
                    "status": a.status,
                    "cust_id": a.cust_id,
                },
            )
        for t in tx_rows:
            edges.setdefault(
                t.txn_id,
                {
                    "id": t.txn_id,
                    "source": t.from_acc,
                    "target": t.to_acc,
                    "amount": float(t.amount),
                    "ts": t.ts.isoformat(),
                    "channel": t.channel,
                },
            )

    timeline = await _timeline(session, txn_ids, log_ids)
    return {
        "graph": {"nodes": list(nodes.values()), "edges": list(edges.values()), "truncated": truncated},
        "timeline": timeline,
        "thresholds": _hit_thresholds(hits),
        "records": {"txn_ids": txn_ids, "log_ids": log_ids},
    }
