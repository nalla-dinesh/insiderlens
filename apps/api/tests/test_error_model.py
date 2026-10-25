"""Uniform JSON error model across: unknown routes, missing entities,
validation failures."""

from tests.conftest import needs_pg


async def test_unknown_route_404_uniform(client):
    res = await client.get("/api/definitely-not-a-route")
    assert res.status_code == 404
    body = res.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)


@needs_pg
async def test_missing_account_404_uniform(client):
    res = await client.get("/api/accounts/99999999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "account_not_found"
    assert res.json()["error"]["details"]["acc_id"] == 99999999


async def test_validation_error_422_uniform(client):
    res = await client.get("/api/accounts/1/transactions", params={"limit": "not-a-number"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
