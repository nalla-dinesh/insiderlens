"""Legitimate traps L1-L5: realistic activity intended to RULE OUT naive detectors.
Injected AFTER the baseline population exists so payroll/bonus recipients are real
customers. Every flow uses exempt purposes and/or spreads/time bounds that the tuned
rules must respect. gt rows (is_suspicious=0) protect evaluation from FPs.
"""

from __future__ import annotations

import pandas as pd

from generator.scenarios._util import find_cycles, forward_occurrences, induced_edges
from generator.types import GenCtx


def inject_l1(ctx: GenCtx, personal_accounts: list[int]) -> None:
    """L1: software-park payroll corp, 60 salary credits on one morning."""
    p = ctx.cfg.scenarios.l1
    corp = ctx.take_npc_business()
    corp_cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == corp)
    for c in ctx.customers:
        if c["cust_id"] == corp_cust:
            c["name"] = "TechVista Software Pvt Ltd"
    incomes = {c["cust_id"]: c["declared_income"] for c in ctx.customers}
    acc2cust = {a["acc_id"]: a["cust_id"] for a in ctx.accounts}
    recipients = sorted(personal_accounts)[: p["employees_paid"]]   # deterministic slice
    assert len(recipients) == p["employees_paid"], "not enough personal accounts for L1"
    for i, rcpt in enumerate(recipients):
        inc = incomes.get(acc2cust[rcpt], 40_000) or 40_000
        ctx.txn(corp, rcpt, round(float(inc) * 0.95, 2), p["day"], p["hour"] + i * 0.01,
                "ACH", "SALARY")
    ctx.gtb.add("L1", "ACCOUNT", corp, False)
    ctx.proof(f"L1 payroll corp {corp}: {p['employees_paid']} SALARY credits day {p['day']} "
              "~09:40 batch (exempt purpose, invisible to T-rules)")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        sal = tx[(tx["from_acc"] == corp) & (tx["purpose"] == "SALARY")]
        assert len(sal) == p["employees_paid"], \
            f"L1 payroll edges {len(sal)} != {p['employees_paid']}"

    ctx.add_assertion(f"L1: exactly {p['employees_paid']} SALARY credits from corp", check)


def inject_l2(ctx: GenCtx) -> None:
    """L2: vendor triangle — cycle YES, layering NO (spans >10d, exempt purposes,
    amounts drift up/down)."""
    p = ctx.cfg.scenarios.l2
    a, b, c = (ctx.take_npc_business() for _ in range(3))
    purposes = ("VENDOR_PAYMENT", "SERVICES", "MATERIAL_SUPPLY")
    for d_ab, d_bc, d_ca in p["loops"]:
        amts = [round(p["base_amount"] * (1 + float(ctx.rng.uniform(-p["variance"], p["variance"]))), 2)
                for _ in range(3)]
        ctx.txn(a, b, amts[0], d_ab, 11.0, "NEFT", purposes[0])
        ctx.txn(b, c, amts[1], d_bc, 15.0, "NEFT", purposes[1])
        ctx.txn(c, a, amts[2], d_ca, 10.0, "NEFT", purposes[2])
    ctx.gtb.add("L2", "ACCOUNT", [a, b, c], False)
    ctx.proof(f"L2 triangle {'/'.join(map(str, (a, b, c)))}: loops {p['loops']} — "
              "every cycle spans >10d with >=2 exempt legs")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = induced_edges(frames["transactions"], {a, b, c})
        exempt = set(ctx.cfg.exempt_purposes) | {"MATERIAL_SUPPLY"}
        cycles = find_cycles(tx, {a, b, c})
        assert cycles, "L2 expected at least one cycle"
        for cyc in cycles:
            n = len(cyc)
            leg_frames = [tx[(tx["from_acc"] == cyc[i]) & (tx["to_acc"] == cyc[(i + 1) % n])]
                          for i in range(n)]
            span_days = (pd.to_datetime(tx["ts"]).max() - pd.to_datetime(tx["ts"]).min()).days
            n_exempt = sum(int(leg["purpose"].isin(exempt).sum()) for leg in leg_frames)
            assert span_days > 10 or n_exempt >= 2, \
                f"L2 cycle looks like layering: span {span_days}d, exempt legs {n_exempt}"

    ctx.add_assertion("L2: every triangle cycle span>10d or >=2 exempt legs", check)


def inject_l3(ctx: GenCtx) -> None:
    """L3: declared Rs3L/mo trader pays Rs45L for property — exempt purpose.
    Uses an NPC person (fields enriched) so account totals stay exact."""
    p = ctx.cfg.scenarios.l3
    trader = ctx.take_npc_person()
    trader_cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == trader)
    for c in ctx.customers:
        if c["cust_id"] == trader_cust:
            c.update(occupation="Trader", declared_income=float(p["income"]), kyc_risk="LOW")
    builder = ctx.take_npc_business()
    builder_cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == builder)
    for c in ctx.customers:
        if c["cust_id"] == builder_cust:
            c["name"] = "Skyline Developers & Builders"
    ctx.txn(trader, builder, p["amount"], p["day"], 11.0, "RTGS", "PROPERTY")
    ctx.gtb.add("L3", "ACCOUNT", [trader, builder], False)
    ctx.proof(f"L3 trader {trader} (income Rs{p['income']:,.0f}) -> builder {builder} "
              f"Rs{p['amount']:,.0f} PROPERTY day {p['day']} (exempt; T6 guard counts "
              "non-exempt volume only)")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        prop = tx[(tx["from_acc"] == trader) & (tx["purpose"] == "PROPERTY")]
        assert len(prop) == 1 and float(prop.iloc[0]["amount"]) == p["amount"], "L3 property txn wrong"
        exempt = set(ctx.cfg.exempt_purposes)
        non_ex = tx[((tx["from_acc"] == trader) | (tx["to_acc"] == trader)) &
                    (~tx["purpose"].isin(exempt))]
        assert float(non_ex["amount"].sum()) <= 6 * p["income"], \
            f"L3 non-exempt volume {non_ex['amount'].sum():,.0f} exceeds 6x income — T6 would fire"

    ctx.add_assertion("L3: single PROPERTY payment; non-exempt volume <= 6x income", check)


def inject_l4(ctx: GenCtx) -> None:
    """L4: family crowdfunds Rs6L, one 97% forward next morning — occurrences = 1 < 3."""
    p = ctx.cfg.scenarios.l4
    family = ctx.take_npc_person()
    relatives = [ctx.take_npc_person() for _ in range(len(p["in_amounts"]))]
    hospital = ctx.take_npc_business()
    hosp_cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == hospital)
    for c in ctx.customers:
        if c["cust_id"] == hosp_cust:
            c["name"] = "CityCare Multispeciality Hospital"
    hours = (20.0, 21.0, 10.0)
    for rel, amt, day, hour in zip(relatives, p["in_amounts"], p["in_days"], hours):
        ctx.txn(rel, family, amt, day, hour, "NEFT", "TRANSFER")
    ctx.txn(family, hospital, p["out_amount"], p["out_day"], 12.0, "NEFT", "HOSPITAL")
    ctx.gtb.add("L4", "ACCOUNT", family, False)
    ctx.proof(f"L4 family {family}: 3 credits Rs{sum(p['in_amounts']):,.0f} days "
              f"{p['in_days']} (hours 20:00/21:00/10:00), one HOSPITAL payment "
              f"Rs{p['out_amount']:,.0f} day {p['out_day']} 12:00 — only ONE inflow inside "
              "the 48h >=80% forward window (occurrences = 1 < 3)")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        occ = forward_occurrences(tx, family, 0.8, 48)
        assert occ == 1, f"L4 forward occurrences {occ} != 1 — would look like pass-through"
        hosp = tx[(tx["from_acc"] == family) & (tx["purpose"] == "HOSPITAL")]
        assert len(hosp) == 1, "L4 hospital payment missing"

    ctx.add_assertion("L4: exactly 1 >=80% forward, single HOSPITAL outflow", check)


def inject_l5(ctx: GenCtx, personal_accounts: list[int]) -> None:
    """L5: festive bonus batch at 20:15 — EVENING but inside the working-hours band."""
    p = ctx.cfg.scenarios.l5
    employer = ctx.take_npc_business()
    emp_cust = next(a["cust_id"] for a in ctx.accounts if a["acc_id"] == employer)
    for c in ctx.customers:
        if c["cust_id"] == emp_cust:
            c["name"] = "Sunrise Textiles Ltd"
    incomes = {c["cust_id"]: c["declared_income"] for c in ctx.customers}
    acc2cust = {a["acc_id"]: a["cust_id"] for a in ctx.accounts}
    recipients = sorted(personal_accounts)[60: 60 + p["bonuses"]]   # disjoint from L1 slice
    assert len(recipients) == p["bonuses"], "not enough personal accounts for L5"
    for i, rcpt in enumerate(recipients):
        inc = incomes.get(acc2cust[rcpt], 45_000) or 45_000
        ctx.txn(employer, rcpt, round(float(inc) * 0.30, 2), p["day"], p["hour"] + i * 0.015,
                "ACH", "BONUS")   # 20:15 .. ~20:51 — evening band, still < off-hours 22:00
    ctx.gtb.add("L5", "ACCOUNT", employer, False)
    ctx.proof(f"L5 bonus employer {employer}: {p['bonuses']} BONUS payments day {p['day']} "
              "~20:15 (evening, NOT in off-hours band 22:00-06:00; exempt purpose)")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        bon = tx[(tx["from_acc"] == employer) & (tx["purpose"] == "BONUS")]
        hrs = pd.to_datetime(bon["ts"]).dt.hour
        assert len(bon) == p["bonuses"] and bool(((hrs >= 20) & (hrs < 21)).all()), \
            f"L5 bonus batch wrong: n={len(bon)}, hours={sorted(set(hrs))}"

    ctx.add_assertion("L5: 40 BONUS credits all within 20:00-21:00 evening band", check)


def inject_all(ctx: GenCtx, personal_accounts: list[int]) -> None:
    inject_l1(ctx, personal_accounts)
    inject_l2(ctx)
    inject_l3(ctx)
    inject_l4(ctx)
    inject_l5(ctx, personal_accounts)
