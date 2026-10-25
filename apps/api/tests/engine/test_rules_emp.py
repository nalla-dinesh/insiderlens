"""E1-E5 insider rules — IST-window edges, role matrix, spike math, burst boundary.

The CSV off_hours / role_violation flags are generator HINTS; these tests
deliberately give them the WRONG value on the critical rows to prove the engine
re-derives everything from tz-aware UTC timestamps + the roles table.
"""

import pandas as pd
import pytest

from app.engine.graph import EngineFrames
from app.engine.rules_emp import e1_offhours, e2_rbac, e3_spike, e4_highrisk, e5_burst

# IST = UTC + 5:30. These UTC anchors make IST wall-clock edges legible.
UTC_2159_IST = pd.Timestamp("2026-08-10T16:29:00Z")  # 21:59 IST — silent
UTC_2200_IST = pd.Timestamp("2026-08-10T16:30:00Z")  # 22:00 IST — fires
UTC_0559_IST = pd.Timestamp("2026-08-11T00:29:00Z")  # 05:59 IST next day — fires
UTC_0600_IST = pd.Timestamp("2026-08-11T00:30:00Z")  # 06:00 IST — silent

BASE = pd.Timestamp("2026-08-01T00:00:00Z")

ROLES_DF = pd.DataFrame(
    [
        {"role_name": "TELLER", "allowed_actions": {"APPROVE_TXN", "LOGIN", "VIEW_ACCOUNT"}},
        {
            "role_name": "OFFICER",
            "allowed_actions": {"ADD_BENEFICIARY", "APPROVE_TXN", "KYC_EDIT", "LOGIN", "VIEW_ACCOUNT"},
        },
        {
            "role_name": "MANAGER",
            "allowed_actions": {
                "ADD_BENEFICIARY",
                "APPROVE_TXN",
                "BULK_EXPORT",
                "KYC_EDIT",
                "LIMIT_INCREASE",
                "LOGIN",
                "VIEW_ACCOUNT",
            },
        },
        {
            "role_name": "ADMIN",
            "allowed_actions": {
                "ADD_BENEFICIARY",
                "APPROVE_TXN",
                "BULK_EXPORT",
                "DISABLE_ALERT",
                "KYC_EDIT",
                "LIMIT_INCREASE",
                "LOGIN",
                "VIEW_ACCOUNT",
            },
        },
    ]
)

EMP_ROWS = {
    101: ("OFFICER", "Nagpur-East"),
    102: ("TELLER", "Pune-Main"),
    103: ("MANAGER", "Pune-Main"),
}


def mk_activity(rows: list[tuple]) -> pd.DataFrame:
    """rows: (log_id, emp_id, ts, action, target_acc, off_hours_flag, role_violation_flag).
    `ts` is a tz-aware UTC Timestamp. The flag columns are INTENTIONALLY wrong
    where the test name says so — the engine must ignore them."""
    recs = []
    for idx, emp, ts, action, acc, off, viol in rows:
        recs.append(
            {
                "log_id": idx,
                "emp_id": emp,
                "ts": ts,
                "action": action,
                "target_acc": acc,
                "details": {},
                "ip": "10.0.0.1",
                "device": "branch-terminal",
                "off_hours": off,
                "role_violation": viol,
            }
        )
    return pd.DataFrame(recs)


def frames_with(activity: pd.DataFrame, employees: dict[int, tuple[str, str]] | None = None) -> EngineFrames:
    employees = employees or EMP_ROWS
    emp_rows = [
        {"emp_id": e, "name": f"E{e}", "role": r, "branch": b, "status": "ACTIVE"}
        for e, (r, b) in employees.items()
    ]
    acc_ids = [int(a) for a in activity["target_acc"].dropna().unique()] if not activity.empty else []
    return EngineFrames(
        tx=pd.DataFrame(columns=["txn_id", "from_acc", "to_acc", "amount", "ts", "channel", "purpose"]),
        accounts=pd.DataFrame(
            [
                {
                    "acc_id": a,
                    "cust_id": 900_000 + a,
                    "type": "SAVINGS",
                    "branch": "Pune-Main",
                    "status": "ACTIVE",
                }
                for a in acc_ids
            ]
        ),
        customers=pd.DataFrame(
            [
                {
                    "cust_id": 900_000 + a,
                    "declared_income": 50_000.0,
                    "occupation": "Clerk",
                    "phone": f"980{a:07d}"[-10:],
                    "address": "x",
                }
                for a in acc_ids
            ]
        ),
        employees=pd.DataFrame(emp_rows),
        roles=ROLES_DF,
        activity=activity,
    )


# ----------------------------------------------------------------- E1 window edges
@pytest.mark.parametrize(
    "ts,expect",
    [
        (UTC_2159_IST, 0),
        (UTC_2200_IST, 1),
        (UTC_0559_IST, 1),
        (UTC_0600_IST, 0),
        (BASE + pd.Timedelta(hours=8), 0),  # 13:30 IST — business hours, silent
    ],
)
def test_e1_window_edges(rules_cfg, ts, expect):
    act = mk_activity([(1, 101, ts, "KYC_EDIT", 200001, False, False)])
    hits = e1_offhours(frames_with(act), rules_cfg)
    assert len(hits) == expect
    if expect:
        assert hits[0].rule_id == "E1"
        assert 101 in hits[0].entity_ids and 200001 in hits[0].entity_ids
        assert hits[0].evidence["records"]["log_ids"]


def test_e1_non_sensitive_night_action_silent(rules_cfg):
    # 23:30 IST LOGIN — night but NOT sensitive
    act = mk_activity([(1, 101, pd.Timestamp("2026-08-10T18:00:00Z"), "LOGIN", None, False, False)])
    assert e1_offhours(frames_with(act), rules_cfg) == []


def test_e1_groups_one_hit_per_emp_per_night(rules_cfg):
    night1 = pd.Timestamp("2026-08-10T17:30:00Z")  # 23:00 IST on the 10th
    night2 = pd.Timestamp("2026-08-12T23:56:00Z")  # 05:26 IST -> belongs to 12th evening
    act = mk_activity(
        [
            (1, 101, night1, "KYC_EDIT", 200001, False, False),
            (2, 101, night1 + pd.Timedelta(minutes=40), "LIMIT_INCREASE", 200001, False, False),
            (3, 101, night2, "KYC_EDIT", 200002, False, False),
        ]
    )
    hits = e1_offhours(frames_with(act), rules_cfg)
    assert len(hits) == 2  # two distinct nights, not 3 rows
    assert {h.evidence["night_of"] for h in hits} == {"2026-08-10", "2026-08-12"}


# ----------------------------------------------------------------- E2 role matrix
def _hour_rows(emp: int, action: str, acc: int = 200001, day_off: int = 0):
    ts = BASE + pd.Timedelta(days=day_off, hours=9)
    return [(1, emp, ts, action, acc, False, False)]


@pytest.mark.parametrize(
    "emp,action,expect",
    [
        (102, "VIEW_ACCOUNT", 0),  # TELLER allowed
        (102, "KYC_EDIT", 1),  # TELLER NOT allowed -> violation (flag wrongly False)
        (103, "LIMIT_INCREASE", 0),  # MANAGER allowed (flag wrongly True -> must still be silent)
        (101, "KYC_EDIT", 0),  # OFFICER allowed
        (101, "DISABLE_ALERT", 1),  # OFFICER not allowed
    ],
)
def test_e2_role_matrix(rules_cfg, emp, action, expect):
    act = mk_activity(_hour_rows(emp, action))
    hits = e2_rbac(frames_with(act), rules_cfg)
    assert len(hits) == expect
    if expect:
        assert hits[0].evidence["missing_actions"] == [action]
        assert hits[0].evidence["role"] == EMP_ROWS[emp][0]


def test_e2_groups_per_emp_per_ist_day(rules_cfg):
    day1 = BASE + pd.Timedelta(hours=9)
    day2 = BASE + pd.Timedelta(days=1, hours=9)
    act = mk_activity(
        [
            (1, 102, day1, "KYC_EDIT", 200001, False, True),
            (2, 102, day1 + pd.Timedelta(hours=2), "DISABLE_ALERT", 200002, False, True),
            (3, 102, day2, "KYC_EDIT", 200001, False, True),
        ]
    )
    hits = e2_rbac(frames_with(act), rules_cfg)
    assert len(hits) == 2
    assert hits[0].evidence["day"] != hits[1].evidence["day"]
    assert sorted(hits[0].evidence["missing_actions"]) == ["DISABLE_ALERT", "KYC_EDIT"] or sorted(
        hits[1].evidence["missing_actions"]
    ) == ["DISABLE_ALERT", "KYC_EDIT"]


# ----------------------------------------------------------------- E3 spike math
def _view_history(emp: int, days: int, per_day: int, start_log: int):
    """`per_day` VIEW_ACCOUNT rows per day for `days` consecutive days."""
    rows, lid = [], start_log
    for d in range(days):
        for h in range(per_day):
            rows.append(
                (
                    lid,
                    emp,
                    BASE + pd.Timedelta(days=d, hours=9) + pd.Timedelta(minutes=5 * h),
                    "VIEW_ACCOUNT",
                    200001 + h,
                    False,
                    False,
                )
            )
            lid += 1
    return rows, lid


def test_e3_spike_fires_vs_both_baselines(rules_cfg):
    # Officer 101: 10 quiet days (2 views/day), then a 10-view spike day.
    # personal median = 2 -> 10 > 3x2 AND 10 >= min_day_count(5)
    # peers 105/106 (also OFFICERs) stay at 2 views on the spike day ->
    # role-day median = median(10, 2, 2) = 2 -> 10 > 3x2  (both gates beaten)
    employees = {**EMP_ROWS, 105: ("OFFICER", "Pune-Main"), 106: ("OFFICER", "Nagpur-East")}
    rows, lid = _view_history(101, days=10, per_day=2, start_log=1)
    spike_day = BASE + pd.Timedelta(days=11, hours=9)
    rows += [
        (lid + i, 101, spike_day + pd.Timedelta(minutes=5 * i), "VIEW_ACCOUNT", 300000 + i, False, False)
        for i in range(10)
    ]
    lid += 10
    for peer, base_acc in ((105, 300100), (106, 300200)):
        rows += [
            (
                lid + i,
                peer,
                spike_day + pd.Timedelta(minutes=5 * i),
                "VIEW_ACCOUNT",
                base_acc + i,
                False,
                False,
            )
            for i in range(2)
        ]
        lid += 2
    hits = e3_spike(frames_with(mk_activity(rows), employees=employees), rules_cfg)
    assert len(hits) == 1
    ev = hits[0].evidence
    assert ev["day_count"] == 10
    assert ev["personal_median"] == 2.0
    assert ev["peer_median"] == 2.0
    assert ev["day_count"] > rules_cfg.thresholds.e3_spike.personal_multiple * ev["personal_median"]
    assert ev["day_count"] > rules_cfg.thresholds.e3_spike.peer_multiple * ev["peer_median"]


def test_e3_big_day_under_peer_floor_silent(rules_cfg):
    # 101's spike day is only 4 views — above 3x median 1.0 but < min_day_count 5
    rows, lid = _view_history(101, days=10, per_day=1, start_log=1)
    rows += [
        (
            lid + i,
            101,
            BASE + pd.Timedelta(days=11, hours=9) + pd.Timedelta(minutes=5 * i),
            "VIEW_ACCOUNT",
            300000 + i,
            False,
            False,
        )
        for i in range(4)
    ]
    assert e3_spike(frames_with(mk_activity(rows)), rules_cfg) == []


def test_e3_peer_median_blocks_lone_wolf(rules_cfg):
    # Second OFFICER (105) also busy on the same day: 101's 7-view day beats his own
    # median (2 -> 3x=6, 7>6 ok) but the OFFICER role-day median is median(7, 8)=7.5
    # -> 7 > 3*7.5 fails. Peer gate holds even when personal gate passes.
    employees = {**EMP_ROWS, 105: ("OFFICER", "Pune-Main")}
    rows, lid = _view_history(101, days=10, per_day=2, start_log=1)
    rows2, lid = _view_history(105, days=10, per_day=2, start_log=lid)
    spike_day = BASE + pd.Timedelta(days=11, hours=9)
    rows += [
        (lid + i, 101, spike_day + pd.Timedelta(minutes=5 * i), "VIEW_ACCOUNT", 300000 + i, False, False)
        for i in range(7)
    ]
    lid += 7
    rows += [
        (lid + i, 105, spike_day + pd.Timedelta(minutes=5 * i), "VIEW_ACCOUNT", 300100 + i, False, False)
        for i in range(8)
    ]
    hits = e3_spike(frames_with(mk_activity(rows + rows2), employees=employees), rules_cfg)
    assert hits == []


# ----------------------------------------------------------------- E4 high-risk
def test_e4_prescribed_actions_only(rules_cfg):
    day = BASE + pd.Timedelta(hours=9)
    act = mk_activity(
        [
            (1, 101, day, "KYC_EDIT", 200001, False, False),
            (2, 103, day, "LIMIT_INCREASE", 200002, False, False),
            (3, 103, day, "VIEW_ACCOUNT", 200003, False, False),  # not a config change
            (4, 103, day, "APPROVE_TXN", 200003, False, False),
        ]
    )
    hits = e4_highrisk(frames_with(act), rules_cfg)
    assert len(hits) == 2
    assert {tuple(sorted(h.entity_ids)) for h in hits} == {(101, 200001), (103, 200002)}


def test_e4_receipts_carry_change_details(rules_cfg):
    day = BASE + pd.Timedelta(hours=9)
    act = mk_activity([(1, 101, day, "KYC_EDIT", 200001, False, False)])
    act.at[0, "details"] = {"field": "phone", "old": "9000000001", "new": "9000000099"}
    hits = e4_highrisk(frames_with(act), rules_cfg)
    assert hits[0].evidence["changes"][0]["field"] == "phone"


# ----------------------------------------------------------------- E5 burst boundary
def _burst_rows(emp: int, count: int, gap_min: int = 30, start_log: int = 1):
    t0 = BASE + pd.Timedelta(hours=9)
    return [
        (start_log + i, emp, t0 + pd.Timedelta(minutes=gap_min * i), "KYC_EDIT", 200001 + i, False, False)
        for i in range(count)
    ]


def test_e5_three_actions_silent(rules_cfg):
    act = mk_activity(_burst_rows(101, 3))
    assert e5_burst(frames_with(act), rules_cfg) == []


def test_e5_four_actions_fire(rules_cfg):
    act = mk_activity(_burst_rows(101, 4))
    hits = e5_burst(frames_with(act), rules_cfg)
    assert len(hits) == 1
    assert hits[0].evidence["gates"][0]["observed"] == 4
    assert hits[0].evidence["gates"][0]["limit"] == rules_cfg.thresholds.e5_burst.min_actions


def test_e5_spread_over_48h_silent(rules_cfg):
    t0 = BASE + pd.Timedelta(hours=9)
    act = mk_activity(
        [
            (i + 1, 101, t0 + pd.Timedelta(hours=13 * i), "KYC_EDIT", 200001 + i, False, False)
            for i in range(4)
        ]
    )
    assert e5_burst(frames_with(act), rules_cfg) == []


def test_e5_second_burst_is_new_hit_not_dup(rules_cfg):
    rows = _burst_rows(101, 4, gap_min=30)
    rows += _burst_rows(101, 4, gap_min=30, start_log=101)
    # shift second burst 3 days later
    act = mk_activity(rows)
    act.loc[4:, "ts"] = act.loc[4:, "ts"] + pd.Timedelta(days=3)
    hits = e5_burst(frames_with(act), rules_cfg)
    assert len(hits) == 2
    assert hits[0].last_ts < pd.Timedelta(days=3) + hits[0].first_ts  # disjoint windows
