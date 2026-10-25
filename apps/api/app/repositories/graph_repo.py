"""Ego-network SQL for GET /api/graph/ego/{acc_id}.

Depth 1: direct counterparties. Depth 2: counterparties of counterparties.
Node metadata comes from accounts (label/group/risk_hint = data hints only —
rule output NEVER leaks into generic graph endpoints; that separation is what
keeps /api/graph safe to show before the scoring phase exists).
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction

MAX_NODES = 250
MAX_EDGES = 600


async def ego_graph(
    session: AsyncSession, acc_id: int, depth: int
) -> tuple[list[Account], list[Transaction], bool]:
    depth1_scope = or_(Transaction.from_acc == acc_id, Transaction.to_acc == acc_id)
    edges1 = (
        (
            await session.execute(
                select(Transaction).where(depth1_scope).order_by(Transaction.ts).limit(MAX_EDGES)
            )
        )
        .scalars()
        .all()
    )

    node_ids: set[int] = {acc_id}
    edge_rows: dict[int, Transaction] = {t.txn_id: t for t in edges1}
    for t in edges1:
        node_ids.update((t.from_acc, t.to_acc))

    frontier = node_ids - {acc_id}
    if depth == 2 and frontier:
        depth2_scope = or_(Transaction.from_acc.in_(frontier), Transaction.to_acc.in_(frontier))
        edges2 = (
            (
                await session.execute(
                    select(Transaction).where(depth2_scope).order_by(Transaction.ts).limit(MAX_EDGES)
                )
            )
            .scalars()
            .all()
        )
        for t in edges2:
            if len(node_ids) >= MAX_NODES:
                break
            edge_rows.setdefault(t.txn_id, t)
            node_ids.update((t.from_acc, t.to_acc))

    truncated = len(node_ids) >= MAX_NODES or len(edge_rows) >= MAX_EDGES
    nodes = (
        (await session.execute(select(Account).where(Account.acc_id.in_(node_ids)).order_by(Account.acc_id)))
        .scalars()
        .all()
    )
    edges = sorted(edge_rows.values(), key=lambda t: (t.ts, t.txn_id))
    return list(nodes), edges, truncated
