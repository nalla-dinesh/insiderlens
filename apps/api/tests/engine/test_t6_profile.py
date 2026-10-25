"""T6: profile-volume mismatch — multiple, persistence, floor, guards."""

from app.engine.rules_txn import t6_profile
from tests.engine.conftest import frames_of, mk_tx


def _frames(rows, income, acc_type="SAVINGS", cust_id=900_088):
    accs = {88: {"cust_id": cust_id, "type": acc_type}}
    custs = {cust_id: {"declared_income": income}}
    return frames_of(mk_tx(rows), accounts=accs, customers=custs)


def _rows(month_vol: float, day0: int, n: int = 6, purpose_in: str = "PAYMENT"):
    """in+out legs summing to `month_vol` spread inside one month starting day0."""
    one = month_vol / (2 * n)
    rows = []
    for i in range(n):
        d = day0 + (i % 20)
        rows.append((i + 101, 300 + i, 88, one, d, 9, "IMPS", purpose_in))
        rows.append((i + 201, 88, 89 + (i % 3), one, d + 1, 15, "IMPS", "TRANSFER"))
    return rows


def test_sustained_30x_two_months_fires(rules_cfg):
    rows = _rows(900_000, day0=2) + _rows(930_000, day0=33)  # 30x & 31x on 30k
    hits = t6_profile(_frames(rows, income=30_000), rules_cfg)
    assert len(hits) == 2  # one per month
    assert all(h.rule_id == "T6" for h in hits)
    for h in hits:
        ev = h.evidence
        assert ev["observed_volume"] > 25 * 30_000
        assert ev["months_over_threshold"] == ["2026-07", "2026-08"]
        assert ev["top_out_txns"]


def test_big_volume_single_month_silent_persistence_gate(rules_cfg):
    rows = _rows(1_200_000, day0=2)  # 40x but ONE month only
    assert t6_profile(_frames(rows, income=30_000), rules_cfg) == []


def test_moderate_volume_silent_below_multiple(rules_cfg):
    rows = _rows(150_000, day0=2) + _rows(160_000, day0=33)  # ~5x both months
    assert t6_profile(_frames(rows, income=30_000), rules_cfg) == []


def test_low_income_floor_excluded(rules_cfg):
    # 35k income... no: 10k -> rattled 90x both months, but floor (25k) excludes
    rows = _rows(900_000, day0=2) + _rows(900_000, day0=33)
    assert t6_profile(_frames(rows, income=10_000), rules_cfg) == []


def test_exempt_only_volume_silent_decoy_L1(rules_cfg):
    rows = [
        (1, 300, 88, 900_000, 3, 9, "NEFT", "SALARY"),  # huge but exempt
        (2, 301, 88, 954_000, 34, 9, "NEFT", "BONUS"),  # exempt, month 2
        (3, 88, 89, 5_000, 5, 15, "UPI", "TRANSFER"),
        (4, 302, 88, 5_000, 6, 9, "UPI", "PAYMENT"),
    ]
    assert t6_profile(_frames(rows, income=30_000), rules_cfg) == []


def test_business_account_excluded(rules_cfg):
    rows = _rows(900_000, day0=2) + _rows(900_000, day0=33)
    assert t6_profile(_frames(rows, income=30_000, acc_type="CURRENT"), rules_cfg) == []
