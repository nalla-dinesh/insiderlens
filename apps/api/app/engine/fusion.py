"""F1-F3 fusion rules — correlate EMPLOYEE actions with MONEY patterns.

Inputs are the run's T-hits and E-hits (plus raw activity rows for F3 approvals,
which never generate E-hits on their own — APPROVE_TXN is everyone's legal action).

Dedupe law (P1 pitfall): one F-hit per (employee, account, linked pattern) triple —
two rule angles citing the same action are fine, two *identical* F1s are not.
"""

from __future__ import annotations

import pandas as pd

from app.engine.graph import EngineFrames
from app.engine.types import RuleHit
from app.services.rules_config import RulesConfig


def f1_linkage(t_hits: list[RuleHit], e_hits: list[RuleHit], cfg: RulesConfig) -> list[RuleHit]:
    """E-action on account X, and X belongs to a T1/T2/T3/T5 pattern that STARTED
    within fusion.window_hours AFTER the action (action → pattern-START, P2 law)."""
    window = pd.Timedelta(hours=cfg.fusion.window_hours)
    allowed_t = set(cfg.fusion.f1_txn_rules)
    hits: dict[tuple, RuleHit] = {}

    relevant_t = [h for h in t_hits if h.rule_id in allowed_t and h.first_ts]
    for eh in e_hits:
        for row in eh.evidence.get("rows", []):
            acc = row.get("target_acc")
            if acc is None:
                continue
            e_ts = pd.Timestamp(row["ts"])
            for th in relevant_t:
                if acc not in th.entity_ids:
                    continue
                dt = pd.Timestamp(th.first_ts) - e_ts
                if dt <= pd.Timedelta(0) or dt > window:
                    continue
                key = (eh.evidence["emp_id"], acc, th.rule_id, tuple(th.entity_ids))
                if key in hits:
                    continue
                hours = round(dt.total_seconds() / 3600, 2)
                hits[key] = RuleHit(
                    rule_id="F1",
                    entity_ids=sorted({eh.evidence["emp_id"], acc}),
                    base_points=cfg.scoring.base_points["F1"],
                    title="Employee action followed by money pattern",
                    summary=(
                        f"Employee {eh.evidence['emp_id']} ran {row['action']} on account "
                        f"{acc}; a {th.rule_id} pattern involving account {acc} started "
                        f"{hours:.1f}h later."
                    ),
                    evidence={
                        "emp_id": eh.evidence["emp_id"],
                        "employee_action": {
                            "log_id": row["log_id"],
                            "action": row["action"],
                            "ts": row["ts"],
                            "target_acc": acc,
                        },
                        "linked_rule": {"rule_id": th.rule_id, "summary": th.summary},
                        "pattern_entities": th.entity_ids,
                        "hours_between": hours,
                        "window_hours_limit": cfg.fusion.window_hours,
                        "records": {
                            "log_ids": [row["log_id"]],
                            "txn_ids": th.evidence.get("records", {}).get("txn_ids", [])[:20],
                        },
                        "gates": [
                            {
                                "key": "fusion.window_hours",
                                "observed": hours,
                                "limit": cfg.fusion.window_hours,
                                "source": "rules.yaml",
                            }
                        ],
                    },
                    first_ts=e_ts.to_pydatetime(),
                    last_ts=pd.Timestamp(th.first_ts).to_pydatetime(),
                )
    return list(hits.values())


def f2_suppression(t_hits: list[RuleHit], e_hits: list[RuleHit], cfg: RulesConfig) -> list[RuleHit]:
    """DISABLE_ALERT on X precedes a confirmed T-pattern on X (E4 always cites
    DISABLE_ALERT rows, so E-hits are the reliable source)."""
    window = pd.Timedelta(hours=cfg.fusion.window_hours)
    hits: dict[tuple, RuleHit] = {}
    disable_rows: list[tuple[int, int, pd.Timestamp, int]] = []  # emp, acc, ts, log_id
    for eh in e_hits:
        for row in eh.evidence.get("rows", []):
            if row["action"] == "DISABLE_ALERT" and row.get("target_acc") is not None:
                disable_rows.append(
                    (
                        eh.evidence["emp_id"],
                        int(row["target_acc"]),
                        pd.Timestamp(row["ts"]),
                        int(row["log_id"]),
                    )
                )
    for emp, acc, ts, log_id in disable_rows:
        for th in t_hits:
            if acc not in th.entity_ids or not th.first_ts:
                continue
            dt = pd.Timestamp(th.first_ts) - ts
            if dt <= pd.Timedelta(0) or dt > window:
                continue  # must strictly PRECEDE pattern start
            key = (emp, acc, th.rule_id, tuple(th.entity_ids))
            if key in hits:
                continue
            hours = round(dt.total_seconds() / 3600, 2)
            hits[key] = RuleHit(
                rule_id="F2",
                entity_ids=sorted({emp, acc}),
                base_points=cfg.scoring.base_points["F2"],
                title="Alert suppression before fraud pattern",
                summary=(
                    f"Employee {emp} ran DISABLE_ALERT on account {acc} "
                    f"{hours:.1f}h before a {th.rule_id} pattern on that account began."
                ),
                evidence={
                    "emp_id": emp,
                    "config_change": {
                        "log_id": log_id,
                        "ts": ts.isoformat(),
                        "action": "DISABLE_ALERT",
                        "target_acc": acc,
                    },
                    "linked_rule": {"rule_id": th.rule_id, "summary": th.summary},
                    "delta_hours": hours,
                    "records": {
                        "log_ids": [log_id],
                        "txn_ids": th.evidence.get("records", {}).get("txn_ids", [])[:20],
                    },
                    "gates": [
                        {
                            "key": "fusion.window_hours",
                            "observed": hours,
                            "limit": cfg.fusion.window_hours,
                            "source": "rules.yaml",
                        }
                    ],
                },
                first_ts=ts.to_pydatetime(),
                last_ts=pd.Timestamp(th.first_ts).to_pydatetime(),
            )
    return list(hits.values())


def f3_rogue_approver(t_hits: list[RuleHit], frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """Employee approved a transaction that IS a leg of a T1 cycle / T4 pass-through,
    AND the employee's branch differs from the approved account's branch (P5 law:
    compare employee.branch with the ACCOUNT branch — the branch that owns the acc,
    not some other field)."""
    emp_branch = frames.emp_branch()
    acc_branch = frames.acc_branch()

    leg_txns: dict[int, tuple[str, set[int]]] = {}
    for th in t_hits:
        if th.rule_id not in {"T1", "T4"}:
            continue
        for tid in th.evidence.get("records", {}).get("txn_ids", []):
            leg_txns[int(tid)] = (th.rule_id, set(th.entity_ids))

    if leg_txns and not frames.activity.empty:
        appr = frames.activity[frames.activity["action"] == "APPROVE_TXN"].copy()
        appr["txn_in_details"] = appr["details"].map(
            lambda d: int(d["txn_id"]) if isinstance(d, dict) and d.get("txn_id") else None
        )
        appr = appr[appr["txn_in_details"].notna()]
        appr["txn_in_details"] = appr["txn_in_details"].astype(int)
        appr = appr[appr["txn_in_details"].isin(leg_txns)]
    else:
        return []

    hits: dict[tuple, RuleHit] = {}
    for r in appr.itertuples():
        acc = int(r.target_acc) if pd.notna(r.target_acc) else None
        if acc is None:
            continue
        e_branch, a_branch = emp_branch.get(int(r.emp_id)), acc_branch.get(acc)
        if e_branch is None or a_branch is None or e_branch == a_branch:
            continue  # same-branch approval = normal work
        rid, ent = leg_txns[int(r.txn_in_details)]
        key = (int(r.emp_id), acc, int(r.txn_in_details))
        if key in hits:
            continue
        hits[key] = RuleHit(
            rule_id="F3",
            entity_ids=sorted({int(r.emp_id), acc}),
            base_points=cfg.scoring.base_points["F3"],
            title="Cross-branch rogue approver",
            summary=(
                f"Employee {int(r.emp_id)} (branch {e_branch}) approved txn "
                f"{int(r.txn_in_details)} moving money from account {acc} "
                f"(branch {a_branch}) — a leg of a {rid} pattern."
            ),
            evidence={
                "emp_id": int(r.emp_id),
                "approval": {
                    "log_id": int(r.log_id),
                    "ts": r.ts.isoformat(),
                    "txn_id": int(r.txn_in_details),
                    "target_acc": acc,
                },
                "linked_rule": {"rule_id": rid, "entities": sorted(ent)},
                "branch_mismatch": {"employee_branch": e_branch, "account_branch": a_branch},
                "records": {"log_ids": [int(r.log_id)], "txn_ids": [int(r.txn_in_details)]},
                "gates": [
                    {
                        "key": "fusion.f3_cross_branch",
                        "observed": f"{e_branch} != {a_branch}",
                        "limit": "branches must differ",
                        "source": "rules.yaml",
                    }
                ],
            },
            first_ts=r.ts.to_pydatetime(),
            last_ts=r.ts.to_pydatetime(),
        )
    return list(hits.values())


def fusion_rules(
    t_hits: list[RuleHit], e_hits: list[RuleHit], frames: EngineFrames, cfg: RulesConfig
) -> list[RuleHit]:
    """All fusion hits for the run (deduped inside each rule, single pass)."""
    return (
        f1_linkage(t_hits, e_hits, cfg)
        + f2_suppression(t_hits, e_hits, cfg)
        + f3_rogue_approver(t_hits, frames, cfg)
    )
