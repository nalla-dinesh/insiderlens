"""F1/F2/F3 fusion — temporal glue logic. Mini fixtures, no DB (spec §5).

Anchor times are tz-aware UTC inside IST business/night hours as the case needs;
the 72h rule is exercised via P NEGATIVE (73h / reversed order), not just +1.
"""

import pandas as pd

from app.engine.fusion import f1_linkage, f2_suppression, f3_rogue_approver
from app.engine.types import RuleHit
from tests.engine.test_rules_emp import frames_with, mk_activity

T0 = pd.Timestamp("2026-08-10T04:00:00Z")  # 09:30 IST


def _mk_hit(
    rid: str, entities: list[int], first: pd.Timestamp, last: pd.Timestamp, txn_ids: list[int] | None = None
) -> RuleHit:
    return RuleHit(
        rule_id=rid,
        entity_ids=sorted(entities),
        base_points=40,
        title=f"{rid} demo",
        summary=f"{rid} on {entities}",
        evidence={"records": {"txn_ids": txn_ids or [901, 902], "log_ids": []}},
        first_ts=first.to_pydatetime(),
        last_ts=last.to_pydatetime(),
    )


def _e_hit(emp: int, log_id: int, ts: pd.Timestamp, action: str, acc: int, rid: str = "E1") -> RuleHit:
    return RuleHit(
        rule_id=rid,
        entity_ids=[emp, acc],
        base_points=10,
        title="E demo",
        summary=f"{action} at {ts}",
        evidence={
            "emp_id": emp,
            "rows": [
                {
                    "log_id": log_id,
                    "emp_id": emp,
                    "ts": ts.isoformat(),
                    "ist_clock": "x",
                    "ist_hour": 1,
                    "action": action,
                    "target_acc": acc,
                }
            ],
            "records": {"log_ids": [log_id]},
            "gates": [{"key": "demo", "observed": 1, "limit": 1}],
        },
        first_ts=ts.to_pydatetime(),
        last_ts=ts.to_pydatetime(),
    )


def _frames_for_f3(emp_branch: str, acc_branch: str, approvals: pd.DataFrame):
    fr = frames_with(approvals, employees={101: ("OFFICER", emp_branch)})
    fr.accounts = pd.DataFrame(
        [{"acc_id": 200071, "cust_id": 900071, "type": "CURRENT", "branch": acc_branch, "status": "ACTIVE"}]
    )
    return fr


# ------------------------------------------------------------------ F1 linkage
def test_f1_within_72h_fires(rules_cfg):
    e = [_e_hit(101, 9, T0, "KYC_EDIT", 200071)]
    t = [_mk_hit("T1", [200071, 200072, 200073], T0 + pd.Timedelta(hours=20), T0 + pd.Timedelta(hours=40))]
    hits = f1_linkage(t, e, rules_cfg)
    assert len(hits) == 1
    assert hits[0].rule_id == "F1"
    assert hits[0].evidence["hours_between"] == 20.0
    assert sorted(hits[0].entity_ids) == [101, 200071]


def test_f1_at_73h_silent(rules_cfg):
    e = [_e_hit(101, 9, T0, "KYC_EDIT", 200071)]
    t = [_mk_hit("T1", [200071, 200072], T0 + pd.Timedelta(hours=73), T0 + pd.Timedelta(hours=80))]
    assert f1_linkage(t, e, rules_cfg) == []


def test_f1_action_after_pattern_silent(rules_cfg):
    # Pattern STARTED before the employee action — direction matters (P2 law).
    e = [_e_hit(101, 9, T0, "KYC_EDIT", 200071)]
    t = [_mk_hit("T1", [200071, 200072], T0 - pd.Timedelta(hours=10), T0 + pd.Timedelta(hours=5))]
    assert f1_linkage(t, e, rules_cfg) == []


def test_f1_t4_not_in_f1_rule_set(rules_cfg):
    e = [_e_hit(101, 9, T0, "KYC_EDIT", 200071)]
    t = [_mk_hit("T4", [200071, 200072], T0 + pd.Timedelta(hours=5), T0 + pd.Timedelta(hours=20))]
    assert f1_linkage(t, e, rules_cfg) == []


def test_f1_dedupes_same_emp_acc_pattern(rules_cfg):
    # two different E-hits (E1 night + E4) citing the SAME emp/account/pattern
    # triple collapse to ONE F1 (P1 triple-dedupe law)
    e = [_e_hit(101, 9, T0, "KYC_EDIT", 200071, rid="E1"), _e_hit(101, 9, T0, "KYC_EDIT", 200071, rid="E4")]
    t = [_mk_hit("T1", [200071, 200072], T0 + pd.Timedelta(hours=3), T0 + pd.Timedelta(hours=9))]
    hits = f1_linkage(t, e, rules_cfg)
    assert len(hits) == 1
    assert hits[0].evidence["linked_rule"]["rule_id"] == "T1"


# ------------------------------------------------------------------ F2 suppression
def test_f2_disable_precedes_pattern_fires(rules_cfg):
    e = [_e_hit(103, 21, T0, "DISABLE_ALERT", 200055, rid="E4")]
    t = [_mk_hit("T3", [200055, 200056], T0 + pd.Timedelta(hours=10), T0 + pd.Timedelta(hours=15))]
    hits = f2_suppression(t, e, rules_cfg)
    assert len(hits) == 1
    assert hits[0].rule_id == "F2"
    assert hits[0].evidence["config_change"]["action"] == "DISABLE_ALERT"
    assert hits[0].evidence["delta_hours"] == 10.0


def test_f2_disable_after_pattern_start_silent(rules_cfg):
    e = [_e_hit(103, 21, T0 + pd.Timedelta(hours=30), "DISABLE_ALERT", 200055, rid="E4")]
    t = [_mk_hit("T3", [200055], T0, T0 + pd.Timedelta(hours=6))]
    assert f2_suppression(t, e, rules_cfg) == []


def test_f2_other_action_not_suppression(rules_cfg):
    e = [_e_hit(103, 21, T0, "LIMIT_INCREASE", 200055, rid="E4")]
    t = [_mk_hit("T3", [200055], T0 + pd.Timedelta(hours=10), T0 + pd.Timedelta(hours=12))]
    assert f2_suppression(t, e, rules_cfg) == []


def test_f2_without_disable_alert_rows_silent(rules_cfg):
    t = [_mk_hit("T3", [200055], T0, T0 + pd.Timedelta(hours=2))]
    assert f2_suppression(t, [], rules_cfg) == []


# ------------------------------------------------------------------ F3 rogue approver
def _approve_frame(emp_branch: str, acc_branch: str, txn_id: int = 901):
    act = mk_activity([(50, 101, T0, "APPROVE_TXN", 200071, False, False)])
    act.at[0, "details"] = {"txn_id": txn_id, "amount": 600000.0}
    return _frames_for_f3(emp_branch, acc_branch, act)


def test_f3_cross_branch_fires(rules_cfg):
    fr = _approve_frame("Nagpur-East", "Mumbai-Andheri")
    t = [_mk_hit("T1", [200071, 200072, 200073], T0, T0 + pd.Timedelta(hours=8), txn_ids=[901])]
    hits = f3_rogue_approver(t, fr, rules_cfg)
    assert len(hits) == 1
    assert hits[0].evidence["branch_mismatch"] == {
        "employee_branch": "Nagpur-East",
        "account_branch": "Mumbai-Andheri",
    }
    assert hits[0].evidence["records"]["txn_ids"] == [901]


def test_f3_same_branch_silent(rules_cfg):
    fr = _approve_frame("Nagpur-East", "Nagpur-East")
    t = [_mk_hit("T1", [200071, 200072], T0, T0 + pd.Timedelta(hours=8), txn_ids=[901])]
    assert f3_rogue_approver(t, fr, rules_cfg) == []


def test_f3_approval_of_non_leg_txn_silent(rules_cfg):
    fr = _approve_frame("Nagpur-East", "Mumbai-Andheri", txn_id=999)
    t = [_mk_hit("T1", [200071, 200072], T0, T0 + pd.Timedelta(hours=8), txn_ids=[901])]
    assert f3_rogue_approver(t, fr, rules_cfg) == []


def test_f3_only_t1_t4_legs_count(rules_cfg):
    # T2 record-holder must NOT become a fusible leg (spec: cycle | pass-through)
    fr = _approve_frame("Nagpur-East", "Mumbai-Andheri", txn_id=901)
    t = [_mk_hit("T2", [200071, 200072], T0, T0 + pd.Timedelta(hours=8), txn_ids=[901])]
    assert f3_rogue_approver(t, fr, rules_cfg) == []
