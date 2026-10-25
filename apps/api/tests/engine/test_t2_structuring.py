"""T2: structuring bands — sender-level fan + pair-level, with trap decoys."""

from app.engine.rules_txn import t2_structuring
from tests.engine.conftest import frames_of, mk_tx


def _rows(
    sender: int,
    receivers: list[int],
    amounts: list[float],
    days: list[int],
    purpose: str = "TRANSFER",
    start: int = 1,
):
    out, tid = [], start
    for i, amt in enumerate(amounts):
        out.append(
            (
                tid,
                sender,
                receivers[i % len(receivers)],
                amt,
                days[i % len(days)],
                10 + (i % 8),
                "IMPS",
                purpose,
            )
        )
        tid += 1
    return out


def test_six_subthreshold_txns_fire(rules_cfg):
    tx = mk_tx(_rows(11, [21, 22, 23], [47_000] * 6, [0, 1, 2, 3, 4, 5]))
    hits = t2_structuring(frames_of(tx), rules_cfg)
    assert any(11 in h.entity_ids for h in hits)
    h = next(h for h in hits if 11 in h.entity_ids)
    assert h.evidence["aggregate"] >= 2 * h.evidence["band_ceiling"]
    assert len(h.evidence["txn_ids"]) >= rules_cfg.thresholds.t2_structuring.min_count
    assert all(0 < d < 5_000 for d in h.evidence["distance_to_band_ceiling"])


def test_four_txns_silent(rules_cfg):
    tx = mk_tx(_rows(11, [21], [47_000] * 4, [0, 1, 2, 3]))
    assert t2_structuring(frames_of(tx), rules_cfg) == []


def test_one_amount_outside_band_kills_it(rules_cfg):
    amounts = [47_000, 47_500, 48_000, 46_500, 50_001]  # last escapes band -> only 4 in-band
    tx = mk_tx(_rows(11, [21, 22], amounts, [0, 1, 2, 3, 4]))
    assert t2_structuring(frames_of(tx), rules_cfg) == []


def test_spread_over_8_days_silent(rules_cfg):
    tx = mk_tx(_rows(11, [21, 22, 23], [47_000] * 6, [0, 3, 8, 12, 16, 20]))
    assert t2_structuring(frames_of(tx), rules_cfg) == []


def test_salary_band_txns_silent_exempt_guard(rules_cfg):
    tx = mk_tx(_rows(11, [21, 22, 23], [47_000] * 6, [0, 1, 2, 3, 4, 5], purpose="SALARY"))
    assert t2_structuring(frames_of(tx), rules_cfg) == []
