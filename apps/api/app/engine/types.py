"""Engine contracts — pydantic models every rule returns."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RuleId = Literal["T1", "T2", "T3", "T4", "T5", "T6", "E1", "E2", "E3", "E4", "E5", "F1", "F2", "F3"]


class LegEvidence(BaseModel):
    """One concrete money movement cited by a rule."""

    txn_id: int
    from_acc: int
    to_acc: int
    amount: float
    ts: datetime
    channel: str = ""
    purpose: str | None = None


class RuleHit(BaseModel):
    """A single rule firing on a set of entities, WITH its receipts.

    Frozen on purpose: downstream (scoring/fusion/persistence) treats hits as
    immutable fact rows — nobody hand-edits a hit after it fired."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    rule_id: RuleId
    entity_ids: list[int] = Field(min_length=1)
    base_points: int  # from scoring.base_points — never recomputed here
    title: str
    summary: str  # one sentence, numbers included
    evidence: dict = Field(min_length=1)  # rule-specific contract (never {})
    first_ts: datetime | None = None  # hit's own window start (merger/fusion glue)
    last_ts: datetime | None = None  # hit's own window end
