"""Small graph helpers used by scenario ASSERTIONS (not by the detection engine —
Phase 03 implements its own fast versions). Brute-force is fine: these run only on
the tiny induced subgraphs of one scenario (≤ 10 accounts)."""

from __future__ import annotations

import pandas as pd


def induced_edges(tx: pd.DataFrame, accounts: set[int]) -> pd.DataFrame:
    m = tx["from_acc"].isin(accounts) & tx["to_acc"].isin(accounts)
    return tx.loc[m].sort_values("ts")


def find_cycles(tx: pd.DataFrame, accounts: set[int], max_len: int = 6) -> list[list[int]]:
    """All simple directed cycles within the induced subgraph (node lists, start=min id)."""
    adj: dict[int, list[int]] = {a: [] for a in accounts}
    for f, t in zip(tx["from_acc"], tx["to_acc"]):
        if f in accounts and t in accounts and f != t:
            adj[f].append(t)
    cycles: set[tuple[int, ...]] = set()
    for start in accounts:
        stack: list[tuple[int, list[int]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            if len(path) > max_len:
                continue
            for nxt in adj.get(node, []):
                if nxt == start and len(path) >= 2:
                    cyc = path[:]
                    k = cyc.index(min(cyc))
                    cycles.add(tuple(cyc[k:] + cyc[:k]))
                elif nxt not in path:
                    stack.append((nxt, path + [nxt]))
    return [list(c) for c in cycles]


def chronology_and_span_days(tx: pd.DataFrame, ordered_accounts: list[int]) -> tuple[bool, float]:
    """For a candidate ordered cycle A->B->C->A: all legs exist, ts strictly increases
    around the ring, and (last - first) span in days."""
    legs = []
    n = len(ordered_accounts)
    for i in range(n):
        f, t = ordered_accounts[i], ordered_accounts[(i + 1) % n]
        hit = tx[(tx["from_acc"] == f) & (tx["to_acc"] == t)]
        if hit.empty:
            return False, -1.0
        legs.append(hit.sort_values("ts").iloc[-1])   # latest leg between the pair
    times = [l["ts"] for l in legs]
    strictly_increasing = all(times[i] < times[i + 1] for i in range(n - 1))
    span = (times[-1] - times[0]).total_seconds() / 86400.0
    return strictly_increasing, span


def retention(tx: pd.DataFrame, ordered_accounts: list[int]) -> float:
    amounts = []
    n = len(ordered_accounts)
    for i in range(n):
        f, t = ordered_accounts[i], ordered_accounts[(i + 1) % n]
        amounts.append(float(tx[(tx["from_acc"] == f) & (tx["to_acc"] == t)]["amount"].max()))
    return amounts[-1] / amounts[0]


def forward_occurrences(tx: pd.DataFrame, account: int, ratio: float, window_h: int) -> int:
    """Count separate inflow events followed by an outflow >= ratio*inflow within window_h."""
    ins = tx[tx["to_acc"] == account].sort_values("ts")
    outs = tx[tx["from_acc"] == account].sort_values("ts")
    count = 0
    for _, r in ins.iterrows():
        w = outs[(outs["ts"] > r["ts"]) & (outs["ts"] <= r["ts"] + pd.Timedelta(hours=window_h))]
        if len(w) and float(w["amount"].sum()) >= ratio * float(r["amount"]):
            count += 1
    return count
