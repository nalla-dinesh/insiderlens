"""Guard helpers + runner resilience (P4 loud-isolation) + build stats."""

from datetime import UTC, datetime

import networkx as nx

from app.engine.guards import exempt_leg_count, is_exempt, t2_bands_active
from app.engine.runner import run_rules
from app.engine.types import LegEvidence
from tests.engine.conftest import frames_of, mk_tx


def test_is_exempt_respects_config(rules_cfg):
    assert is_exempt("SALARY", rules_cfg)
    assert is_exempt("HOSPITAL", rules_cfg)
    assert not is_exempt("TRANSFER", rules_cfg)
    assert not is_exempt(None, rules_cfg)


def test_two_bands_active_after_extension(rules_cfg):
    bands = t2_bands_active(rules_cfg)
    assert bands == [(45_000.0, 49_999.99), (800_000.0, 999_999.0)]


def test_exempt_leg_count(rules_cfg):
    ts = datetime(2026, 7, 1, 9, tzinfo=UTC)

    def leg(purpose):
        return LegEvidence(
            txn_id=1, from_acc=1, to_acc=2, amount=10_000.0, ts=ts, channel="NEFT", purpose=purpose
        )

    legs = [leg("SALARY"), leg("TRANSFER"), leg("HOSPITAL"), leg("TRANSFER")]
    assert exempt_leg_count(legs, rules_cfg) == 2


def test_runner_isolates_failing_rule(monkeypatch, rules_cfg):
    from app.engine import rules_txn

    def boom(frames, cfg):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(rules_txn, "t3_fanin", boom)

    tx = mk_tx(
        [
            (1, 101, 102, 950_000, 5, 10, "RTGS", "TRANSFER"),
            (2, 102, 103, 902_500, 7, 11, "RTGS", "TRANSFER"),
            (3, 103, 104, 857_375, 9, 12, "RTGS", "TRANSFER"),
            (4, 104, 101, 814_506, 11, 13, "RTGS", "TRANSFER"),
        ]
    )
    fr = frames_of(tx)
    g = nx.DiGraph(list(tx.groupby(["from_acc", "to_acc"]).size().index))
    result = run_rules(g, fr, rules_cfg)
    assert any(err.startswith("T3: RuntimeError") for err in result.stats.errors)
    assert any(h.rule_id == "T1" for h in result.hits)  # the loop kept going
    assert result.stats.rule_ms["T1"] >= 0


def test_hit_constraints_enforced(rules_cfg):
    from pydantic import ValidationError

    from app.engine.types import RuleHit

    try:
        RuleHit(
            rule_id="T9", entity_ids=[], base_points=-1, title="x", summary="y", evidence={}, custom="nope"
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("RuleHit must reject unknown rules / empty entities / missing evidence")
    h = RuleHit(rule_id="T1", entity_ids=[5, 5, 3], base_points=40, title="t", summary="s", evidence={"k": 1})
    try:
        h.summary = "mutate"  # frozen model must refuse
    except ValidationError:
        pass
    else:
        raise AssertionError("RuleHit must be frozen")

    del rules_cfg
