"""Graph DTOs — ego network response consumed by the Phase 05 frontend."""

from datetime import datetime

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: int
    label: str  # "200053 · CURRENT"
    group: str  # account type (SAVINGS/CURRENT/MERCHANT/...)
    risk_hint: str | None = None  # data-level hints only ("DORMANT") — NO rule output here


class GraphEdge(BaseModel):
    source: int
    target: int
    amount: float
    ts: datetime
    txn_id: int


class EgoGraphResponse(BaseModel):
    center: int
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool  # True when the node/edge cap kicked in
