"""Ego-network endpoint: seeded mini graph, exact node/edge expectations."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.db.session import build_session_factory
from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction
from tests.conftest import needs_pg

pytestmark = needs_pg


def _ts(day: int) -> datetime:
    return datetime(2026, 7, day, 10, 0, tzinfo=UTC)


async def _seed(engine) -> None:
    factory = build_session_factory(engine)
    async with factory.begin() as s:
        for cid in range(1, 5):
            s.add(
                Customer(
                    cust_id=cid,
                    name=f"C{cid}",
                    occupation="T",
                    declared_income=Decimal("50000"),
                    kyc_risk="LOW",
                    phone=f"90000000{cid}0",
                    address="a",
                )
            )
        await s.flush()  # parents before children (no ORM relationships by design)
        s.add_all(
            [
                Account(
                    acc_id=1,
                    cust_id=1,
                    type="SAVINGS",
                    branch="Pune-Main",
                    open_date=date(2020, 1, 1),
                    last_active_date=date(2026, 7, 5),
                    status="ACTIVE",
                ),
                Account(
                    acc_id=2,
                    cust_id=2,
                    type="CURRENT",
                    branch="Nagpur-East",
                    open_date=date(2020, 1, 1),
                    last_active_date=date(2026, 7, 6),
                    status="ACTIVE",
                ),
                Account(
                    acc_id=3,
                    cust_id=3,
                    type="CURRENT",
                    branch="Delhi-CP",
                    open_date=date(2020, 1, 1),
                    last_active_date=date(2026, 7, 8),
                    status="ACTIVE",
                ),
                Account(
                    acc_id=4,
                    cust_id=4,
                    type="SAVINGS",
                    branch="Pune-Main",
                    open_date=date(2019, 1, 1),
                    last_active_date=date(2024, 1, 1),
                    status="DORMANT",
                ),
            ]
        )
        s.add_all(
            [
                Transaction(txn_id=1, from_acc=1, to_acc=2, amount=Decimal("100"), ts=_ts(5), channel="IMPS"),
                Transaction(txn_id=2, from_acc=2, to_acc=3, amount=Decimal("200"), ts=_ts(6), channel="IMPS"),
                Transaction(txn_id=3, from_acc=3, to_acc=1, amount=Decimal("180"), ts=_ts(8), channel="NEFT"),
                Transaction(txn_id=4, from_acc=4, to_acc=2, amount=Decimal("400"), ts=_ts(9), channel="UPI"),
            ]
        )


async def test_ego_depth1(client, engine):
    await _seed(engine)
    res = await client.get("/api/graph/ego/1", params={"depth": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["center"] == 1 and body["depth"] == 1
    assert sorted(n["id"] for n in body["nodes"]) == [1, 2, 3]
    assert len(body["edges"]) == 2  # only edges touching the center (1->2, 3->1)
    assert body["truncated"] is False
    labels = {n["id"]: n for n in body["nodes"]}
    assert labels[1]["group"] == "SAVINGS" and "200" not in labels[1]["label"]


async def test_ego_depth2_adds_next_hop(client, engine):
    await _seed(engine)
    res = await client.get("/api/graph/ego/1", params={"depth": 2})
    assert res.status_code == 200
    body = res.json()
    assert sorted(n["id"] for n in body["nodes"]) == [1, 2, 3, 4]
    assert len(body["edges"]) == 4
    dormant = next(n for n in body["nodes"] if n["id"] == 4)
    assert dormant["risk_hint"] == "DORMANT"


async def test_ego_unknown_account_404(client, engine):
    await _seed(engine)
    res = await client.get("/api/graph/ego/999999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "account_not_found"
