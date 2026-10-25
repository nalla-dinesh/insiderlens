"""Baseline employee activity: realistic branch work rhythm for 25 employees.

Login ~08:45-09:30, view/approve work clustered 09:15-17:45, rare evening shifts
(18:30-21:30, ~3% of active days), and tiny night LOGIN noise (0.5%/emp/day,
NON-sensitive only, 22:00-24:00) so off-hours alone never convicts anyone.
role_violation is computed automatically by ctx.log (baseline stays clean by design).
"""

from __future__ import annotations

import numpy as np

from generator.rng import choose
from generator.types import GenCtx

VIEW_RATE = {"TELLER": 7.0, "OFFICER": 6.0, "MANAGER": 4.0, "ADMIN": 3.0}
ACTIVE_P = {0: 0.90, 1: 0.90, 2: 0.90, 3: 0.90, 4: 0.90, 5: 0.35, 6: 0.08}


def build(ctx: GenCtx, pop: dict[str, list[int]]) -> dict[str, int]:
    cfg, rng = ctx.cfg, ctx.rng
    view_pool = pop["personal"][:400] + pop["merchants"]
    n_logs = {"LOGIN": 0, "VIEW_ACCOUNT": 0, "sensitive": 0, "night_noise": 0}

    for emp in ctx.employees:
        emp_id, role = int(emp["emp_id"]), emp["role"]
        for day in range(cfg.days):
            if rng.random() > ACTIVE_P[ctx.weekday(day)]:
                continue
            evening = rng.random() < 0.03
            if evening:
                login_h = 18.5 + float(rng.uniform(0, 0.5))
                work_lo, work_hi = 18.8, 21.8
            else:
                login_h = 8.75 + float(rng.uniform(0, 0.5))
                work_lo, work_hi = 9.25, 17.75
            ctx.log(emp_id, "LOGIN", day, login_h)
            n_logs["LOGIN"] += 1

            for _ in range(int(rng.poisson(VIEW_RATE[role]))):
                hour = float(np.clip(12.5 + rng.normal(0, 2.5), work_lo, work_hi))
                target = int(choose(rng, view_pool)) if rng.random() < 0.9 else None
                ctx.log(emp_id, "VIEW_ACCOUNT", day, hour, target_acc=target)
                n_logs["VIEW_ACCOUNT"] += 1

            def sens(action: str, rate: float, detail, *,
                     _emp: int = emp_id, _day: int = day,
                     _lo: float = work_lo, _hi: float = work_hi) -> None:
                if rng.random() < rate:
                    ctx.log(_emp, action, _day, float(rng.uniform(_lo, _hi)),
                            target_acc=int(choose(rng, view_pool)),
                            details=detail())
                    n_logs["sensitive"] += 1

            sens("APPROVE_TXN", 1.2, lambda: {"amount": int(rng.uniform(10_000, 300_000))})
            if role in ("OFFICER", "MANAGER", "ADMIN"):
                sens("KYC_EDIT", 0.8, lambda: {"field": str(rng.choice(["phone", "address", "email"]))})
                sens("ADD_BENEFICIARY", 0.3, lambda: {"beneficiary": int(choose(rng, view_pool))})
            if role in ("MANAGER", "ADMIN"):
                sens("LIMIT_INCREASE", 0.25, lambda: {"new_daily_limit": int(rng.integers(100_000, 800_000))})
                sens("BULK_EXPORT", 0.12, lambda: {"rows": int(rng.integers(200, 2500))})
            if role == "ADMIN":
                sens("DISABLE_ALERT", 0.08, lambda: {"rule": str(rng.choice(["T1", "T2", "F5"]))})

            if rng.random() < 0.005:                      # night noise: login only
                ctx.log(emp_id, "LOGIN", day, float(rng.uniform(22.0, 23.9)))
                n_logs["night_noise"] += 1

    total = sum(n_logs.values())
    ctx.proof(f"Baseline activity: {n_logs} -> ~{total} logs across {len(ctx.employees)} employees")
    return n_logs
