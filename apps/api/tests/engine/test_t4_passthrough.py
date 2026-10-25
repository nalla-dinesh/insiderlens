"""T4: rapid pass-through — dominant match, discipline, route share, retention."""

from app.engine.rules_txn import t4_passthrough
from tests.engine.conftest import frames_of, mk_tx


def _acct_rows(acc: int, ratios: list[float], kept_extra: float = 0.0, next_hops: list[int] | None = None):
    """One inflow (120k) per corridor leg followed by a single dominant forward
    of ratio -> same-style next hop, 20 days apart so nothing leaks across windows."""
    next_hops = next_hops or [7] * len(ratios)
    rows, tid, day = [], 1, 2
    for k, r in enumerate(ratios):
        inflow = 120_000.0
        rows.append((tid, 5 + k, acc, inflow, day, 9, "NEFT", "TRANSFER"))
        tid += 1
        rows.append((tid, acc, next_hops[k % len(next_hops)], inflow * r, day, 21, "NEFT", "TRANSFER"))
        tid += 1
        day += 20
    if kept_extra:
        rows.append((tid, 42, acc, kept_extra, day, 9, "NEFT", "TRANSFER"))
    return rows


def test_disciplined_corridor_fires(rules_cfg):
    tx = mk_tx(_acct_rows(88, [0.90, 0.91, 0.88, 0.89, 0.92]))  # kept = 10% < 12%
    hits = t4_passthrough(frames_of(tx), rules_cfg)
    assert len(hits) == 1
    ev = hits[0].evidence
    assert ev["occurrences"] == 5
    assert ev["fraction_std"] <= ev["max_fraction_std"]
    assert ev["route_share_dominant_next_hop"] >= ev["min_route_share"]
    assert ev["median_hours"] <= 48
    assert {o["inflow_txn"] for o in ev["occurrences_detail"]}


def test_four_cycles_silent_below_min_occurrences(rules_cfg):
    tx = mk_tx(_acct_rows(88, [0.90, 0.90, 0.90, 0.90]))
    assert t4_passthrough(frames_of(tx), rules_cfg) == []


def test_ratio_079_does_not_count(rules_cfg):
    tx = mk_tx(_acct_rows(88, [0.79, 0.79, 0.79, 0.79, 0.79]))
    assert t4_passthrough(frames_of(tx), rules_cfg) == []


def test_retaining_account_silent_decoy_L4(rules_cfg):
    tx = mk_tx(_acct_rows(88, [0.90, 0.90, 0.91, 0.89, 0.91], kept_extra=600_000))
    assert t4_passthrough(frames_of(tx), rules_cfg) == []


def test_chaotic_fractions_silent_not_a_corridor(rules_cfg):
    # outs big enough to dominate, but wildly inconsistent sizes = background churn
    tx = mk_tx(_acct_rows(88, [0.85, 1.40, 0.92, 2.30, 1.10]))
    assert t4_passthrough(frames_of(tx), rules_cfg) == []


def test_fanned_next_hops_silent_route_gate(rules_cfg):
    tx = mk_tx(_acct_rows(88, [0.90, 0.91, 0.88, 0.89, 0.92], next_hops=[7, 8, 9, 10, 11]))
    assert t4_passthrough(frames_of(tx), rules_cfg) == []


def test_slow_forward_silent(rules_cfg):
    tidy = []
    for k in range(5):
        tidy.append((10 + k, 5 + k, 88, 120_000, 2 + k * 20, 9, "NEFT", "TRANSFER"))
        tidy.append((20 + k, 88, 7, 102_000, 2 + k * 20 + 3, 9, "NEFT", "TRANSFER"))  # +72h
    assert t4_passthrough(frames_of(mk_tx(tidy)), rules_cfg) == []
