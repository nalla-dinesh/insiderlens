"""Baseline transaction traffic: payroll, recurring bills, merchant retail, P2P.

Baseline NEVER touches reserved accounts (scenario + NPC) — this is what makes the
suspicious patterns and legitimate traps exactly measurable. Dormant-marked accounts
also receive nothing, so their dormancy evidence stays intact.

Determinism note: all randomness flows through ctx.rng (PCG64, SEED); every `choose`
call sorts its pool first; loops only ever iterate sorted id lists.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from generator.rng import choose, lognormal_amounts
from generator.types import GenCtx

MERCHANT_PURPOSES = ["GROCERY", "FUEL", "DINING", "SHOPPING", "UTILITIES", "TUITION", "OTHER_RETAIL"]
MERCHANT_P = [0.20, 0.15, 0.15, 0.20, 0.15, 0.07, 0.08]
MERCHANT_CHANNELS = ["UPI", "IMPS", "CASH", "NEFT"]
MERCHANT_CHANNEL_P = [0.55, 0.20, 0.15, 0.10]


def _salary_days(ctx: GenCtx) -> list[int]:
    return [d for d in range(ctx.cfg.days) if (ctx.base_dt + timedelta(days=d)).day == 1]


def build(ctx: GenCtx, pop: dict[str, list[int]]) -> dict[str, int]:
    cfg, rng = ctx.cfg, ctx.rng
    personal = pop["personal"]
    active_personal = [a for a in personal if a not in set(pop["dormant"])]
    merchants, corporates = pop["merchants"], pop["corporates"]
    incomes = {c["cust_id"]: c["declared_income"] for c in ctx.customers}
    acc2cust = {a["acc_id"]: a["cust_id"] for a in ctx.accounts}
    counts: dict[str, int] = {}

    # --- 1) payroll: every personal account with income, on both month-starts ---
    employers = corporates[:12]
    pay_days = _salary_days(ctx)
    n_salary = 0
    salaried = [a for a in active_personal if (incomes.get(acc2cust[a], 0) or 0) > 15_000]
    for i, acc in enumerate(salaried):
        employer = employers[i % len(employers)]
        base_amt = float(incomes[acc2cust[acc]]) * float(rng.uniform(0.92, 1.06))
        for d in pay_days:
            ctx.txn(employer, acc, base_amt, d, 9.5 + float(rng.uniform(0, 0.75)),
                    "ACH", "SALARY")
            n_salary += 1
    counts["salary"] = n_salary

    # --- 2) recurring: rent + EMI on fixed calendar days (450 customers) ---
    subs = choose(rng, active_personal, size=min(cfg.baseline.recurring_customers,
                                                 len(active_personal)), replace=False)
    n_rec = 0
    for i, acc in enumerate(subs):
        merchant = merchants[i % len(merchants)]
        inc = float(incomes.get(acc2cust[int(acc)], 40_000) or 40_000)
        rent, emi = max(3_000.0, inc * 0.25), max(2_000.0, inc * 0.18)
        r_day, e_day = int(rng.integers(2, 5)), int(rng.integers(5, 8))
        for offset in range(0, cfg.days, 31):
            if r_day + offset < cfg.days:
                ctx.txn(int(acc), merchant, rent, r_day + offset, 10.0, "NEFT", "RENT")
                n_rec += 1
            if e_day + offset < cfg.days:
                ctx.txn(int(acc), merchant, emi, e_day + offset, 11.0, "NEFT", "EMI")
                n_rec += 1
    counts["recurring"] = n_rec

    # --- 3) merchant retail burst: ~28k small payments ---
    n_mer = cfg.baseline.merchant_txns
    buyers = choose(rng, active_personal, size=n_mer, replace=True)
    sellers = choose(rng, merchants, size=n_mer, replace=True)
    amts = lognormal_amounts(rng, median=1_300.0, sigma=0.8, size=n_mer, lo=150.0, hi=20_000.0)
    purposes = rng.choice(MERCHANT_PURPOSES, size=n_mer, p=MERCHANT_P)
    channels = rng.choice(MERCHANT_CHANNELS, size=n_mer, p=MERCHANT_CHANNEL_P)
    days = rng.integers(0, cfg.days, size=n_mer)
    hours = np.clip(rng.normal(14.0, 3.2, size=n_mer), 8.0, 21.99)
    for i in range(n_mer):
        ctx.txn(int(buyers[i]), int(sellers[i]), float(amts[i]), int(days[i]),
                float(hours[i]), str(channels[i]), str(purposes[i]))
    counts["merchant"] = n_mer

    # --- 4) P2P chatter: ~16k transfers between distinct persons ---
    n_p2p = cfg.baseline.p2p_txns
    senders = choose(rng, active_personal, size=n_p2p, replace=True)
    receivers = choose(rng, active_personal, size=n_p2p, replace=True)
    amts = lognormal_amounts(rng, median=8_000.0, sigma=0.85, size=n_p2p, lo=500.0, hi=250_000.0)
    days = rng.integers(0, cfg.days, size=n_p2p)
    hours = np.clip(rng.normal(19.5, 2.3, size=n_p2p), 7.0, 23.79)
    upi_mask = rng.random(n_p2p) < 0.8
    n_done = 0
    for i in range(n_p2p):
        if senders[i] == receivers[i]:
            continue
        ctx.txn(int(senders[i]), int(receivers[i]), float(amts[i]), int(days[i]),
                float(hours[i]), "UPI" if upi_mask[i] else "IMPS", "TRANSFER")
        n_done += 1
    counts["p2p"] = n_done

    ctx.proof(f"Baseline traffic: salary {counts['salary']}, recurring {counts['recurring']}, "
              f"merchant {counts['merchant']}, p2p {counts['p2p']} "
              f"(total {sum(counts.values())})")
    return counts
