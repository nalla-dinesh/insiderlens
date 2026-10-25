"""Account DTOs — `from_attributes` lets us return ORM rows directly."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    acc_id: int
    cust_id: int
    type: str
    branch: str
    open_date: date
    last_active_date: date
    status: str


class AccountPage(BaseModel):
    items: list[AccountOut]
    total: int
    limit: int
    offset: int
