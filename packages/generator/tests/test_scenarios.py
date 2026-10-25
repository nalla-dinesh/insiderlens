"""Every planted scenario, re-derived independently from the CSV frames.
If the generator silently changed shape, these fail even if build-time code did not.
"""

from __future__ import annotations

import pandas as pd
from generator.config import GeneratorConfig
from generator.scenarios._util import (
    chronology_and_span_days,
    find_cycles,
    forward_occurrences,
    induced_edges,
    retention,
)

CFG = GeneratorConfig()


def _gt_accounts(built, sid: str) -> set[int]:
    gt = built["ground_truth"]
    return set(gt.loc[(gt["scenario_id"] == sid) & (gt["entity_type"] == "ACCOUNT") &
                      gt["is_suspicious"], "entity_ids"].astype(int))


def test_s1_ring(built):
    p = CFG.scenarios.s1
    accs = _gt_accounts(built, "S1")
    assert len(accs) == p["hops"]
    tx = induced_edges(built["transactions"], accs)
    hits = [(retention(tx, c), chronology_and_span_days(tx, c))
            for c in find_cycles(tx, accs) if len(c) == p["hops"]]
    assert any(inc and span <= p["max_span_days"] and ret >= 0.70
               for ret, (inc, span) in hits)


def test_s2_subthreshold_ring(built):
    accs = _gt_accounts(built, "S2")
    tx = induced_edges(built["transactions"], accs)
    assert len(tx) == 3 and ((45_000 <= tx["amount"]) & (tx["amount"] < 50_000)).all()
    cycs = find_cycles(tx, accs)
    assert len(cycs) == 1
    ok, span = chronology_and_span_days(tx, cycs[0])
    assert ok and span <= 10


def test_s3_fan_in_bulk_out(built):
    p = CFG.scenarios.s3
    accs = _gt_accounts(built, "S3")
    tx = built["transactions"]
    inbound = tx[tx["to_acc"].isin(accs)]
    structured = inbound[(inbound["amount"] >= 45_000) & (inbound["amount"] < 50_000)]
    assert len(structured) >= 16
    span = (structured["ts"].max() - structured["ts"].min()).days
    assert span <= 6
    bulk = tx[(tx["amount"] == p["bulk_out_amount"]) & tx["from_acc"].isin(accs)]
    assert len(bulk) == 1, "exactly one Rs8.6L bulk-out from the S3 cluster"
    # shared-phone cluster evidence on the mule customers
    gt = built["ground_truth"]
    custs = gt.loc[(gt["scenario_id"] == "S3") & (gt["entity_type"] == "CUSTOMER"),
                   "entity_ids"].astype(int)
    phones = built["customers"].set_index("cust_id").loc[custs, "phone"]
    assert phones.nunique() == 1, "mules must share exactly one phone"


def test_s4_pass_through(built):
    p = CFG.scenarios.s4
    tx = built["transactions"]
    for m in _gt_accounts(built, "S4"):
        assert forward_occurrences(tx, m, 0.8, p["lag_hours_max"]) >= p["occurrences"]
        ins = tx[tx["to_acc"] == m]["amount"].sum()
        outs = tx[tx["from_acc"] == m]["amount"].sum()
        assert 1 - outs / ins < 0.10


def test_s5_insider(built):
    p = CFG.scenarios.s5
    emp = p["employee"]
    logs = built["activity_log"]
    emp_logs = logs[logs["emp_id"] == emp]
    night = emp_logs[emp_logs["ts"].dt.hour >= 22]
    assert {"KYC_EDIT", "LIMIT_INCREASE"} <= set(night["action"])
    lim = night[night["action"] == "LIMIT_INCREASE"].iloc[0]
    assert bool(lim["role_violation"]) and bool(lim["off_hours"])
    accs = _gt_accounts(built, "S5")
    tx = built["transactions"]
    cycs = find_cycles(induced_edges(tx, accs), accs)
    assert len(cycs) == 1 and retention(induced_edges(tx, accs), cycs[0]) >= 0.75
    approved = tx[tx["approved_by"] == emp]
    assert len(approved) >= 1
    emp_branch = built["employees"].set_index("emp_id").loc[emp, "branch"]
    for acc in accs:
        assert built["accounts"].set_index("acc_id").loc[acc, "branch"] != emp_branch \
            or built["accounts"].set_index("acc_id").loc[acc, "status"] == "ACTIVE"


def test_s6_dormant_wake(built):
    p = CFG.scenarios.s6
    (d,) = _gt_accounts(built, "S6")
    tx = built["transactions"]
    touched = tx[(tx["from_acc"] == d) | (tx["to_acc"] == d)]
    base = pd.Timestamp(CFG.start_date, tz="UTC")
    first_day = (touched["ts"].min() - base).days
    assert first_day >= 35, f"first activity day {first_day}"
    assert float(tx[tx["to_acc"] == d]["amount"].sum()) == sum(p["inflows"])
    assert float(tx[tx["from_acc"] == d]["amount"].sum()) > 900_000


def test_s7_income_mismatch(built):
    p = CFG.scenarios.s7
    gt = built["ground_truth"]
    cid = int(gt.loc[(gt["scenario_id"] == "S7") & (gt["entity_type"] == "CUSTOMER"),
                     "entity_ids"].iloc[0])
    row = built["customers"].set_index("cust_id").loc[cid]
    assert row["occupation"] == "Junior Clerk"
    tx = built["transactions"]
    (a,) = _gt_accounts(built, "S7")
    volume = tx[tx["to_acc"] == a]["amount"].sum() + tx[tx["from_acc"] == a]["amount"].sum()
    assert tx[tx["to_acc"] == a]["amount"].sum() >= 2_500_000
    assert volume > 36 * p["income"]


def test_l1_payroll_bulk(built):
    p = CFG.scenarios.l1
    gt = built["ground_truth"]
    corp = int(gt.loc[gt["scenario_id"] == "L1", "entity_ids"].iloc[0])
    tx = built["transactions"]
    assert len(tx[(tx["from_acc"] == corp) & (tx["purpose"] == "SALARY")]) == p["employees_paid"]


def test_l2_triangle_not_layering(built):
    gt = built["ground_truth"]
    accs = set(gt.loc[gt["scenario_id"] == "L2", "entity_ids"].astype(int))
    tx = induced_edges(built["transactions"], accs)
    cycles = find_cycles(tx, accs)
    assert cycles
    span = (tx["ts"].max() - tx["ts"].min()).days
    exempt = set(CFG.exempt_purposes) | {"MATERIAL_SUPPLY"}
    n_exempt = int(tx["purpose"].isin(exempt).sum())
    assert span > 10 and n_exempt >= 2


def test_l3_property_exempt(built):
    p = CFG.scenarios.l3
    gt = built["ground_truth"]
    accs = set(gt.loc[gt["scenario_id"] == "L3", "entity_ids"].astype(int))
    tx = built["transactions"]
    prop = tx[(tx["purpose"] == "PROPERTY") & (tx["amount"] == p["amount"])]
    assert len(prop) == 1 and {int(prop.iloc[0]["from_acc"]), int(prop.iloc[0]["to_acc"])} <= accs
    trader = int(prop.iloc[0]["from_acc"])
    non_ex = tx[((tx["from_acc"] == trader) | (tx["to_acc"] == trader)) &
                (~tx["purpose"].isin(set(CFG.exempt_purposes)))]
    assert float(non_ex["amount"].sum()) <= 6 * p["income"]


def test_l4_emergency_not_pass_through(built):
    gt = built["ground_truth"]
    family = int(gt.loc[gt["scenario_id"] == "L4", "entity_ids"].iloc[0])
    tx = built["transactions"]
    assert forward_occurrences(tx, family, 0.8, 48) == 1
    assert len(tx[(tx["from_acc"] == family) & (tx["purpose"] == "HOSPITAL")]) == 1


def test_l5_evening_bonus_batch(built):
    p = CFG.scenarios.l5
    gt = built["ground_truth"]
    employer = int(gt.loc[gt["scenario_id"] == "L5", "entity_ids"].iloc[0])
    bon = built["transactions"]
    bon = bon[(bon["from_acc"] == employer) & (bon["purpose"] == "BONUS")]
    assert len(bon) == p["bonuses"]
    assert ((bon["ts"].dt.hour >= 20) & (bon["ts"].dt.hour < 21)).all()
