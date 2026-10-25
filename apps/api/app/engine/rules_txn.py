"""T1-T6 transaction rules — pure functions over (graph, frames, cfg) -> RuleHit.

Every rule:
  - reads thresholds ONLY from RulesConfig (law),
  - normalizes time to UTC frames (P5),
  - returns evidence per the Section-3 contract,
  - never touches ground truth (law).
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from app.engine.graph import EngineFrames
from app.engine.guards import exempt_leg_count, t2_bands_active
from app.engine.types import LegEvidence, RuleHit
from app.services.rules_config import RulesConfig

DAY = pd.Timedelta(days=1)


def _legs(df: pd.DataFrame) -> list[LegEvidence]:
    return [
        LegEvidence(
            txn_id=int(r.txn_id),
            from_acc=int(r.from_acc),
            to_acc=int(r.to_acc),
            amount=float(r.amount),
            ts=r.ts.to_pydatetime(),
            channel=str(r.channel),
            purpose=str(r.purpose) or None,
        )
        for r in df.itertuples()
    ]


def _hit(
    cfg: RulesConfig,
    rid: str,
    entity_ids: list[int],
    title: str,
    summary: str,
    evidence: dict,
    span: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> RuleHit:
    return RuleHit(
        rule_id=rid,  # type: ignore[arg-type]
        entity_ids=sorted(set(int(e) for e in entity_ids)),
        base_points=cfg.scoring.base_points[rid],
        title=title,
        summary=summary,
        evidence=evidence,
        first_ts=pd.Timestamp(span[0]).to_pydatetime() if span else None,
        last_ts=pd.Timestamp(span[1]).to_pydatetime() if span else None,
    )


# ----------------------------------------------------------------------------- T1
def _chrono_legs(w: pd.DataFrame, cyc: list[int]) -> list[LegEvidence] | None:
    """Walk the cycle nodes in path order; for each consecutive pair pick the
    earliest unused leg strictly AFTER the previous leg's ts. Try every rotation —
    a cycle has no privileged start. Returns None if no chronological walk exists."""
    n = len(cyc)
    for rot in range(n):
        order = [cyc[(rot + i) % n] for i in range(n)]
        legs: list[LegEvidence] = []
        prev_ts: pd.Timestamp | None = None
        ok = True
        for i in range(n):
            f, t = order[i], order[(i + 1) % n]
            cand = w[(w["from_acc"] == f) & (w["to_acc"] == t)].sort_values("ts")
            if prev_ts is not None:
                cand = cand[cand["ts"] > prev_ts]
            if cand.empty:
                ok = False
                break
            leg = _legs(cand.head(1))[0]
            legs.append(leg)
            prev_ts = cand.iloc[0]["ts"]
        if ok:
            return legs
    return None


def t1_circular(g: nx.DiGraph, frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T1: chronological directed 3-6 hop cycle within window_days, retention >= floor.

    Perf law (P1): never enumerate cycles on the full graph.
    Prune order: (1) legs >= min_leg_amount, (2) SCCs >= min_len, (3) sliding
    day windows of window_days, (4) simple_cycles length_bound=max_len, then
    (5) chronology + retention verified from the parallel-leg frame.
    """
    p = cfg.thresholds.t1_circular
    tx = frames.tx
    if p.min_leg_amount:
        tx = tx[tx["amount"] >= p.min_leg_amount]
    if tx.empty:
        return []

    pairs = tx.groupby(["from_acc", "to_acc"], sort=False).size()
    h = nx.DiGraph()
    h.add_edges_from((int(f), int(t)) for (f, t) in pairs.index)

    hits: dict[tuple[int, ...], RuleHit] = {}
    t0 = frames.tx["ts"].min().normalize()
    n_days = max(1, (frames.tx["ts"].max().normalize() - t0).days + 1)

    for scc in nx.strongly_connected_components(h):
        if len(scc) < p.min_len:
            continue
        sub = tx[tx["from_acc"].isin(scc) & tx["to_acc"].isin(scc)]
        if len(sub) < p.min_len:
            continue
        for d in range(n_days):
            lo = t0 + d * DAY
            hi = lo + p.window_days * DAY
            w = sub[(sub["ts"] >= lo) & (sub["ts"] < hi)]
            if len(w) < p.min_len:
                continue
            wg = nx.DiGraph()
            wg.add_edges_from(w.groupby(["from_acc", "to_acc"], sort=False).size().index)
            for cyc in nx.simple_cycles(wg, length_bound=p.max_len):
                if len(cyc) < p.min_len:
                    continue
                key = tuple(sorted(cyc))
                if key in hits:
                    continue
                legs = _chrono_legs(w, cyc)
                if legs is None:
                    continue
                retention = legs[-1].amount / legs[0].amount
                if retention < p.min_retention:
                    continue
                if exempt_leg_count(legs, cfg) >= 2:
                    continue  # vendor-triangle veto (L2)
                span = (legs[-1].ts - legs[0].ts).total_seconds() / 86400
                total = sum(leg.amount for leg in legs)
                hits[key] = _hit(
                    cfg,
                    "T1",
                    list(cyc),
                    "Circular funds flow",
                    f"{len(cyc)}-hop cycle routed Rs{total:,.0f} in {span:.1f}d "
                    f"with {retention:.0%} of the seed retained.",
                    {
                        "legs": [leg.model_dump() for leg in legs],
                        "total_routed": round(total, 2),
                        "retention": round(retention, 4),
                        "window_days_actual": round(span, 2),
                        "window_days_limit": p.window_days,
                        "min_retention": p.min_retention,
                        "records": {"txn_ids": [leg.txn_id for leg in legs]},
                        "gates": [
                            {
                                "key": "t1_circular.min_retention",
                                "observed": round(retention, 4),
                                "limit": p.min_retention,
                                "source": "rules.yaml",
                            },
                            {
                                "key": "t1_circular.window_days",
                                "observed": round(span, 2),
                                "limit": p.window_days,
                                "source": "rules.yaml",
                            },
                        ],
                    },
                    (legs[0].ts, legs[-1].ts),
                )
    return list(hits.values())


# ----------------------------------------------------------------------------- T2
def _best_window(sub: pd.DataFrame, window: pd.Timedelta, min_count: int):
    """Two-pointer densest window; returns (rows_df, count) or None."""
    ts = sub["ts"].sort_values()
    arr = ts.to_numpy()
    best_i, best_j = 0, 0
    for i in range(len(arr)):
        j = np.searchsorted(arr, arr[i] + window.to_timedelta64(), side="right")
        if j - i > best_j - best_i:
            best_i, best_j = i, j
    if best_j - best_i < min_count:
        return None
    sel = sub[sub["ts"].between(ts.iloc[best_i], ts.iloc[best_i] + window)]
    return sel, len(sel)


def t2_structuring(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T2: >= min_count sub-threshold txns within window_days — sender-level
    (hub-facing set, spec alternate clause) and pair-level."""
    p = cfg.thresholds.t2_structuring
    bands = t2_bands_active(cfg)
    exempt = cfg.legitimacy_guards.exempt_purposes
    tx = frames.tx[~frames.tx["purpose"].isin(exempt)]
    in_band = pd.Series(False, index=tx.index)
    for lo, hi in bands:
        in_band |= tx["amount"].between(lo, hi, inclusive="left")
    tx = tx[in_band]
    if tx.empty:
        return []

    hits: list[RuleHit] = []
    window = pd.Timedelta(days=p.window_days)
    seen: set[tuple] = set()

    for by, label in [(["from_acc", "to_acc"], "pair"), (["from_acc"], "sender")]:
        for key, sub in tx.groupby(by, sort=False):
            best = _best_window(sub, window, p.min_count)
            if best is None:
                continue
            rows, _count = best
            agg = float(rows["amount"].sum())
            band_hi = bands[0][1] if (rows["amount"] < bands[0][0] + 10_000).all() else bands[-1][1]
            if agg < 2 * band_hi:
                continue  # aggregate must exceed 2x band ceiling
            dedup_key = (label, key if label == "pair" else (key,))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            rows = rows.sort_values("ts")
            dist = (band_hi - rows["amount"]).round(2).tolist()
            bins = (
                pd.cut(rows["amount"], bins=range(0, int(band_hi) + 20_000, 20_000))
                .value_counts()
                .sort_index()
            )
            hist = {str(k): int(v) for k, v in bins.items() if v}
            senders = sorted(rows["from_acc"].unique().tolist())
            receivers = sorted(rows["to_acc"].unique().tolist())[:10]
            hits.append(
                _hit(
                    cfg,
                    "T2",
                    senders + receivers,
                    "Structuring / smurfing pattern",
                    f"{len(rows)} txns in {p.window_days}d sit Rs{int(min(dist)):,}-"
                    f"Rs{int(max(dist)):,} under the review band; aggregate Rs{agg:,.0f} "
                    f">= 2x band ceiling Rs{2 * band_hi:,.0f}.",
                    {
                        "txn_ids": rows["txn_id"].astype(int).tolist(),
                        "amounts": rows["amount"].tolist(),
                        "distance_to_band_ceiling": dist,
                        "histogram_20k_bins": hist,
                        "aggregate": round(agg, 2),
                        "band_ceiling": band_hi,
                        "aggregate_vs_2x_ceiling": round(agg / (2 * band_hi), 3),
                        "window_days": p.window_days,
                        "mode": label,
                        "records": {"txn_ids": rows["txn_id"].astype(int).tolist()},
                        "gates": [
                            {
                                "key": "t2_structuring.min_count",
                                "observed": len(rows),
                                "limit": p.min_count,
                                "source": "rules.yaml",
                            },
                            {
                                "key": "t2_structuring.aggregate_vs_2x_ceiling",
                                "observed": round(agg / (2 * band_hi), 3),
                                "limit": 1.0,
                                "source": "rules.yaml",
                            },
                        ],
                    },
                    (rows["ts"].min(), rows["ts"].max()),
                )
            )
    return hits


# ----------------------------------------------------------------------------- T3
def t3_fanin(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T3: hub in-degree >= min_in_degree within window_days of near-band chunks
    (leg_min_amount floor + exempt-purpose exclusion — L5 payroll fan-in dies
    here legitimately), >= sub_threshold_fraction below review_band, then a bulk
    outflow >= bulk_out_multiple x median within bulk_window_hours.

    Perf: numpy two-pointer window scan; pandas slices ONLY for the one
    canonical (earliest fully-valid) window per hub.
    """
    p = cfg.thresholds.t3_fanin
    review = cfg.thresholds.review_band
    exempt = cfg.legitimacy_guards.exempt_purposes
    amin = float(p.leg_min_amount or 0.0)
    tx = frames.tx
    window_ns = int(p.window_days * 86_400_000_000_000)  # datetime64 ns
    bulk_ns = int(p.bulk_window_hours * 3_600_000_000_000)
    hits: list[RuleHit] = []

    phone_by_cust = dict(zip(frames.customers["cust_id"], frames.customers["phone"], strict=False))
    cust_by_acc = dict(zip(frames.accounts["acc_id"], frames.accounts["cust_id"], strict=False))

    ins_src = tx[~tx["purpose"].isin(exempt)]
    if amin:
        ins_src = ins_src[ins_src["amount"] >= amin]

    outs_arrays: dict[int, tuple] = {}
    for frm, g_out in tx.groupby("from_acc", sort=False):
        g_out = g_out.sort_values("ts")
        outs_arrays[int(frm)] = (
            g_out["ts"].to_numpy(dtype="datetime64[ns]"),
            g_out["amount"].to_numpy(float),
            g_out.index.to_numpy(),
        )

    for hub, inbound in ins_src.groupby("to_acc", sort=False):
        inbound = inbound.sort_values("ts")
        if len(inbound) < p.min_in_degree:
            continue
        arr_ts = inbound["ts"].to_numpy(dtype="datetime64[ns]")
        arr_src = inbound["from_acc"].to_numpy(np.int64)
        arr_amt = inbound["amount"].to_numpy(float)
        idx = inbound.index.to_numpy()
        outs = outs_arrays.get(int(hub))
        if outs is None:
            continue
        out_ts, out_amt, out_idx = outs

        chosen: tuple[int, int] | None = None  # (i, j) of canonical window
        for i in range(len(arr_ts) - p.min_in_degree + 1):
            j = int(np.searchsorted(arr_ts, arr_ts[i] + np.timedelta64(window_ns, "ns"), side="right"))
            if j - i < p.min_in_degree:
                continue
            if np.unique(arr_src[i:j]).size < p.min_in_degree:
                continue
            w_amt = arr_amt[i:j]
            if float((w_amt < review).mean()) < p.sub_threshold_fraction:
                continue
            med = float(np.median(w_amt))
            w_end = arr_ts[i] + np.timedelta64(window_ns, "ns")
            lo = int(np.searchsorted(out_ts, w_end, side="right"))
            hi = int(np.searchsorted(out_ts, w_end + np.timedelta64(bulk_ns, "ns"), side="right"))
            if hi > lo and float(out_amt[lo:hi].max()) >= p.bulk_out_multiple * med:
                chosen = (i, j)
                break  # earliest fully-valid window
        if chosen is None:
            continue

        i, j = chosen
        w = tx.loc[idx[i:j]]
        med = float(w["amount"].median())
        w_end = w["ts"].min() + pd.Timedelta(days=p.window_days)
        bulk = tx[tx["from_acc"] == hub]
        bulk = (
            bulk[
                (bulk["ts"] > w_end)
                & (bulk["ts"] <= w_end + pd.Timedelta(hours=p.bulk_window_hours))
                & (bulk["amount"] >= p.bulk_out_multiple * med)
            ]
            .sort_values("ts")
            .head(1)
        )
        senders = sorted(int(s) for s in w["from_acc"].unique())
        phones = [phone_by_cust.get(cust_by_acc.get(s, -1), "") for s in senders]
        legs = _legs(w) + _legs(bulk)
        hits.append(
            _hit(
                cfg,
                "T3",
                [int(hub), *senders],
                "Smurfing fan-in with bulk out",
                f"Account {int(hub)} consolidated {w['from_acc'].nunique()} senders' "
                f"Rs{float(w['amount'].sum()):,.0f} in {p.window_days}d "
                f"(median leg Rs{med:,.0f}), then fired Rs{float(bulk['amount'].iloc[0]):,.0f} "
                f"out within {p.bulk_window_hours}h.",
                {
                    "hub": int(hub),
                    "senders": senders,
                    "shared_phone_cluster": len(set(phones)) < len(phones),
                    "in_txn_ids": w["txn_id"].astype(int).tolist(),
                    "leg_min_amount": amin,
                    "exempt_purposes_excluded": len(exempt),
                    "bulk_out": _legs(bulk)[0].model_dump(),
                    "median_leg": med,
                    "bulk_multiple_vs_median": round(float(bulk["amount"].iloc[0]) / med, 2),
                    "timeline": {
                        "first_deposit": w["ts"].min().isoformat(),
                        "last_deposit": w["ts"].max().isoformat(),
                        "bulk_out": bulk["ts"].iloc[0].isoformat(),
                    },
                    "legs": [leg.model_dump() for leg in legs],
                    "records": {"txn_ids": [leg.txn_id for leg in legs]},
                    "gates": [
                        {
                            "key": "t3_fanin.min_in_degree",
                            "observed": int(w["from_acc"].nunique()),
                            "limit": p.min_in_degree,
                            "source": "rules.yaml",
                        },
                        {
                            "key": "t3_fanin.bulk_out_multiple",
                            "observed": round(float(bulk["amount"].iloc[0]) / med, 2),
                            "limit": p.bulk_out_multiple,
                            "source": "rules.yaml",
                        },
                    ],
                },
                (w["ts"].min(), bulk["ts"].iloc[0]),
            )
        )
    return hits


# ----------------------------------------------------------------------------- T4
def t4_passthrough(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T4: a single dominant outflow forwards >= forward_ratio of an inflow
    within window_hours, on >= min_occurrences occasions, and the account keeps
    < max_kept_fraction of total inflows overall.

    NOTE on occurrence semantics: a corridor mule pushes ONE ~same-size transfer
    shortly after each inflow — so each inflow is "forwarded" only if a single
    dominant out (>= ratio x inflow) lands inside the window. Cumulative-sum
    matching was tried in phase-03 calibration and drowned in background churn
    (371 false hits); dominant-out keeps the corridor and kills the noise.
    """
    p = cfg.thresholds.t4_passthrough
    tx = frames.tx
    window_ns = int(p.window_hours * 3_600_000_000_000)
    hits: list[RuleHit] = []

    outs_by_from: dict[int, tuple] = {}
    for frm, g_out in tx.groupby("from_acc", sort=False):
        g_out = g_out.sort_values("ts")
        outs_by_from[int(frm)] = (
            g_out["ts"].to_numpy(dtype="datetime64[ns]"),
            g_out["amount"].to_numpy(float),
            g_out["txn_id"].to_numpy(np.int64),
            g_out["to_acc"].to_numpy(np.int64),
        )

    for to_acc, ins in tx.groupby("to_acc", sort=False):
        outs = outs_by_from.get(int(to_acc))
        if outs is None or len(ins) < p.min_occurrences:
            continue
        out_ts, out_amt, out_ids, out_to = outs
        ins = ins.sort_values("ts")
        ins_ts = ins["ts"].to_numpy(dtype="datetime64[ns]")
        ins_amt = ins["amount"].to_numpy(float)
        ins_ids = ins["txn_id"].to_numpy(np.int64)

        occ: list[dict] = []
        for i in range(len(ins)):
            a = int(np.searchsorted(out_ts, ins_ts[i], side="right"))
            b = int(np.searchsorted(out_ts, ins_ts[i] + np.timedelta64(window_ns, "ns"), side="right"))
            if b <= a:
                continue
            w_amt = out_amt[a:b]
            k = int(w_amt.argmax()) + a
            if out_amt[k] < p.forward_ratio * ins_amt[i]:
                continue
            occ.append(
                {
                    "inflow_txn": int(ins_ids[i]),
                    "inflow_amount": round(float(ins_amt[i]), 2),
                    "inflow_ts": pd.Timestamp(ins_ts[i]).isoformat(),
                    "matched_out_txn": int(out_ids[k]),
                    "matched_out_amount": round(float(out_amt[k]), 2),
                    "matched_out_to": int(out_to[k]),
                    "fraction": round(float(out_amt[k]) / float(ins_amt[i]), 4),
                    "within_hours": round(float((out_ts[k] - ins_ts[i]) / np.timedelta64(1, "h")), 2),
                }
            )
        if len(occ) < p.min_occurrences:
            continue
        in_total, out_total = float(ins["amount"].sum()), float(out_amt.sum())
        kept = 1 - out_total / in_total if in_total else 1.0
        if kept >= p.max_kept_fraction:
            continue
        fracs = np.array([o["fraction"] for o in occ])
        frac_std = float(fracs.std())
        if frac_std > p.max_fraction_std:
            continue  # chaotic amounts = churn, not corridor
        cp_share = float(pd.Series([o["matched_out_to"] for o in occ]).value_counts(normalize=True).iloc[0])
        if cp_share < p.min_route_share:
            continue  # fanned-out forwards = not a corridor
        median_hours = round(float(np.median([o["within_hours"] for o in occ])), 2)
        hits.append(
            _hit(
                cfg,
                "T4",
                [int(to_acc)],
                "Rapid pass-through (layering mule)",
                f"Account forwarded ~{p.forward_ratio:.0%} of inflows within "
                f"{p.window_hours}h on {len(occ)} occasions (discipline std "
                f"{frac_std:.3f}), retaining only {max(kept, 0.0):.1%}.",
                {
                    "occurrences": len(occ),
                    "occurrences_detail": occ[:20],
                    "median_hours": median_hours,
                    "forward_ratio": p.forward_ratio,
                    "window_hours": p.window_hours,
                    "in_total": round(in_total, 2),
                    "out_total": round(out_total, 2),
                    "keep_fraction": round(max(kept, 0.0), 4),
                    "max_kept_fraction": p.max_kept_fraction,
                    "fraction_std": round(frac_std, 4),
                    "max_fraction_std": p.max_fraction_std,
                    "route_share_dominant_next_hop": round(cp_share, 4),
                    "min_route_share": p.min_route_share,
                    "records": {
                        "txn_ids": sorted(
                            {o["inflow_txn"] for o in occ} | {o["matched_out_txn"] for o in occ}
                        )
                    },
                    "gates": [
                        {
                            "key": "t4_passthrough.min_occurrences",
                            "observed": len(occ),
                            "limit": p.min_occurrences,
                            "source": "rules.yaml",
                        },
                        {
                            "key": "t4_passthrough.max_fraction_std",
                            "observed": round(frac_std, 4),
                            "limit": p.max_fraction_std,
                            "source": "rules.yaml",
                        },
                        {
                            "key": "t4_passthrough.min_route_share",
                            "observed": round(cp_share, 4),
                            "limit": p.min_route_share,
                            "source": "rules.yaml",
                        },
                    ],
                },
                (pd.Timestamp(occ[0]["inflow_ts"]), pd.Timestamp(occ[-1]["inflow_ts"])),
            )
        )
    return hits


# ----------------------------------------------------------------------------- T5
def t5_dormant(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T5: dormancy + reactivation burst.

    Two honest paths (60-day snapshot caveat, documented in rules.yaml):
      (a) the bank marker path: accounts.status == 'DORMANT' AND silent for
          >= window_silence_days after window start, then burst;
      (b) the history path: >= dormant_days between consecutive txns, then burst.
    """
    p = cfg.thresholds.t5_dormant
    tx = frames.tx
    acc_status = dict(zip(frames.accounts["acc_id"], frames.accounts["status"], strict=False))
    w_start = tx["ts"].min()
    burst_within = pd.Timedelta(hours=p.burst_window_hours)
    hits: list[RuleHit] = []

    ins_by_to = {k: v.sort_values("ts") for k, v in tx.groupby("to_acc", sort=False)}
    outs_by_from = {k: v.sort_values("ts") for k, v in tx.groupby("from_acc", sort=False)}
    activity: dict[int, pd.Series] = {}
    for acc, outs in outs_by_from.items():
        ins = ins_by_to.get(acc)
        all_ts = outs["ts"] if ins is None else pd.concat([outs["ts"], ins["ts"]]).sort_values()
        activity[acc] = all_ts

    for acc, ts_series in activity.items():
        ts_list = list(ts_series)
        first = ts_list[0]
        dormant_path = None
        if acc_status.get(acc) == "DORMANT" and (first - w_start).days >= p.window_silence_days:
            dormant_path = ("bank_marker", int((first - w_start).days))
        else:
            gaps = [(ts_list[i + 1] - ts_list[i]).days for i in range(len(ts_list) - 1)]
            if gaps and max(gaps) >= p.dormant_days:
                idx = gaps.index(max(gaps)) + 1
                dormant_path = ("history_gap", int(max(gaps)))
                first = ts_list[idx]
        if dormant_path is None:
            continue
        outs = outs_by_from.get(acc)
        if outs is None:
            continue
        burst = outs[(outs["ts"] >= first) & (outs["ts"] <= first + burst_within)]
        burst_total = float(burst["amount"].sum())
        if burst_total <= p.burst_amount:
            continue
        hits.append(
            _hit(
                cfg,
                "T5",
                [int(acc)],
                "Dormant account reactivation burst",
                f"Account silent ~{dormant_path[1]}d then burst Rs{burst_total:,.0f} "
                f"within {p.burst_window_hours}h of reactivation.",
                {
                    "dormancy_evidence": dormant_path[0],
                    "silence_days_before_wake": dormant_path[1],
                    "dormant_days_threshold": p.dormant_days,
                    "reactivation_txn": int(burst["txn_id"].iloc[0]),
                    "reactivation_ts": first.isoformat(),
                    "burst_txn_ids": burst["txn_id"].astype(int).tolist(),
                    "burst_total": round(burst_total, 2),
                    "burst_amount_threshold": p.burst_amount,
                    "records": {"txn_ids": burst["txn_id"].astype(int).tolist()},
                    "gates": [
                        {
                            "key": "t5_dormant.window_silence_days"
                            if dormant_path[0] == "bank_marker"
                            else "t5_dormant.dormant_days",
                            "observed": dormant_path[1],
                            "limit": p.window_silence_days
                            if dormant_path[0] == "bank_marker"
                            else p.dormant_days,
                            "source": "rules.yaml",
                        },
                        {
                            "key": "t5_dormant.burst_amount",
                            "observed": round(burst_total, 2),
                            "limit": p.burst_amount,
                            "source": "rules.yaml",
                        },
                    ],
                },
                (first, burst["ts"].max()),
            )
        )
    return hits


# ----------------------------------------------------------------------------- T6
def t6_profile(frames: EngineFrames, cfg: RulesConfig) -> list[RuleHit]:
    """T6: per CUSTOMER (across personal accounts) monthly NON-exempt volume
    > multiple x declared income, sustained across >= min_months calendar months.
    Personal accounts (SAVINGS/SALARY) only; businesses are volume-driven by nature.

    Calibration note (phase-03): background churn in realistic 60-day snapshots
    spikes single months to ~20x incomes for ordinary customers; laundering
    leaves a sustained 50x+ trail. multiple=25 + min_months=2 separates them on
    this bundle (documented in rules.yaml)."""
    p = cfg.thresholds.t6_profile
    exempt = cfg.legitimacy_guards.exempt_purposes
    tx = frames.tx[~frames.tx["purpose"].isin(exempt)]

    personal = frames.accounts[frames.accounts["type"].isin(["SAVINGS", "SALARY"])]
    acc2cust = dict(zip(personal["acc_id"], personal["cust_id"], strict=False))
    rel = tx[tx["to_acc"].isin(acc2cust) | tx["from_acc"].isin(acc2cust)].copy()
    if rel.empty:
        return []
    info = frames.customers.set_index("cust_id")

    side_in = rel[rel["to_acc"].isin(acc2cust)]
    side_in = side_in.assign(cust=side_in["to_acc"].map(acc2cust))
    side_out = rel[rel["from_acc"].isin(acc2cust)]
    side_out = side_out.assign(cust=side_out["from_acc"].map(acc2cust))
    long = pd.concat(
        [
            side_in[["cust", "amount", "ts", "txn_id"]],
            side_out[["cust", "amount", "ts", "txn_id"]],
        ]
    )
    long["month"] = long["ts"].dt.tz_convert(None).dt.to_period("M")
    grp = long.groupby(["cust", "month"])["amount"].agg(["sum", "count"])

    # persistence gate: how many months did this customer exceed the multiple?
    over: dict[int, list] = {}
    for (cust, month), row in grp.iterrows():
        cust = int(cust)
        income = float(info.loc[cust, "declared_income"]) if cust in info.index else 0.0
        if income < p.min_income_floor:
            continue
        if float(row["sum"]) > p.multiple * income:
            over.setdefault(cust, []).append((month, float(row["sum"]), int(row["count"]), income))

    hits: list[RuleHit] = []
    for cust, rows in over.items():
        if len(rows) < p.min_months:
            continue
        months_over = sorted(str(r[0]) for r in rows)
        for month, volume, n_legs, income in rows:
            accs = sorted(
                frames.accounts[
                    (frames.accounts["cust_id"] == cust)
                    & (frames.accounts["type"].isin(["SAVINGS", "SALARY"]))
                ]["acc_id"].tolist()
            )
            ratio = volume / income
            hits.append(
                _hit(
                    cfg,
                    "T6",
                    [cust],
                    "Declared-income profile mismatch",
                    f"Customer '{info.loc[cust, 'occupation']}' declares Rs{income:,.0f}/mo "
                    f"but moved Rs{volume:,.0f} in {month} ({ratio:.0f}x), for "
                    f"{len(rows)} months straight.",
                    {
                        "cust_id": cust,
                        "acc_ids": accs,
                        "month": str(month),
                        "declared_income": income,
                        "observed_volume": round(volume, 2),
                        "ratio": round(ratio, 2),
                        "multiple_threshold": p.multiple,
                        "months_over_threshold": months_over,
                        "min_months": p.min_months,
                        "nonexempt_leg_count": n_legs,
                        "top_out_txns": (
                            side_out[
                                (side_out["cust"] == cust)
                                & (side_out["ts"].dt.tz_convert(None).dt.to_period("M") == month)
                            ]
                            .nlargest(5, "amount")["txn_id"]
                            .astype(int)
                            .tolist()
                        ),
                        "records": {
                            "txn_ids": (
                                long[(long["cust"] == cust) & (long["month"] == month)]
                                .nlargest(50, "amount")["txn_id"]
                                .astype(int)
                                .tolist()
                            )
                        },
                        "gates": [
                            {
                                "key": "t6_profile.multiple",
                                "observed": round(ratio, 2),
                                "limit": p.multiple,
                                "source": "rules.yaml",
                            },
                            {
                                "key": "t6_profile.min_months",
                                "observed": len(rows),
                                "limit": p.min_months,
                                "source": "rules.yaml",
                            },
                        ],
                    },
                    (
                        month.start_time.tz_localize("UTC"),
                        min(
                            month.end_time.tz_localize("UTC"),
                            long[(long["cust"] == cust) & (long["month"] == month)]["ts"].max(),
                        ),
                    ),
                )
            )
    hits.sort(key=lambda h: (-h.evidence["ratio"], h.evidence["month"]))
    return hits
