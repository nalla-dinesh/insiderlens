"""Baseline population: roles, employees (+branches), NPC pool, customer/account fill.

Build ORDER matters for determinism and for scenario isolation:
    roles -> employees -> NPC pool -> [S1..S7 injectors] -> baseline fill -> [L1..L5]
Scenario and NPC accounts are RESERVED (baseline txns/views never touch them),
which keeps planted patterns and legitimate traps perfectly controlled.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from generator import pools
from generator.rng import choose
from generator.types import ROLE_PERMISSIONS, GenCtx

ROLE_DESCRIPTIONS = {
    "TELLER": "Front-line: views and transaction approvals within own branch",
    "OFFICER": "KYC maintenance and beneficiary operations",
    "MANAGER": "Limits, bulk exports, branch supervision",
    "ADMIN": "Alert configuration and system administration",
}
# (branch, tellers, officers, managers) — 23 branch staff + 2 admins = 25 employees
BRANCH_STAFFING = [
    ("Pune-Main", 3, 2, 1),
    ("Nagpur-East", 3, 1, 1),      # <- planted insider (OFFICER) lives here
    ("Mumbai-Andheri", 2, 1, 1),
    ("Delhi-CP", 2, 1, 1),
    ("Hyderabad-Hitech", 2, 1, 1),
]
S5_EMPLOYEE_ID = 1017


def build_roles(ctx: GenCtx) -> None:
    for role in ["TELLER", "OFFICER", "MANAGER", "ADMIN"]:
        ctx.roles.append({
            "role_name": role,
            "allowed_actions": "|".join(sorted(ROLE_PERMISSIONS[role])),
            "description": ROLE_DESCRIPTIONS[role],
        })


def build_employees(ctx: GenCtx) -> None:
    """Assign ids via an explicit slot list so the planted insider lands exactly on
    1017 as OFFICER @ Nagpur-East, without disturbing the staffing plan."""
    slots: list[tuple[str, str]] = []            # (branch, role)
    for branch, n_t, n_o, n_m in BRANCH_STAFFING:
        slots += [(branch, "TELLER")] * n_t
        slots += [(branch, "OFFICER")] * n_o
        slots += [(branch, "MANAGER")] * n_m
    slots += [("Pune-Main", "ADMIN")] * 2

    insider_slot = next(i for i, (b, r) in enumerate(slots)
                        if b == "Nagpur-East" and r == "OFFICER")
    start_id = S5_EMPLOYEE_ID - insider_slot

    rng = ctx.rng
    for i, (branch, role) in enumerate(slots):
        emp_id = start_id + i
        join = (ctx.base_dt - timedelta(days=int(rng.integers(365, 2400)))).date().isoformat()
        ctx.employees.append({
            "emp_id": emp_id, "name": pools.make_person_name(rng), "role": role,
            "branch": branch, "join_date": join, "status": "ACTIVE",
        })
        ctx.roles_map[emp_id] = role


def build_npc_pool(ctx: GenCtx) -> None:
    """18 shell persons + 12 businesses — feeders/collectors/builders/trap employers.
    All NPC accounts are RESERVED exactly like scenario accounts."""
    n_persons = 40                     # S4/S6/S7/L3/L4 consume 39; no wrap => episodic purity
    n_biz = ctx.cfg.volumes.npc_pool_size - n_persons
    for _ in range(n_persons):
        _, aid = ctx.add_person(reserved=True)
        ctx.npc_person_accounts.append(aid)
    for _ in range(n_biz):
        _, aid = ctx.add_business(acc_type="CURRENT", reserved=True)
        ctx.npc_biz_accounts.append(aid)


def fill_baseline_population(ctx: GenCtx) -> dict[str, list[int]]:
    """Fill customers/accounts to configured totals with realistic mix."""
    cfg, rng = ctx.cfg, ctx.rng
    merchants: list[int] = []
    corporates: list[int] = []

    while len(corporates) < cfg.baseline.corporates_min:
        _, aid = ctx.add_business(acc_type="CURRENT", income=1_500_000.0)
        corporates.append(aid)
    while len(merchants) < cfg.baseline.merchants_min:
        cid = ctx.add_customer(
            name=pools.make_person_name(rng) + " Stores", occupation="Shop Owner",
            declared_income=round(float(rng.uniform(40, 120)) * 1000, -2), kyc_risk="LOW",
            phone=pools.make_phone(rng), address=pools.make_address(rng),
        )
        merchants.append(ctx.add_account(cid, acc_type="MERCHANT"))

    while len(ctx.customers) < cfg.volumes.customers_total:
        if rng.random() < 0.88:
            cid, _ = ctx.add_person()
            income = ctx.customers[-1]["declared_income"]
            if income > 15_000:                        # salaried folks hold SALARY accounts
                ctx.accounts[-1]["type"] = "SALARY"
        else:
            ctx.add_business()

    have_acc = {a["cust_id"] for a in ctx.accounts}
    for c in ctx.customers:
        if c["cust_id"] not in have_acc:
            ctx.add_account(c["cust_id"], acc_type="SALARY" if c["declared_income"] > 15_000 else "SAVINGS")

    personal_ids = [a["acc_id"] for a in ctx.accounts
                    if a["type"] in ("SAVINGS", "SALARY") and a["acc_id"] not in ctx.reserved_accounts]
    for aid_seed in choose(rng, personal_ids, size=cfg.baseline.second_accounts, replace=False):
        if len(ctx.accounts) >= cfg.volumes.accounts_total:
            break
        cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == int(aid_seed))
        ctx.add_account(cust, acc_type="SAVINGS")
    while len(ctx.accounts) < cfg.volumes.accounts_total:
        cust = int(choose(rng, [c["cust_id"] for c in ctx.customers
                                if c["occupation"] != "Business Entity"]))
        ctx.add_account(cust, acc_type="SAVINGS")

    personal_accounts = [a for a in ctx.accounts
                         if a["type"] in ("SAVINGS", "SALARY")
                         and a["acc_id"] not in ctx.reserved_accounts]
    n_dormant = round(len(personal_accounts) * cfg.baseline.dormant_fraction)
    dormant_ids = {int(x) for x in choose(rng, [a["acc_id"] for a in personal_accounts],
                                          size=n_dormant, replace=False)}
    for a in ctx.accounts:
        if a["acc_id"] in dormant_ids:
            opened = np.datetime64(a["open_date"])
            a["status"] = "DORMANT"
            a["last_active_date"] = str(
                (opened + np.timedelta64(int(rng.integers(60, 300)), "D")).astype("datetime64[D]")
            )

    return {
        "personal": sorted(personal_ids),
        "merchants": sorted(merchants),
        "corporates": sorted(corporates),
        "dormant": sorted(dormant_ids),
    }
