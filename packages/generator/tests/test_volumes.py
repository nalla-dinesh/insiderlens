"""Volume envelopes: the fake bank must look like the blueprint's fake bank."""

from __future__ import annotations

from generator.config import GeneratorConfig


def test_entity_totals(built):
    cfg = GeneratorConfig()
    assert len(built["customers"]) == cfg.volumes.customers_total
    assert len(built["accounts"]) == cfg.volumes.accounts_total
    assert len(built["employees"]) == cfg.volumes.employees_total
    assert len(built["roles"]) == 4


def test_transaction_and_activity_envelopes(built):
    cfg = GeneratorConfig()
    n_tx = len(built["transactions"])
    n_log = len(built["activity_log"])
    assert cfg.volumes.txn_min <= n_tx <= cfg.volumes.txn_max, f"txns {n_tx}"
    assert cfg.volumes.activity_min <= n_log <= cfg.volumes.activity_max, f"logs {n_log}"


def test_dormant_fraction_and_statuses(built):
    acc = built["accounts"]
    dormant = (acc["status"] == "DORMANT").mean()
    assert 0.02 <= dormant <= 0.12, f"dormant fraction {dormant:.2%}"
    assert set(acc["status"]) <= {"ACTIVE", "DORMANT"}
    assert set(built["accounts"]["branch"]) == {"Pune-Main", "Nagpur-East", "Mumbai-Andheri",
                                                "Delhi-CP", "Hyderabad-Hitech"}


def test_two_salary_pulses(built):
    tx = built["transactions"]
    sal = tx[tx["purpose"] == "SALARY"]
    sal_months = set(sal["ts"].dt.month)
    assert sal_months == {7, 8}, f"salary should pulse in July and August, got {sal_months}"
    assert len(sal) >= 1_000, f"only {len(sal)} salary credits"


def test_employees_role_violations_are_rare_and_planted(built):
    logs = built["activity_log"]
    viol = logs[logs["role_violation"]]
    assert len(viol) == 1, f"expected exactly the planted S5 violation, got {len(viol)}"
    assert set(viol["action"]) == {"LIMIT_INCREASE"}
    assert int(viol.iloc[0]["emp_id"]) == 1017
