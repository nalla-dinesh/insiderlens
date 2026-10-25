"""API-layer fixtures — an S5-shaped insider bundle, crafted to be DETERMINISTIC.

The story: officer 1017 (Nagpur-East) edits KYC + bumps the limit on account
200071 (Mumbai-Andheri) at night, then approves one leg of a 3-hop circular ring
that starts 11h later. Ring custs share a phone.

Expected detections (derived from rules.yaml, verified by hand):
  T1 ring (600k -> 585k -> 570k, retention 95%, span <2d)  40
  E1 night-window sensitive ops at 22:13/22:16 IST         10
  E2 LIMIT_INCREASE outside OFFICER perms                  20
  E4 two config changes on 200071 same IST day             15
  F1 E-action -> T1 pattern starts 11.3h later             25
  F3 cross-branch approval of ring leg 601                 10
  modifiers: amount>5L +10, cross-branch +10, shared phone +10
  -----------------------------------------------
  total 150 -> CRITICAL.  NO T5 (accounts ACTIVE), NO F2 (no DISABLE_ALERT).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

CRAFTED: dict[str, str] = {
    "roles": (
        "role_name,allowed_actions,description\n"
        "TELLER,APPROVE_TXN|LOGIN|VIEW_ACCOUNT,front line\n"
        "OFFICER,ADD_BENEFICIARY|APPROVE_TXN|KYC_EDIT|LOGIN|VIEW_ACCOUNT,kyc officer\n"
        "MANAGER,ADD_BENEFICIARY|APPROVE_TXN|BULK_EXPORT|KYC_EDIT|LIMIT_INCREASE|LOGIN|VIEW_ACCOUNT,mgr\n"
        "ADMIN,ADD_BENEFICIARY|APPROVE_TXN|BULK_EXPORT|DISABLE_ALERT|KYC_EDIT|LIMIT_INCREASE|LOGIN|VIEW_ACCOUNT,admin\n"
    ),
    "employees": (
        "emp_id,name,role,branch,join_date,status\n"
        "1017,Myra Kulkarni,OFFICER,Nagpur-East,2021-05-01,ACTIVE\n"
        "1002,Test Teller,TELLER,Pune-Main,2022-03-15,ACTIVE\n"
        "1003,Test Manager,MANAGER,Mumbai-Andheri,2020-01-10,ACTIVE\n"
    ),
    "customers": (
        "cust_id,name,occupation,declared_income,kyc_risk,phone,address\n"
        '300071,Ring Owner A,Trader,320000.00,MEDIUM,9811110000,"1, Bandra, Mumbai"\n'
        '300072,Ring Owner B,Trader,340000.00,MEDIUM,9811110000,"2, Bandra, Mumbai"\n'
        '300073,Ring Owner C,Trader,360000.00,MEDIUM,9833333333,"3, Deccan, Pune"\n'
        '300080,Normal Cust,Teacher,45000.00,LOW,9844444444,"4, MG Road, Pune"\n'
    ),
    "accounts": (
        "acc_id,cust_id,type,branch,open_date,last_active_date,status\n"
        "200071,300071,CURRENT,Mumbai-Andheri,2020-06-01,2026-08-20,ACTIVE\n"
        "200072,300072,CURRENT,Nagpur-East,2020-06-05,2026-08-20,ACTIVE\n"
        "200073,300073,CURRENT,Pune-Main,2021-01-12,2026-08-20,ACTIVE\n"
        "200080,300080,SAVINGS,Pune-Main,2019-03-01,2026-08-20,ACTIVE\n"
    ),
    "transactions": (
        "txn_id,from_acc,to_acc,amount,ts,channel,purpose,approved_by\n"
        # the 3-hop ring (T1), leg 601 approved by the insider
        "601,200071,200072,600000.00,2026-08-16T04:00:00Z,NEFT,TRANSFER,1017\n"
        "602,200072,200073,585000.00,2026-08-17T04:10:00Z,NEFT,TRANSFER,\n"
        "603,200073,200071,570000.00,2026-08-17T08:00:00Z,NEFT,TRANSFER,\n"
        # benign background: one small transfer + one exempt salary credit
        "604,200080,200073,1500.00,2026-08-18T06:30:00Z,UPI,TRANSFER,\n"
        "605,200073,200080,45000.00,2026-08-01T04:10:00Z,ACH,SALARY,\n"
    ),
    "activity_log": (
        "log_id,emp_id,ts,action,target_acc,details,ip,device,off_hours,role_violation\n"
        # 22:13 IST = 16:43 UTC — NIGHT. off_hours=False ON PURPOSE (engine re-derives)
        '11,1017,2026-08-15T16:43:00Z,KYC_EDIT,200071,{"field":"phone"},10.20.1.5,branch-terminal,False,False\n'
        '12,1017,2026-08-15T16:46:00Z,LIMIT_INCREASE,200071,{"new_daily_limit":2000000},10.20.1.5,branch-terminal,False,False\n'
        # 09:20 IST next morning — the rogue approval
        '13,1017,2026-08-16T03:50:00Z,APPROVE_TXN,200071,"{""txn_id"":601,""amount"":600000.0}",10.20.1.5,branch-terminal,False,False\n'
        "14,1002,2026-08-16T09:10:00Z,VIEW_ACCOUNT,200080,{},10.20.2.7,branch-terminal,False,False\n"
        "15,1003,2026-08-16T09:35:00Z,LOGIN,,{},10.20.3.2,mobile-app,False,False\n"
    ),
    "ground_truth": (
        "gt_id,scenario_id,entity_type,entity_ids,is_suspicious\n"
        "1,S5,EMPLOYEE,1017,True\n"
        "2,S5,ACCOUNT,200071,True\n"
        "3,S5,ACCOUNT,200072,True\n"
        "4,S5,ACCOUNT,200073,True\n"
        "5,L1,ACCOUNT,200080,False\n"
    ),
}


@pytest.fixture()
def crafted_bundle(tmp_path: Path) -> Path:
    data_dir = tmp_path / "generated"
    data_dir.mkdir()
    files = {}
    for name, content in CRAFTED.items():
        path = data_dir / f"{name}.csv"
        path.write_text(content, encoding="utf-8", newline="")
        files[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (data_dir / "meta.json").write_text(json.dumps({"files": files}), encoding="utf-8", newline="")
    return data_dir


# ---- Phase 06 shared helpers (imported by test_cases_api / test_export) ----
async def ingest_and_run(client, engine, bundle) -> dict:  # noqa: ANN001, ANN201
    """Real ingestion + real pipeline over HTTP — the exact flow the analyst UI drives."""
    from app.db.session import build_session_factory
    from app.services.ingestion import IngestionService

    factory = build_session_factory(engine)
    await IngestionService(factory, bundle).run()
    resp = await client.post("/api/analysis/run")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def critical_alert(client) -> dict:  # noqa: ANN001, ANN201
    page = (await client.get("/api/alerts", params={"band": "CRITICAL"})).json()
    assert page["total"] == 1, page
    return page["items"][0]


async def make_case(client, alert_id: int, **kwargs) -> dict:  # noqa: ANN001, ANN003, ANN201
    resp = await client.post("/api/cases", json={"alert_id": alert_id, **kwargs})
    assert resp.status_code == 201, resp.text
    return resp.json()
