"""T1: chronological circular layering — positive(s) + every named decoy."""

import networkx as nx

from app.engine.rules_txn import t1_circular
from tests.engine.conftest import frames_of, mk_tx


def _run(tx, rules_cfg, accounts=None):
    fr = frames_of(tx, accounts=accounts)
    pairs = tx.groupby(["from_acc", "to_acc"], sort=False).size()
    g = nx.DiGraph()
    g.add_edges_from(pairs.index)
    return t1_circular(g, fr, rules_cfg)


def _ring(seed: float, cut: float, days: list[int], purposes=None, start_id: int = 101):
    n = len(days)
    purposes = purposes or ["TRANSFER"] * n
    rows, amt, tid = [], seed, 1
    for i in range(n):
        f, t = start_id + i, start_id + (i + 1) % n
        rows.append((tid, f, t, round(amt, 2), days[i], 10 + i, "RTGS", purposes[i]))
        amt *= 1 - cut
        tid += 1
    return rows


def test_four_hop_ring_fires(rules_cfg):
    hits = _run(mk_tx(_ring(950_000, 0.05, [5, 7, 9, 11])), rules_cfg)
    assert len(hits) == 1
    h = hits[0]
    assert h.rule_id == "T1"
    assert h.entity_ids == [101, 102, 103, 104]
    ev = h.evidence
    assert len(ev["legs"]) == 4
    assert ev["retention"] >= rules_cfg.thresholds.t1_circular.min_retention
    assert ev["window_days_actual"] <= rules_cfg.thresholds.t1_circular.window_days


def test_eleven_day_span_silent(rules_cfg):
    assert _run(mk_tx(_ring(950_000, 0.05, [0, 3, 7, 11])), rules_cfg) == []


def test_low_retention_ring_silent(rules_cfg):
    rows = _ring(100_000, 0.0, [1, 2, 3, 4])
    rows[1] = (2, 102, 103, 80_000, 2, 11, "NEFT", "TRANSFER")
    rows[2] = (3, 103, 104, 68_000, 3, 12, "NEFT", "TRANSFER")
    rows[3] = (4, 104, 101, 68_000, 4, 13, "NEFT", "TRANSFER")  # 0.68 retention
    assert _run(mk_tx(rows), rules_cfg) == []


def test_vendor_triangle_with_exempt_legs_silent_decoy_L2(rules_cfg):
    rows = _ring(220_000, -0.15, [3, 25, 40], purposes=["VENDOR_PAYMENT", "SERVICES", "MATERIAL_SUPPLY"])
    assert _run(mk_tx(rows), rules_cfg) == []  # span>10d AND 2 exempt legs


def test_scrambled_chronology_silent(rules_cfg):
    # same ring accounts/amounts, times NOT increasing around the cycle
    rows = [
        (1, 101, 102, 950_000, 20, 10, "RTGS", "TRANSFER"),
        (2, 102, 103, 902_500, 10, 10, "RTGS", "TRANSFER"),  # ts goes BACKWARD
        (3, 103, 104, 857_375, 30, 10, "RTGS", "TRANSFER"),
        (4, 104, 101, 814_506, 15, 10, "RTGS", "TRANSFER"),
    ]
    assert _run(mk_tx(rows), rules_cfg) == []


def test_two_node_ping_pong_silent(rules_cfg):
    rows = [
        (1, 201, 202, 100_000, 1, 10, "NEFT", "TRANSFER"),
        (2, 202, 201, 95_000, 2, 10, "NEFT", "TRANSFER"),
    ]
    assert _run(mk_tx(rows), rules_cfg) == []  # min_len = 3
