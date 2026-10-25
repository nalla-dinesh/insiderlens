"""GenCtx — the shared build context. All creation flows through here so that:
1. ids never collide (single allocators),
2. timestamps normalize to ISO-UTC datetimes,
3. scenario/npc accounts get registered as RESERVED (baseline flows skip them),
4. scenario assertions get registered for the quality phase,
5. role_violation/off_hours flags auto-compute on every activity log.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from generator import pools
from generator.config import GeneratorConfig
from generator.ground_truth import GtBuilder

Assertion = Callable[[dict[str, pd.DataFrame]], None]

# populated during entities.build_employees — mirrored here to avoid a circular import
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "TELLER": {"LOGIN", "VIEW_ACCOUNT", "APPROVE_TXN"},
    "OFFICER": {"LOGIN", "VIEW_ACCOUNT", "APPROVE_TXN", "KYC_EDIT", "ADD_BENEFICIARY"},
    "MANAGER": {"LOGIN", "VIEW_ACCOUNT", "APPROVE_TXN", "KYC_EDIT", "ADD_BENEFICIARY",
                "LIMIT_INCREASE", "BULK_EXPORT"},
    "ADMIN": {"LOGIN", "VIEW_ACCOUNT", "APPROVE_TXN", "KYC_EDIT", "ADD_BENEFICIARY",
              "LIMIT_INCREASE", "BULK_EXPORT", "DISABLE_ALERT"},
}


@dataclass
class GenCtx:
    cfg: GeneratorConfig
    rng: np.random.Generator
    base_dt: datetime = field(init=False)

    customers: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    roles: list[dict] = field(default_factory=list)
    txns: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)

    roles_map: dict[int, str] = field(default_factory=dict)      # emp_id -> role (set by entities)
    gtb: GtBuilder = field(default_factory=GtBuilder)
    assertions: list[tuple[str, Assertion]] = field(default_factory=list)
    proofs: list[str] = field(default_factory=list)
    reserved_accounts: set[int] = field(default_factory=set)

    # NPC pool: shared shell counterparties for scenarios (reserved, never baseline-touched)
    npc_person_accounts: list[int] = field(default_factory=list)
    npc_biz_accounts: list[int] = field(default_factory=list)
    _npc_pi: int = field(default=0, init=False)
    _npc_bi: int = field(default=0, init=False)

    _cid: int = field(default=100_001, init=False)
    _aid: int = field(default=200_001, init=False)
    _tid: int = field(default=1, init=False)
    _lid: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        self.base_dt = datetime.combine(self.cfg.start_date, datetime.min.time(), tzinfo=UTC)

    # ---------- time ----------
    def ts(self, day: float, hour: float = 12.0) -> datetime:
        if not (0 <= day < self.cfg.days):
            raise ValueError(f"day {day} outside 0..{self.cfg.days - 1}")
        return self.base_dt + timedelta(days=float(day), hours=float(hour))

    def weekday(self, day: int) -> int:
        return (self.base_dt + timedelta(days=day)).weekday()

    # ---------- npc pool ----------
    def take_npc_person(self) -> int:
        aid = self.npc_person_accounts[self._npc_pi % len(self.npc_person_accounts)]
        self._npc_pi += 1
        return aid

    def take_npc_business(self) -> int:
        aid = self.npc_biz_accounts[self._npc_bi % len(self.npc_biz_accounts)]
        self._npc_bi += 1
        return aid

    # ---------- entity factories ----------
    def add_customer(self, *, name: str, occupation: str, declared_income: float,
                     kyc_risk: str, phone: str, address: str) -> int:
        cid = self._cid
        self._cid += 1
        self.customers.append({
            "cust_id": cid, "name": name, "occupation": occupation,
            "declared_income": round(float(declared_income), 2), "kyc_risk": kyc_risk,
            "phone": phone, "address": address,
        })
        return cid

    def add_account(self, cust_id: int, *, acc_type: str = "SAVINGS", branch: str | None = None,
                    status: str = "ACTIVE", open_date: str | None = None,
                    last_active_date: str | None = None, reserved: bool = False) -> int:
        aid = self._aid
        self._aid += 1
        if open_date is None:
            open_days_ago = int(self.rng.integers(30, 2900))
            open_date = (self.base_dt - timedelta(days=open_days_ago)).date().isoformat()
        if last_active_date is None:
            last_active_date = open_date
        self.accounts.append({
            "acc_id": aid, "cust_id": cust_id, "type": acc_type,
            "branch": branch or pools.pick_branch(self.rng),
            "open_date": open_date, "last_active_date": last_active_date, "status": status,
        })
        if reserved:
            self.reserved_accounts.add(aid)
        return aid

    def add_person(self, *, occupation: str | None = None, income: float | None = None,
                   phone: str | None = None, address: str | None = None, kyc: str = "LOW",
                   name: str | None = None, acc_type: str = "SAVINGS", branch: str | None = None,
                   reserved: bool = False) -> tuple[int, int]:
        if occupation is None:
            occ, inc = pools.pick_occupation(self.rng)
        else:
            occ, inc = occupation, (income if income is not None else 30_000.0)
        cid = self.add_customer(
            name=name or pools.make_person_name(self.rng), occupation=occ,
            declared_income=inc, kyc_risk=kyc,
            phone=phone or pools.make_phone(self.rng),
            address=address or pools.make_address(self.rng),
        )
        aid = self.add_account(cid, acc_type=acc_type, branch=branch, reserved=reserved)
        return cid, aid

    def add_business(self, *, name: str | None = None, acc_type: str = "CURRENT",
                     branch: str | None = None, income: float = 800_000.0, kyc: str = "LOW",
                     reserved: bool = False) -> tuple[int, int]:
        cid = self.add_customer(
            name=name or pools.make_business_name(self.rng), occupation="Business Entity",
            declared_income=income, kyc_risk=kyc,
            phone=pools.make_phone(self.rng), address=pools.make_address(self.rng),
        )
        aid = self.add_account(cid, acc_type=acc_type, branch=branch, reserved=reserved)
        return cid, aid

    def add_dormant(self, *, branch: str | None = None, last_active_day_ago: int = 400,
                    reserved: bool = True, **person_kwargs) -> tuple[int, int]:
        cid, aid = self.add_person(reserved=reserved, branch=branch, **person_kwargs)
        opened_days_ago = last_active_day_ago + int(self.rng.integers(60, 300))
        open_date = (self.base_dt - timedelta(days=opened_days_ago)).date().isoformat()
        last_active = (self.base_dt - timedelta(days=last_active_day_ago)).date().isoformat()
        for a in self.accounts:
            if a["acc_id"] == aid:
                a.update(status="DORMANT", open_date=open_date, last_active_date=last_active)
        return cid, aid

    # ---------- records ----------
    def txn(self, from_acc: int, to_acc: int, amount: float, day: float, hour: float,
            channel: str, purpose: str, approved_by: int | None = None) -> int:
        tid = self._tid
        self._tid += 1
        self.txns.append({
            "txn_id": tid, "from_acc": from_acc, "to_acc": to_acc,
            "amount": round(float(amount), 2), "ts": self.ts(day, hour),
            "channel": channel, "purpose": purpose, "approved_by": approved_by,
        })
        return tid

    def log(self, emp_id: int, action: str, day: float, hour: float, *,
            target_acc: int | None = None, details: dict | None = None,
            device: str | None = None) -> int:
        lid = self._lid
        self._lid += 1
        role = self.roles_map.get(emp_id, "")
        permissions = ROLE_PERMISSIONS.get(role, set())
        ts = self.ts(day, hour)
        self.logs.append({
            "log_id": lid, "emp_id": emp_id, "ts": ts, "action": action,
            "target_acc": target_acc, "details": details or {},
            "ip": pools.make_internal_ip(self.rng),
            "device": device or pools.pick_device(self.rng),
            "off_hours": bool(ts.hour >= 22 or ts.hour < 6),
            "role_violation": bool(permissions) and action not in permissions,
        })
        return lid

    # ---------- scenario support ----------
    def add_assertion(self, name: str, fn: Assertion) -> None:
        self.assertions.append((name, fn))

    def proof(self, line: str) -> None:
        self.proofs.append(line)

    # ---------- frames ----------
    def frames(self) -> dict[str, pd.DataFrame]:
        out = {
            "roles": pd.DataFrame(self.roles),
            "employees": pd.DataFrame(self.employees),
            "customers": pd.DataFrame(self.customers),
            "accounts": pd.DataFrame(self.accounts),
            "transactions": pd.DataFrame(self.txns),
            "activity_log": pd.DataFrame(self.logs),
            "ground_truth": self.gtb.frame(),
        }
        out["transactions"] = out["transactions"].sort_values(["ts", "txn_id"], ignore_index=True)
        out["activity_log"] = out["activity_log"].sort_values(["ts", "log_id"], ignore_index=True)
        return out

    def close_last_active(self, frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        if tx.empty:
            return
        both = pd.concat([tx[["from_acc", "ts"]].rename(columns={"from_acc": "acc"}),
                          tx[["to_acc", "ts"]].rename(columns={"to_acc": "acc"})])
        last = both.groupby("acc")["ts"].max().dt.date.astype(str)
        acc = frames["accounts"].set_index("acc_id")
        acc.loc[acc.index.isin(last.index), "last_active_date"] = last
        frames["accounts"] = acc.reset_index()
