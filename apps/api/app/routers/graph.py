"""Ego-network endpoint — SQL-built, deterministic ordering, capped sizes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.repositories import accounts_repo, graph_repo
from app.schemas.graph import EgoGraphResponse, GraphEdge, GraphNode

router = APIRouter(prefix="/api/graph", tags=["graph"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/ego/{acc_id}", response_model=EgoGraphResponse)
async def ego_graph(
    acc_id: int,
    session: DbSession,
    depth: Annotated[int, Query(ge=1, le=2, description="1 = direct neighbors, 2 = two hops")] = 1,
) -> EgoGraphResponse:
    if await accounts_repo.get_account(session, acc_id) is None:
        raise AppError(
            code="account_not_found",
            message=f"Account {acc_id} does not exist.",
            status_code=404,
            details={"acc_id": acc_id},
        )
    nodes, edges, truncated = await graph_repo.ego_graph(session, acc_id, depth)
    return EgoGraphResponse(
        center=acc_id,
        depth=depth,
        nodes=[
            GraphNode(
                id=n.acc_id,
                label=f"{n.acc_id} · {n.type}",
                group=n.type,
                risk_hint="DORMANT" if n.status == "DORMANT" else None,
            )
            for n in nodes
        ],
        edges=[
            GraphEdge(source=e.from_acc, target=e.to_acc, amount=float(e.amount), ts=e.ts, txn_id=e.txn_id)
            for e in edges
        ],
        truncated=truncated,
    )
