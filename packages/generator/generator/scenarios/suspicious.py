"""Suspicious injectors S1-S7. Every injector:
  1. creates fresh RESERVED accounts (or consumes the NPC pool) — never reused elsewhere,
  2. emits transactions/activity per exact config params,
  3. writes ground-truth rows,
  4. registers a hard-fail assertion that re-derives the pattern from the built frames,
  5. appends a proof line for DATA_REPORT.md (real ids + computed metrics).
"""

from __future__ import annotations

import pandas as pd

from generator.scenarios._util import (
    chronology_and_span_days,
    find_cycles,
    forward_occurrences,
    induced_edges,
    retention,
)
from generator.types import GenCtx

_RETENTION_FLOOR = 0.70  # S1 minimum end-to-end retention for a true layering ring


def inject_s1(ctx: GenCtx) -> None:
    """S1: 4-hop circular RTGS layering ring, shrinking 4-6% per hop."""
    p = ctx.cfg.scenarios.s1
    accs = [ctx.add_person(reserved=True)[1] for _ in range(p["hops"])]
    amounts, cuts, legs = [float(p["seed_amount"])], [], []
    for i in range(p["hops"]):
        cut = float(ctx.rng.uniform(p["cut_min"], p["cut_max"]))
        cuts.append(cut)
        legs.append(ctx.txn(accs[i], accs[(i + 1) % p["hops"]], amounts[-1],
                            p["start_day"] + i * 2, 9.5 + i * 1.7, "RTGS", "TRANSFER"))
        amounts.append(round(amounts[-1] * (1 - cut), 2))
    ret = amounts[-2] / p["seed_amount"]

    ctx.gtb.add("S1", "ACCOUNT", accs, True)
    ctx.proof(f"S1 ring {' -> '.join(map(str, accs))} -> {accs[0]}: seed Rs{p['seed_amount']:,.0f}, "
              f"cuts {[f'{c:.3f}' for c in cuts]}, retention {ret:.1%}, txn_ids {legs}")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = induced_edges(frames["transactions"], set(accs))
        ok, span = False, -1.0
        for cyc in find_cycles(tx, set(accs)):
            if len(cyc) == p["hops"]:
                inc, span_days = chronology_and_span_days(tx, cyc)
                if inc and span_days <= p["max_span_days"] and retention(tx, cyc) >= _RETENTION_FLOOR:
                    ok, span = True, span_days
        assert ok, f"S1 cycle missing/violated (span<=10d, retention>={_RETENTION_FLOOR}); span={span}"

    ctx.add_assertion("S1: chronological 4-cycle, span<=10d, retention>=70%", check)


def inject_s2(ctx: GenCtx) -> None:
    """S2: 3-hop sub-threshold layering — every leg just under Rs50k."""
    p = ctx.cfg.scenarios.s2
    a, b, c = (ctx.add_person(reserved=True)[1] for _ in range(3))
    days = [p["start_day"], p["start_day"] + p["gap_days"][1], p["start_day"] + p["gap_days"][2]]
    ctx.txn(a, b, p["amounts"][0], days[0], 10.5, "IMPS", "TRANSFER")
    ctx.txn(b, c, p["amounts"][1], days[1], 14.0, "IMPS", "TRANSFER")
    ctx.txn(c, a, p["amounts"][2], days[2], 11.25, "UPI", "TRANSFER")
    ctx.gtb.add("S2", "ACCOUNT", [a, b, c], True)
    ctx.proof(f"S2 ring {a} -> {b} -> {c} -> {a}: amounts {p['amounts']} "
              f"(all Rs45k-49.9k, days {days})")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = induced_edges(frames["transactions"], {a, b, c})
        cycs = find_cycles(tx, {a, b, c})
        assert len(cycs) == 1, f"S2 expected exactly 1 cycle, found {len(cycs)}"
        ok, span = chronology_and_span_days(tx, cycs[0])
        band = sorted(float(x) for x in tx["amount"])
        assert ok and span <= 10, f"S2 chronology/span broken (span={span})"
        assert all(45_000 <= amt < 50_000 for amt in band), f"S2 legs out of band: {band}"

    ctx.add_assertion("S2: 3-cycle, monotone, span<=10d, all legs in [45k,50k)", check)


def inject_s3(ctx: GenCtx) -> None:
    """S3: structured cash fan-in to 7 mules (shared phone) -> hub -> bulk collector."""
    p = ctx.cfg.scenarios.s3
    _, source = ctx.add_business(income=2_000_000, reserved=True)
    shared_phone = "98" + "".join(str(int(x)) for x in ctx.rng.integers(0, 10, size=8))
    mules = [ctx.add_person(kyc="MEDIUM", phone=shared_phone, reserved=True)[1]
             for _ in range(p["mules"])]
    _, collector = ctx.add_business(name="Om Shivay Exports LLP", income=3_000_000, reserved=True)

    deposits: dict[int, list[float]] = {m: [] for m in mules}
    for i in range(p["deposits"]):
        mule = mules[i % p["mules"]]
        amt = float(ctx.rng.uniform(p["deposits_lo"], p["deposits_hi"]))
        ctx.txn(source, mule, amt, p["start_day"] + (i % p["window_days"]),
                9.0 + (i * 0.7) % 9, "CASH" if i % 2 == 0 else "IMPS", "CASH_DEPOSIT")
        deposits[mule].append(amt)

    hub = mules[0]
    for mule in mules:
        recvd = sum(deposits[mule])
        if recvd > 0:
            ctx.txn(mule, hub, round(recvd * 0.97, 2), p["bulk_out_day"] - 1,
                    10.0 + mules.index(mule) * 0.5, "IMPS", "TRANSFER")
    ctx.txn(hub, collector, p["bulk_out_amount"], p["bulk_out_day"], 11.5, "RTGS", "TRANSFER")

    total_in = sum(sum(v) for v in deposits.values())
    mule_custs = [a["cust_id"] for a in ctx.accounts if a["acc_id"] in mules]
    ctx.gtb.add("S3", "ACCOUNT", [source, *mules, collector], True)
    ctx.gtb.add("S3", "CUSTOMER", mule_custs, True)
    ctx.proof(f"S3 source {source} -> {p['mules']} mules {mules} (shared phone {shared_phone}) "
              f"-> hub {hub} -> collector {collector}: {p['deposits']} deposits "
              f"Rs{total_in:,.0f} total, bulk-out Rs{p['bulk_out_amount']:,.0f} day {p['bulk_out_day']}")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        win = tx[tx["to_acc"].isin(mules)]
        band = win[(win["amount"] >= p["deposits_lo"] * 0.9) & (win["amount"] < 50_000)]
        first = pd.to_datetime(win["ts"]).min()
        last = pd.to_datetime(band["ts"]).max()
        assert len(band) >= p["deposits"] - 1, f"S3 deposits {len(band)} < {p['deposits'] - 1}"
        assert (last - first).days <= 6, f"S3 deposit window {(last - first).days}d > 6d"
        bulk = tx[(tx["from_acc"] == hub) & (tx["to_acc"] == collector)]
        med = float(band["amount"].median())
        assert len(bulk) == 1 and float(bulk.iloc[0]["amount"]) >= 5 * med, \
            "S3 bulk-out missing or < 5x median deposit"

    ctx.add_assertion("S3: >=16 structured deposits in <=6d, then >=5x median bulk-out", check)


def inject_s4(ctx: GenCtx) -> None:
    """S4: two high-turnover mule accounts — sink in, forward 86-95% within 20h."""
    p = ctx.cfg.scenarios.s4
    mules = [ctx.add_person(kyc="MEDIUM", reserved=True)[1] for _ in range(p["accounts"])]
    hops = [ctx.take_npc_person(), ctx.take_npc_person()]

    for m_i, mule in enumerate(mules):
        for o in range(p["occurrences"]):
            feeder = ctx.take_npc_person()
            in_amt = float(p["inflow_amounts"][o])
            ratio = float(ctx.rng.uniform(p["forward_ratio_lo"], p["forward_ratio_hi"]))
            lag = float(ctx.rng.uniform(2, p["lag_hours_max"] - 1))
            day = p["days"][o]
            ctx.txn(feeder, mule, in_amt, day, 9.5, "IMPS", "TRANSFER")
            ctx.txn(mule, hops[m_i], round(in_amt * ratio, 2),
                    day + (9.5 + lag) / 24.0, 0.0, "IMPS", "TRANSFER")  # absolute offset: inflow+lag h

    ctx.gtb.add("S4", "ACCOUNT", mules, True)
    ctx.proof(f"S4 mules {mules} -> hops {hops}: {p['occurrences']} occurrences each, "
              f"days {p['days']}, forward {p['forward_ratio_lo']:.2f}-{p['forward_ratio_hi']:.2f} "
              f"within {p['lag_hours_max']}h")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        for m in mules:
            occ = forward_occurrences(tx, m, 0.8, p["lag_hours_max"])
            assert occ >= p["occurrences"], f"S4 mule {m}: only {occ} rapid forwards"
            ins = tx[tx["to_acc"] == m]["amount"].sum()
            outs = tx[tx["from_acc"] == m]["amount"].sum()
            kept = 1 - outs / ins
            assert kept < 0.12, f"S4 mule {m}: kept {kept:.1%} — account should drain >=88%"

    ctx.add_assertion("S4: >=5 forwards >=80% within 20h per mule, drains >=88% of inflow", check)


def inject_s5(ctx: GenCtx) -> None:
    """S5: insider officer 1017 — night KYC_EDIT + role-violating LIMIT_INCREASE,
    then RTGS approved leg closing a clean 3-cycle (expected merged score ~[130,170];
    the target account is NORMAL, so dormant reactivation must NOT fire)."""
    p = ctx.cfg.scenarios.s5
    emp = int(p["employee"])
    emp_branch = next(e["branch"] for e in ctx.employees if e["emp_id"] == emp)

    # target: OLD but ACTIVE, quiet current account at a DIFFERENT branch
    _, d = ctx.add_person(branch=next(b for b in ["Mumbai-Andheri", "Delhi-CP"] if b != emp_branch),
                          acc_type="CURRENT", reserved=True)
    for acc in ctx.accounts:
        if acc["acc_id"] == d:
            acc.update(status="ACTIVE",
                       open_date=(ctx.base_dt - pd.Timedelta(days=1800)).date().isoformat())
    _, pq = ctx.add_person(reserved=True)
    _, qr = ctx.add_person(reserved=True)

    night = p["night_day"]
    ctx.log(emp, "LOGIN", night, 23.68)
    ctx.log(emp, "KYC_EDIT", night, 23.73, target_acc=d,
            details={"field": "address", "old": "Pune", "new": "Nagpur"})
    ctx.log(emp, "LIMIT_INCREASE", night, 23.78, target_acc=d,
            details={"new_daily_limit": 1_000_000})          # OFFICER cannot -> role_violation

    d0 = p["cycle_days"][0]
    leg1 = ctx.txn(d, pq, p["cycle_seed"], d0, 10.25, "RTGS", "TRANSFER", approved_by=emp)
    ctx.log(emp, "APPROVE_TXN", d0, 9.95, target_acc=d,
            details={"txn_id": leg1, "amount": p["cycle_seed"]})   # morning, role-legal
    leg2_amt = round(p["cycle_seed"] * (1 - p["cut"]), 2)
    leg3_amt = round(leg2_amt * (1 - p["cut"]), 2)
    ctx.txn(pq, qr, leg2_amt, p["cycle_days"][1], 14.0, "NEFT", "TRANSFER")
    ctx.txn(qr, d, leg3_amt, p["cycle_days"][2], 11.0, "NEFT", "TRANSFER")
    ret = leg3_amt / p["cycle_seed"]

    ctx.gtb.add("S5", "EMPLOYEE", emp, True)
    ctx.gtb.add("S5", "ACCOUNT", [d, pq, qr], True)
    ctx.proof(f"S5 employee {emp} OFFICER@{emp_branch}: night day{night} LOGIN 23:41, "
              f"KYC_EDIT 23:44, LIMIT_INCREASE 23:47 (role-violation) on ACTIVE acc {d}; "
              f"approved RTGS leg txn {leg1} cross-branch; cycle {d}->{pq}->{qr}->{d} "
              f"retention {ret:.1%}")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        logs = frames["activity_log"]
        ts = pd.to_datetime(logs["ts"])
        emp_logs = logs[logs["emp_id"] == emp]
        night_logs = emp_logs[ts.loc[emp_logs.index].dt.normalize() ==
                              pd.Timestamp(ctx.ts(night, 0))]
        after22 = night_logs[ts.loc[night_logs.index].dt.hour >= 22]
        assert {"KYC_EDIT", "LIMIT_INCREASE"} <= set(after22["action"]), \
            "S5 night KYC_EDIT/LIMIT_INCREASE missing in 22:00-24:00"
        lim = after22[after22["action"] == "LIMIT_INCREASE"].iloc[0]
        assert bool(lim["role_violation"]), "S5 LIMIT_INCREASE must be flagged role_violation"
        assert bool(after22["off_hours"].all()), "S5 night logs must be off_hours"
        tx = frames["transactions"]
        cyc = find_cycles(tx, {d, pq, qr})
        assert len(cyc) == 1 and retention(tx, cyc[0]) >= 0.75, "S5 clean cycle broken"
        leg = tx[tx["txn_id"] == leg1].iloc[0]
        assert int(leg["approved_by"]) == emp, "S5 RTGS leg missing insider approval"
        tgt_branch = frames["accounts"].set_index("acc_id").loc[d, "branch"]
        acct_status = frames["accounts"].set_index("acc_id").loc[d, "status"]
        assert tgt_branch != emp_branch, "S5 target must sit outside officer's branch"
        assert acct_status == "ACTIVE", "S5 target stays ACTIVE (dormant rule T5 must not fire)"

    ctx.add_assertion("S5: off-hours edits + role violation + approved-leg cycle + cross-branch; "
                      "target ACTIVE", check)


def inject_s6(ctx: GenCtx) -> None:
    """S6: ~240d-silent dormant account wakes with Rs9.6L in, Rs9.3L out in 3 days."""
    p = ctx.cfg.scenarios.s6
    pre_window_silence = p["dormant_days"] - p["inflow_day"]   # 199d before window
    _, d = ctx.add_dormant(last_active_day_ago=pre_window_silence)
    feeders = [ctx.take_npc_person(), ctx.take_npc_person()]
    sinks = [ctx.take_npc_person(), ctx.take_npc_person(), ctx.take_npc_person()]
    ctx.txn(feeders[0], d, p["inflows"][0], p["inflow_day"], 10.33, "NEFT", "TRANSFER")
    ctx.txn(feeders[1], d, p["inflows"][1], p["inflow_day"], 11.08, "NEFT", "TRANSFER")
    for i, (amt, day) in enumerate(zip(p["out_amounts"], p["out_days"])):
        ctx.txn(d, sinks[i % 3], amt, day, 9.0 + i,
                "IMPS" if i % 2 == 0 else "NEFT", "TRANSFER")

    ctx.gtb.add("S6", "ACCOUNT", d, True)
    ctx.proof(f"S6 dormant acc {d} (silent ~{p['dormant_days']}d at wake): in "
              f"Rs{sum(p['inflows']):,.0f} day {p['inflow_day']}, out "
              f"Rs{sum(p['out_amounts']):,.0f} across days {min(p['out_days'])}-{max(p['out_days'])}")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        acc = frames["accounts"].set_index("acc_id").loc[d]
        assert acc["status"] == "DORMANT", "S6 account must stay marked DORMANT"
        tx = frames["transactions"]
        touched = tx[(tx["from_acc"] == d) | (tx["to_acc"] == d)]
        first_day = (pd.to_datetime(touched["ts"]).min() - pd.Timestamp(ctx.ts(0, 0))).days
        assert first_day >= 35, f"S6 silence broken: first activity day {first_day} < 35"
        in_s = tx[tx["to_acc"] == d]["amount"].sum()
        out_s = tx[tx["from_acc"] == d]["amount"].sum()
        assert float(in_s) == sum(p["inflows"]) and float(out_s) > 900_000, \
            f"S6 volumes wrong: in {in_s:,.0f}, out {out_s:,.0f}"

    ctx.add_assertion("S6: >=35d window silence wake + Rs9.6L in + >Rs9L out in <=3d", check)


def inject_s7(ctx: GenCtx) -> None:
    """S7: Junior Clerk (Rs35k/mo declared) receiving ~Rs28L across 8 credits."""
    p = ctx.cfg.scenarios.s7
    cid, a = ctx.add_person(occupation="Junior Clerk", income=p["income"],
                            kyc="MEDIUM", reserved=True)
    for acc in ctx.accounts:
        if acc["acc_id"] == a:
            acc["type"] = "SALARY"
    totals = 0.0
    for i, day in enumerate(p["days"]):
        amt = float(ctx.rng.uniform(p["credit_lo"], p["credit_hi"]))
        ctx.txn(ctx.take_npc_person(), a, amt, day, 19.0 + i * 0.3, "NEFT", "TRANSFER")
        totals += amt
        ctx.txn(a, ctx.take_npc_person(), round(amt * 0.6, 2), day + 1, 11.0, "IMPS", "TRANSFER")

    ctx.gtb.add("S7", "CUSTOMER", cid, True)
    ctx.gtb.add("S7", "ACCOUNT", a, True)
    ctx.proof(f"S7 cust {cid} 'Junior Clerk' income Rs{p['income']:,.0f}/mo: acc {a} credits "
              f"Rs{totals:,.0f} over {p['credits']} events days {p['days']} "
              f"(~{totals / p['income']:.0f}x monthly income)")

    def check(frames: dict[str, pd.DataFrame]) -> None:
        tx = frames["transactions"]
        ins = float(tx[tx["to_acc"] == a]["amount"].sum())
        outs = float(tx[tx["from_acc"] == a]["amount"].sum())
        volume = ins + outs
        assert ins >= 2_500_000, f"S7 credits {ins:,.0f} < Rs25L"
        ratio = volume / (6 * p["income"])
        assert ratio > 6, f"S7 volume only {ratio:.1f}x the 6x-income guard"

    ctx.add_assertion("S7: >=Rs25L credits, total volume >> 6x declared income", check)


def inject_all(ctx: GenCtx) -> None:
    for fn in (inject_s1, inject_s2, inject_s3, inject_s4, inject_s5, inject_s6, inject_s7):
        fn(ctx)
    ctx.proof(f"Suspicious pool complete: {len(ctx.gtb.rows)} ground-truth rows so far (S1-S7)")
