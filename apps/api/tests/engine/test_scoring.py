"""Scoring engine invariants — the explainability spine.

IRON LAW under test: score == sum(reason.pts) EXACTLY, on every group shape we
can think of (single hit, multi-hit same rule, modifiers, merged monsters).
"""

import re

import pandas as pd
import pytest

from app.engine.graph import EngineFrames
from app.engine.merger import AlertGroup
from app.engine.scoring import band_for, score_group, should_persist
from app.engine.types import RuleHit

T0 = pd.Timestamp("2026-08-10T04:00:00Z")


def _hit(
    rid: str, pts: int, entities: list[int], invert: int = 0, txn_ids: list[int] | None = None
) -> RuleHit:
    first = T0 + pd.Timedelta(hours=invert * 3)
    return RuleHit(
        rule_id=rid,
        entity_ids=sorted(entities),
        base_points=pts,
        title=f"{rid} title",
        summary=f"{rid} summary mention 1 account(s)",
        evidence={
            "records": {"txn_ids": txn_ids or [], "log_ids": []},
            "gates": [{"key": "demo.gate", "observed": 1, "limit": 1}],
        },
        first_ts=first.to_pydatetime(),
        last_ts=(first + pd.Timedelta(hours=2)).to_pydatetime(),
    )


def _group(hits: list[RuleHit], rule_set: list[str] | None = None) -> AlertGroup:
    return AlertGroup(
        hits=hits,
        rule_set=rule_set or [h.rule_id for h in hits],
        overflow_rules=[],
        entity_ids=sorted({e for h in hits for e in h.entity_ids}),
        window=(T0, T0 + pd.Timedelta(hours=48)),
    )


def _frames() -> EngineFrames:
    tx = pd.DataFrame(
        [
            {
                "txn_id": 501,
                "from_acc": 200071,
                "to_acc": 200072,
                "amount": 600_000.0,
                "ts": T0,
                "channel": "NEFT",
                "purpose": "TRANSFER",
            },
            {
                "txn_id": 502,
                "from_acc": 200072,
                "to_acc": 200073,
                "amount": 50_000.0,
                "ts": T0 + pd.Timedelta(hours=1),
                "channel": "NEFT",
                "purpose": "TRANSFER",
            },
            {
                "txn_id": 503,
                "from_acc": 200073,
                "to_acc": 200071,
                "amount": 45_000.0,
                "ts": T0 + pd.Timedelta(hours=2),
                "channel": "NEFT",
                "purpose": "TRANSFER",
            },
        ]
    )
    accs = pd.DataFrame(
        [
            {
                "acc_id": 200071,
                "cust_id": 300001,
                "type": "CURRENT",
                "branch": "Mumbai-Andheri",
                "status": "ACTIVE",
            },
            {
                "acc_id": 200072,
                "cust_id": 300002,
                "type": "SAVINGS",
                "branch": "Nagpur-East",
                "status": "ACTIVE",
            },
            {
                "acc_id": 200073,
                "cust_id": 300001,
                "type": "SAVINGS",
                "branch": "Nagpur-East",
                "status": "ACTIVE",
            },
        ]
    )
    custs = pd.DataFrame(
        [
            {
                "cust_id": 300001,
                "declared_income": 200_000.0,
                "occupation": "Trader",
                "phone": "9810000001",
                "address": "Mumbai",
            },
            {
                "cust_id": 300002,
                "declared_income": 45_000.0,
                "occupation": "Clerk",
                # SAME phone as cust 300001 -> S3-style shared contact
                "phone": "9810000001",
                "address": "Nagpur",
            },
        ]
    )
    emps = pd.DataFrame(
        [{"emp_id": 1017, "name": "E1", "role": "OFFICER", "branch": "Nagpur-East", "status": "ACTIVE"}]
    )
    roles = pd.DataFrame([{"role_name": "OFFICER", "allowed_actions": {"KYC_EDIT"}}])
    return EngineFrames(
        tx=tx,
        accounts=accs,
        customers=custs,
        employees=emps,
        roles=roles,
        activity=pd.DataFrame(columns=["log_id", "emp_id", "ts", "action", "target_acc", "details"]),
    )


# ------------------------------------------------------------- band boundaries
@pytest.mark.parametrize(
    "score,band",
    [
        (0, "LOW"),
        (39, "LOW"),
        (40, "MEDIUM"),
        (69, "MEDIUM"),
        (70, "HIGH"),
        (89, "HIGH"),
        (90, "CRITICAL"),
        (250, "CRITICAL"),
    ],
)
def test_band_for_boundaries(rules_cfg, score, band):
    assert band_for(score, rules_cfg) == band


# ------------------------------------------------------------- iron law
def test_score_equals_reason_sum_single_rule(rules_cfg):
    g = _group([_hit("T1", 40, [200071, 200072, 200073], txn_ids=[501])])
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    assert s.score == sum(r["pts"] for r in s.reasons)


def test_score_equals_reason_sum_with_modifiers(rules_cfg):
    # T1(40) + E4(15): has >5L leg + cross-branch accounts + shared phone
    g = _group(
        [_hit("T1", 40, [200071, 200072, 200073], txn_ids=[501, 502, 503]), _hit("E4", 15, [1017, 200071])]
    )
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    assert s.score == sum(r["pts"] for r in s.reasons)
    names = [r["rule"] for r in s.reasons]
    assert "amount_gt_5l" in names and "cross_branch" in names
    assert "shared_contact_cluster" in names  # custs 300001/300002 share phone


def test_each_modifier_at_most_once(rules_cfg):
    # MANY big legs in the group -> still exactly ONE amount_gt_5l reason
    big_tx = [
        {
            "txn_id": 1000 + i,
            "from_acc": 200071,
            "to_acc": 200072,
            "amount": 900_000.0,
            "ts": T0 + pd.Timedelta(hours=i),
            "channel": "NEFT",
            "purpose": "TRANSFER",
        }
        for i in range(4)
    ]
    fr = _frames()
    fr.tx = pd.concat([fr.tx, pd.DataFrame(big_tx)], ignore_index=True)
    g = _group([_hit("T1", 40, [200071, 200072], txn_ids=[1000, 1001, 1002, 1003])])
    s = score_group(g, rules_cfg, fr, prior_entities=set())
    amt = [r for r in s.reasons if r["rule"] == "amount_gt_5l"]
    assert len(amt) == 1
    assert amt[0]["pts"] == rules_cfg.scoring.modifiers["amount_gt_5l"]


def test_multi_hit_rule_folds_into_one_reason(rules_cfg):
    # two E1 nights on the same employee merge -> one E1 reason carrying 10 pts once
    g = _group(
        [_hit("E1", 10, [1017, 200071], invert=0), _hit("E1", 10, [1017, 200072], invert=24)], rule_set=["E1"]
    )
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    e1 = [r for r in s.reasons if r["rule"] == "E1"]
    assert len(e1) == 1 and e1[0]["pts"] == 10
    assert "folded" in e1[0]["text"]


def test_repeat_pattern_modifier(rules_cfg):
    g = _group([_hit("T1", 40, [200071, 200072], txn_ids=[501])])
    s = score_group(g, rules_cfg, _frames(), prior_entities={200071})
    rep = [r for r in s.reasons if r["rule"] == "repeat_pattern"]
    assert len(rep) == 1
    assert s.band == band_for(s.score, rules_cfg)


def test_reason_texts_carry_numbers(rules_cfg):
    g = _group([_hit("T1", 40, [200071, 200072, 200073], txn_ids=[501, 502]), _hit("E1", 10, [1017, 200071])])
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    for r in s.reasons:
        assert re.search(r"\d", r["text"]), f"reason without a number: {r!r}"


# ------------------------------------------------------------- persist policy
def test_solo_low_e_hit_is_signal_not_alert(rules_cfg):
    g = _group([_hit("E4", 15, [1017, 200071])])
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    assert should_persist(s, rules_cfg) is False  # cannot OPEN an analyst queue


def test_t_rule_solo_always_persists(rules_cfg):
    g = _group([_hit("T5", 25, [200071], txn_ids=[501])])
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    assert should_persist(s, rules_cfg) is True


def test_two_distinct_e_rules_persist(rules_cfg):
    # E1(10)+E4(15) score 25 < MEDIUM floor, but 2-rule corroboration counts
    g = _group([_hit("E1", 10, [1017, 200071]), _hit("E4", 15, [1017, 200071])])
    s = score_group(g, rules_cfg, _frames(), prior_entities=set())
    assert should_persist(s, rules_cfg) is True
