"""T5: dormant account wakes with a burst — bank-marker path + history-gap path."""

from app.engine.rules_txn import t5_dormant
from tests.engine.conftest import frames_of, mk_tx


def _baseline():
    # someone else's earliest activity anchors the window start at day 0
    return [(0, 999, 555, 5_000, 0, 8, "UPI", "PAYMENT")]


def test_bank_marked_dormant_silence_then_burst_fires(rules_cfg):
    rows = _baseline() + [
        (1, 301, 88, 12_000, 40, 9, "UPI", "TRANSFER"),  # wakes day 40
        (2, 88, 401, 30_000, 40, 12, "RTGS", "TRANSFER"),
        (3, 88, 402, 28_000, 41, 10, "NEFT", "TRANSFER"),  # burst 58k in <72h
    ]
    hits = t5_dormant(frames_of(mk_tx(rows), accounts={88: {"status": "DORMANT"}}), rules_cfg)
    assert len(hits) == 1
    ev = hits[0].evidence
    assert ev["dormancy_evidence"] == "bank_marker"
    assert ev["silence_days_before_wake"] >= 30
    assert ev["burst_total"] > ev["burst_amount_threshold"]


def test_active_account_same_pattern_silent(rules_cfg):
    rows = _baseline() + [
        (1, 301, 88, 12_000, 40, 9, "UPI", "TRANSFER"),
        (2, 88, 401, 30_000, 40, 12, "RTGS", "TRANSFER"),
        (3, 88, 402, 28_000, 41, 10, "NEFT", "TRANSFER"),
    ]
    assert t5_dormant(frames_of(mk_tx(rows), accounts={88: {"status": "ACTIVE"}}), rules_cfg) == []


def test_short_silence_silent(rules_cfg):
    rows = _baseline() + [
        (1, 301, 88, 12_000, 10, 9, "UPI", "TRANSFER"),  # wakes day 10 < 30
        (2, 88, 401, 60_000, 10, 12, "RTGS", "TRANSFER"),
    ]
    assert t5_dormant(frames_of(mk_tx(rows), accounts={88: {"status": "DORMANT"}}), rules_cfg) == []


def test_burst_under_threshold_silent(rules_cfg):
    rows = _baseline() + [
        (1, 301, 88, 12_000, 40, 9, "UPI", "TRANSFER"),
        (2, 88, 401, 30_000, 40, 12, "RTGS", "TRANSFER"),  # only 30k < 50k
    ]
    assert t5_dormant(frames_of(mk_tx(rows), accounts={88: {"status": "DORMANT"}}), rules_cfg) == []


def test_gap_path_200_days_would_fire(rules_cfg):
    # 200d consecutive gap inside the window: day 0 leg, day 200 wake (+burst)
    rows = [
        (0, 999, 555, 5_000, 0, 8, "UPI", "PAYMENT"),
        (1, 88, 401, 8_000, 1, 9, "NEFT", "TRANSFER"),  # last activity day 1
        (2, 301, 88, 12_000, 200, 9, "UPI", "TRANSFER"),  # ~199d gap
        (3, 88, 401, 30_000, 200, 12, "RTGS", "TRANSFER"),
        (4, 88, 402, 28_000, 201, 10, "NEFT", "TRANSFER"),  # burst 58k
    ]
    hits = t5_dormant(frames_of(mk_tx(rows), accounts={88: {"status": "ACTIVE"}}), rules_cfg)
    assert len(hits) == 1 and hits[0].evidence["dormancy_evidence"] == "history_gap"
    assert hits[0].evidence["silence_days_before_wake"] >= 180
