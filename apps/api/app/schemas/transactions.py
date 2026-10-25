"""Transaction DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txn_id: int
    from_acc: int
    to_acc: int
    amount: float
    ts: datetime
    channel: str
    purpose: str | None
    approved_by: int | None

    @field_serializer("ts")
    def _ts_z(self, v: datetime) -> str:
        return v.astimezone().isoformat()


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int
