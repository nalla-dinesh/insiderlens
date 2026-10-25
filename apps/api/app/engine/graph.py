"""GraphBuilder: chunked async SQL -> networkx.DiGraph + pandas frames.

Design (perf notes):
- Edges stream in 10k-row chunks straight into add_edges_from — no ORM objects.
- Structure graph is a *simple* DiGraph (one edge per ordered pair) for SCC /
  cycle search; the pandas frame keeps EVERY parallel leg for chronology and
  retention verification. MultiDiGraph would make nx.simple_cycles explode.
- Money: Decimal -> float at exactly this boundary (P3); amounts < ~₹50L with
  2 decimals sit far inside float64's exact integer range, and rules only
  compare ratios/sums — documented choice.
- Timestamps normalize to tz-aware UTC at the frame boundary (P5).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import networkx as nx
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

CHUNK = 10_000


@dataclass
class EngineFrames:
    tx: pd.DataFrame  # txn_id, from_acc, to_acc, amount, ts(UTC), channel, purpose
    accounts: pd.DataFrame  # acc_id, cust_id, type, branch, status
    customers: pd.DataFrame  # cust_id, declared_income, occupation, phone, address
    # Phase 04 — insider world (optional; empty frames keep txn-only callers working):
    employees: pd.DataFrame = field(default_factory=pd.DataFrame)  # emp_id, name, role, branch, status
    roles: pd.DataFrame = field(default_factory=pd.DataFrame)  # role_name, allowed_actions
    activity: pd.DataFrame = field(default_factory=pd.DataFrame)  # log_id, emp_id, ts, action, ...

    @property
    def window_start(self) -> pd.Timestamp:
        return self.tx["ts"].min()

    @property
    def window_days(self) -> int:
        return max(1, (self.tx["ts"].max() - self.tx["ts"].min()).days + 1)

    def emp_role(self) -> dict[int, str]:
        return dict(zip(self.employees["emp_id"], self.employees["role"], strict=False))

    def emp_branch(self) -> dict[int, str]:
        return dict(zip(self.employees["emp_id"], self.employees["branch"], strict=False))

    def role_perms(self) -> dict[str, set[str]]:
        return {str(r.role_name): set(r.allowed_actions) for r in self.roles.itertuples()}

    def acc_branch(self) -> dict[int, str]:
        return dict(zip(self.accounts["acc_id"], self.accounts["branch"], strict=False))


@dataclass
class BuildStats:
    nodes: int = 0
    edges_total: int = 0
    edges_structural: int = 0
    build_ms: int = 0
    rule_ms: dict[str, int] = field(default_factory=dict)
    rule_hits: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class GraphBuilder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(self) -> tuple[nx.DiGraph, EngineFrames, int]:
        t0 = time.perf_counter()

        rows: list[dict] = []
        offset = 0
        while True:
            result = await self.session.execute(
                text(
                    "SELECT txn_id, from_acc, to_acc, amount, ts, channel, purpose "
                    "FROM transactions ORDER BY txn_id LIMIT :n OFFSET :o"
                ),
                {"n": CHUNK, "o": offset},
            )
            chunk = result.mappings().all()
            rows.extend(dict(r) for r in chunk)
            if len(chunk) < CHUNK:
                break
            offset += CHUNK

        tx = pd.DataFrame(rows)
        tx["amount"] = tx["amount"].astype(float)
        tx["ts"] = pd.to_datetime(tx["ts"], utc=True)
        tx["purpose"] = tx["purpose"].fillna("")

        acc_rows = (
            (await self.session.execute(text("SELECT acc_id, cust_id, type, branch, status FROM accounts")))
            .mappings()
            .all()
        )
        accounts = pd.DataFrame(dict(r) for r in acc_rows)

        cust_rows = (
            (
                await self.session.execute(
                    text("SELECT cust_id, declared_income, occupation, phone, address FROM customers")
                )
            )
            .mappings()
            .all()
        )
        customers = pd.DataFrame(dict(r) for r in cust_rows)
        customers["declared_income"] = customers["declared_income"].astype(float)

        # Phase 04 insider world (small tables — single reads)
        emp_rows = (
            (await self.session.execute(text("SELECT emp_id, name, role, branch, status FROM employees")))
            .mappings()
            .all()
        )
        employees = pd.DataFrame(dict(r) for r in emp_rows)

        role_rows = (
            (await self.session.execute(text("SELECT role_name, allowed_actions FROM roles")))
            .mappings()
            .all()
        )
        roles = pd.DataFrame(dict(r) for r in role_rows)

        # activity_log: ~9k rows here, chunked anyway for scale safety (CHUNK protocol)
        act_rows: list[dict] = []
        offset = 0
        while True:
            result = await self.session.execute(
                text(
                    "SELECT log_id, emp_id, ts, action, target_acc, details "
                    "FROM activity_log ORDER BY log_id LIMIT :n OFFSET :o"
                ),
                {"n": CHUNK, "o": offset},
            )
            chunk = result.mappings().all()
            act_rows.extend(dict(r) for r in chunk)
            if len(chunk) < CHUNK:
                break
            offset += CHUNK
        activity = pd.DataFrame(act_rows)
        if not activity.empty:
            activity["ts"] = pd.to_datetime(activity["ts"], utc=True)

        # structural graph: one edge per ordered pair (weight = leg count)
        pairs = tx.groupby(["from_acc", "to_acc"], sort=False).size()
        g = nx.DiGraph()
        g.add_nodes_from(accounts["acc_id"].tolist())
        g.add_edges_from((int(f), int(t), {"legs": int(n)}) for (f, t), n in pairs.items())

        build_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "graph_build",
            nodes=g.number_of_nodes(),
            edges_structural=g.number_of_edges(),
            legs=len(tx),
            build_ms=build_ms,
        )
        return (
            g,
            EngineFrames(
                tx=tx,
                accounts=accounts,
                customers=customers,
                employees=employees,
                roles=roles,
                activity=activity,
            ),
            build_ms,
        )
