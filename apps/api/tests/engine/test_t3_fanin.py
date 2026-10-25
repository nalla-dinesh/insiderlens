"""T3: fan-in hub + bulk out — includes shared-phone cluster evidence."""

from app.engine.rules_txn import t3_fanin
from tests.engine.conftest import frames_of, mk_tx


def _hub_rows(n_senders: int, *, bulk: bool = True, purpose: str = "CASH_DEPOSIT", base: int = 46_000):
    rows, tid = [], 1
    for i in range(n_senders):
        rows.append((tid, 100 + i, 555, base + 500 * i, i % 4, 10 + i, "CASH", purpose))
        tid += 1
    if bulk:
        rows.append((tid, 555, 777, 900_000, 5, 14, "RTGS", "TRANSFER"))
    return rows


def test_nine_senders_plus_bulk_out_fires(rules_cfg):
    tx = mk_tx(_hub_rows(9))
    hits = t3_fanin(frames_of(tx), rules_cfg)
    assert len(hits) == 1
    h = hits[0]
    assert h.evidence["hub"] == 555
    assert len(h.evidence["senders"]) == 9
    assert h.evidence["bulk_multiple_vs_median"] >= 5
    assert {"first_deposit", "last_deposit", "bulk_out"} <= set(h.evidence["timeline"])


def test_seven_senders_silent(rules_cfg):
    tx = mk_tx(_hub_rows(7))
    assert t3_fanin(frames_of(tx), rules_cfg) == []


def test_no_bulk_out_silent(rules_cfg):
    tx = mk_tx(_hub_rows(10, bulk=False))
    assert t3_fanin(frames_of(tx), rules_cfg) == []


def test_payroll_fan_in_silent_decoy_L5(rules_cfg):
    # 12 around-40k+ legs from one employer into a hub with VENDOR_PAYMENT/SERVICES
    # exempt purposes — inbound legs are excluded, so the hub never qualifies.
    tx = mk_tx(_hub_rows(12, purpose="VENDOR_PAYMENT"))
    assert t3_fanin(frames_of(tx), rules_cfg) == []


def test_small_leg_fan_in_silent_leg_floor(rules_cfg):
    # normal churn-sized deposits (6k) even from 20 senders are not smurfing
    tx = mk_tx(_hub_rows(20, base=6_000))
    assert t3_fanin(frames_of(tx), rules_cfg) == []


def test_bulk_under_5x_median_silent(rules_cfg):
    rows = _hub_rows(10)
    rows[-1] = (rows[-1][0], 555, 777, 100_000, 5, 14, "RTGS", "TRANSFER")  # < 5x ~48k median
    assert t3_fanin(frames_of(mk_tx(rows)), rules_cfg) == []


def test_shared_phone_cluster_flagged(rules_cfg):
    tx = mk_tx(_hub_rows(9))
    accts = {
        **{100 + i: {"cust_id": 1000 + i} for i in range(9)},
        555: {"cust_id": 1999},
        777: {"cust_id": 1888},
    }
    custs = {a["cust_id"]: {"phone": "9812345678"} for a in accts.values()}  # ALL same phone
    custs[1999] = {"phone": "9000000000"}  # senders share; hub & receiver don't
    custs[1888] = {"phone": "9000000001"}
    hits = t3_fanin(frames_of(tx, accounts=accts, customers=custs), rules_cfg)
    assert hits[0].evidence["shared_phone_cluster"] is True
