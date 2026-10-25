"""Explainable scoring — the platform's spine.

IRON LAW:  alert.score == sum(r.pts for r in alert.reasons)  — EXACTLY.
Because of that, score is DERIVED from the reasons list here, never computed
separately: reasons are built first, then `score = sum(...)`. If it can't be
explained as (+pts) line items, it cannot raise the score.

- one reason per contributing RULE (multi-hit rules fold into one reason with a
  count note — merges never multiply-count the same rule),
- one reason per MODIFIER (each modifier adds AT MOST once, even if many legs
  pass its bar),
- bands come ONLY from rules.yaml cutoffs.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.graph import EngineFrames
from app.engine.merger import AlertGroup
from app.services.rules_config import RulesConfig

BAND_LOW = "LOW"


@dataclass(frozen=True)
class ScoredGroup:
    rule_set: list[str]
    entity_ids: list[int]
    score: int
    band: str
    reasons: list[dict]  # [{rule|modifier, pts, text}] — text carries numbers
    group: AlertGroup


def band_for(score: int, cfg: RulesConfig) -> str:
    bands = cfg.scoring.bands  # {"MEDIUM": 40, "HIGH": 70, "CRITICAL": 90}
    if score >= bands["CRITICAL"]:
        return "CRITICAL"
    if score >= bands["HIGH"]:
        return "HIGH"
    if score >= bands["MEDIUM"]:
        return "MEDIUM"
    return BAND_LOW


def _modifier_reasons(
    group: AlertGroup, cfg: RulesConfig, frames: EngineFrames, prior_entities: set[int]
) -> list[dict]:
    mods = cfg.scoring.modifiers
    reasons: list[dict] = []

    # any txn leg > threshold (amounts come from hit receipts, not re-queries)
    thr = int(cfg.scoring.params.get("amount_gt_5l_threshold", 500_000))
    tx_ids = {int(t) for h in group.hits for t in h.evidence.get("records", {}).get("txn_ids", [])}
    if tx_ids:
        tx = frames.tx
        big = tx[(tx["txn_id"].isin(tx_ids)) & (tx["amount"] > thr)]
        if not big.empty:
            r = big.iloc[0]
            reasons.append(
                {
                    "rule": "amount_gt_5l",
                    "pts": mods["amount_gt_5l"],
                    "text": f"A ₹{float(r['amount']):,.0f} leg (txn "
                    f"{int(r['txn_id'])}) crossed the ₹{thr:,.0f} amount bar "
                    f"(+{mods['amount_gt_5l']})",
                }
            )

    # cross-branch: >1 distinct branch among the group's accounts, OR any employee
    # whose branch differs from every account branch in the group
    acc_branch = frames.acc_branch()
    emp_branch = frames.emp_branch()
    accs = [e for e in group.entity_ids if e in acc_branch]
    emps = [e for e in group.entity_ids if e in emp_branch]
    acc_branches = {acc_branch[a] for a in accs}
    emp_match = [e for e in emps if acc_branches and emp_branch[e] not in acc_branches]
    if len(acc_branches) > 1 or emp_match:
        bits = []
        if len(acc_branches) > 1:
            bits.append(f"pattern spans {len(acc_branches)} branches ({', '.join(sorted(acc_branches))})")
        if emp_match:
            e = emp_match[0]
            bits.append(
                f"employee {e} works at {emp_branch[e]}, not among {len(acc_branches)} account branch(es)"
            )
        reasons.append(
            {
                "rule": "cross_branch",
                "pts": mods["cross_branch"],
                "text": "Cross-branch linkage: " + "; ".join(bits) + f" (+{mods['cross_branch']})",
            }
        )

    # repeat pattern: any entity appeared in a previous run's persisted alert
    rep = sorted(set(group.entity_ids) & prior_entities)
    if rep:
        reasons.append(
            {
                "rule": "repeat_pattern",
                "pts": mods["repeat_pattern"],
                "text": f"{len(rep)} entity/entities ({rep[:5]}) already appeared "
                f"in an earlier run's alert (+{mods['repeat_pattern']})",
            }
        )

    # shared phone/address cluster among entity customers
    if len(accs) >= 2:
        a2c = dict(zip(frames.accounts["acc_id"], frames.accounts["cust_id"], strict=False))
        custs = {a2c[a] for a in accs if a in a2c}
        info = frames.customers[frames.customers["cust_id"].isin(custs)]
        shared_ph = info["phone"].duplicated().any()
        shared_ad = info["address"].duplicated().any()
        if shared_ph or shared_ad:
            kind = "phone" if shared_ph else "address"
            reasons.append(
                {
                    "rule": "shared_contact_cluster",
                    "pts": mods["shared_contact_cluster"],
                    "text": f"At least 2 entity customers (of {len(custs)}) share "
                    f"the same {kind} (+{mods['shared_contact_cluster']})",
                }
            )
    return reasons


def score_group(
    group: AlertGroup, cfg: RulesConfig, frames: EngineFrames, prior_entities: set[int]
) -> ScoredGroup:
    reasons: list[dict] = []
    by_rule: dict[str, list] = {}
    for h in group.hits:
        by_rule.setdefault(h.rule_id, []).append(h)
    for rid in group.rule_set:  # merger's capped, ordered set
        hs = by_rule.get(rid, [])
        if not hs:
            continue
        text = hs[0].summary
        if len(hs) > 1:
            text += f" (and {len(hs) - 1} more hit(s) folded in)"
        reasons.append({"rule": rid, "pts": hs[0].base_points, "text": f"[{rid}] {text}"})
    reasons.extend(_modifier_reasons(group, cfg, frames, prior_entities))
    score = sum(r["pts"] for r in reasons)  # the iron law lives HERE
    return ScoredGroup(
        rule_set=group.rule_set,
        entity_ids=group.entity_ids,
        score=score,
        band=band_for(score, cfg),
        reasons=reasons,
        group=group,
    )


def should_persist(scored: ScoredGroup, cfg: RulesConfig) -> bool:
    """Alert-vs-signal policy (console sanity, Phase-04 calibration):
    persist a merged group only if
      (a) it involves a money-pattern rule (T1-T6) or a fusion rule (F1-F3), OR
      (b) >= 2 distinct rules corroborate, OR
      (c) score >= MEDIUM band floor.
    Single-rule employee blips stay 'signals' — counted in run stats, not
    persisted as analyst-queue alerts. Kept deterministic, config-anchored."""
    rs = set(scored.rule_set)
    if rs & {"T1", "T2", "T3", "T4", "T5", "T6", "F1", "F2", "F3"}:
        return True
    if len(rs) >= 2:
        return True
    return scored.score >= int(cfg.scoring.bands["MEDIUM"])
