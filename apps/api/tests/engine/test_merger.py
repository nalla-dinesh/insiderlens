"""Merger — union-find + caps. The mega-blob law gets exercised directly."""

import pandas as pd

from app.engine.merger import merge_hits
from app.engine.types import RuleHit

T0 = pd.Timestamp("2026-08-10T04:00:00Z")


def _h(rid: str, pts: int, entities: list[int], h_off: int = 0) -> RuleHit:
    first = T0 + pd.Timedelta(hours=h_off)
    return RuleHit(
        rule_id=rid,
        entity_ids=sorted(entities),
        base_points=pts,
        title=rid,
        summary=f"{rid} summary 1",
        evidence={"records": {"txn_ids": [], "log_ids": []}},
        first_ts=first.to_pydatetime(),
        last_ts=(first + pd.Timedelta(hours=2)).to_pydatetime(),
    )


def test_shared_entity_and_overlap_merge(rules_cfg):
    groups = merge_hits([_h("T1", 40, [200071, 200072], 0), _h("E1", 10, [1017, 200071], 2)], rules_cfg)
    assert len(groups) == 1
    g = groups[0]
    assert set(g.rule_set) == {"T1", "E1"}
    assert set(g.entity_ids) == {200071, 200072, 1017}


def test_disjoint_windows_do_not_merge(rules_cfg):
    # same account but windows 100h apart (beyond the documented 6h slack)
    groups = merge_hits([_h("E1", 10, [200001], 0), _h("E4", 15, [200001], 100)], rules_cfg)
    assert len(groups) == 2


def test_disjoint_entities_do_not_merge_even_if_simultaneous(rules_cfg):
    groups = merge_hits([_h("E1", 10, [1017, 200071], 0), _h("E1", 10, [1031, 200272], 0)], rules_cfg)
    assert len(groups) == 2


def test_rule_cap_overflow_documented_no_points(rules_cfg):
    # 7 distinct rules all sharing entities -> cap at 6, overflow documented
    hits = [
        _h("T1", 40, [200071, 200072]),
        _h("T2", 30, [200071]),
        _h("T3", 35, [200071]),
        _h("F1", 25, [1017, 200071]),
        _h("F2", 20, [1017, 200071]),
        _h("F3", 10, [1017, 200071]),
        _h("E2", 20, [1017, 200071]),
    ]
    groups = merge_hits(hits, rules_cfg)
    assert len(groups) == 1
    g = groups[0]
    assert len(g.rule_set) == rules_cfg.fusion.max_rules_per_alert
    assert g.overflow_rules == ["F3"]  # lowest base_points falls off first
    assert set(g.rule_set) | set(g.overflow_rules) == {h.rule_id for h in hits}


def test_entity_cap_splits_at_weakest_temporal_link(rules_cfg):
    # one wide chain: 24 distinct accounts, hits strung across time pairs
    hits = []
    for i in range(12):
        hits.append(_h("T1", 40, [300000 + 2 * i, 300001 + 2 * i], h_off=i * 30))
    groups = merge_hits(hits, rules_cfg)
    assert all(len(g.entity_ids) <= rules_cfg.fusion.max_entities_per_alert for g in groups)
    assert len(groups) >= 2  # the mega-blob was refused


def test_merge_empty_input(rules_cfg):
    assert merge_hits([], rules_cfg) == []
