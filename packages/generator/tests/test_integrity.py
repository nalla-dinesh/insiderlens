"""Referential integrity + scenario isolation, verified from the CSVs themselves."""

from __future__ import annotations

BASELINE_ONLY_PURPOSES = {"GROCERY", "FUEL", "DINING", "SHOPPING", "UTILITIES",
                          "TUITION", "OTHER_RETAIL", "RENT", "EMI"}


def test_foreign_keys(built):
    acc, cust, emp = built["accounts"], built["customers"], built["employees"]
    tx, logs, gt = built["transactions"], built["activity_log"], built["ground_truth"]
    acc_ids, cust_ids, emp_ids = set(acc["acc_id"]), set(cust["cust_id"]), set(emp["emp_id"])
    assert set(tx["from_acc"]) <= acc_ids and set(tx["to_acc"]) <= acc_ids
    assert set(acc["cust_id"]) <= cust_ids
    assert set(logs["emp_id"]) <= emp_ids
    assert set(tx["approved_by"].dropna().astype(int)) <= emp_ids
    gt_acc = set(gt.loc[gt["entity_type"] == "ACCOUNT", "entity_ids"].astype(int))
    gt_cust = set(gt.loc[gt["entity_type"] == "CUSTOMER", "entity_ids"].astype(int))
    gt_emp = set(gt.loc[gt["entity_type"] == "EMPLOYEE", "entity_ids"].astype(int))
    assert gt_acc <= acc_ids and gt_cust <= cust_ids and gt_emp <= emp_ids


def test_id_ranges(built):
    assert built["customers"]["cust_id"].min() >= 100_001
    assert built["accounts"]["acc_id"].min() >= 200_001
    assert built["employees"]["emp_id"].min() >= 1001
    assert built["transactions"]["txn_id"].min() == 1
    assert built["activity_log"]["log_id"].min() == 1


def test_suspicious_accounts_have_no_baseline_traffic(built):
    """GT suspicious accounts must never appear in baseline-only flows
    (proves the reserved-account isolation the evaluation depends on)."""
    gt = built["ground_truth"]
    susp_acc = set(gt.loc[(gt["entity_type"] == "ACCOUNT") & gt["is_suspicious"],
                          "entity_ids"].astype(int))
    tx = built["transactions"]
    retail = tx[tx["purpose"].isin(BASELINE_ONLY_PURPOSES)]
    touching = set(retail["from_acc"]) | set(retail["to_acc"])
    assert not (touching & susp_acc), "baseline retail flow touched a suspicious account"
    salary_in = tx[(tx["purpose"].isin({"SALARY", "BONUS"})) & (tx["to_acc"].isin(susp_acc))]
    assert salary_in.empty, "a suspicious account received payroll — isolation broken"


def test_no_duplicate_ids(built):
    for name in ["customers", "accounts", "employees", "transactions", "activity_log"]:
        id_col = next(c for c in built[name].columns if c.endswith("_id"))
        assert built[name][id_col].is_unique, f"{name}.{id_col} has duplicates"


def test_purpose_vocabulary_bounded(built):
    purposes = set(built["transactions"]["purpose"])
    allowed = BASELINE_ONLY_PURPOSES | {"SALARY", "BONUS", "TRANSFER", "CASH_DEPOSIT",
                                        "PROPERTY", "HOSPITAL", "VENDOR_PAYMENT",
                                        "SERVICES", "MATERIAL_SUPPLY", "EMERGENCY"}
    assert purposes <= allowed, f"unexpected purposes: {purposes - allowed}"
