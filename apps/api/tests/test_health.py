"""Phase 00: /health shape + version passthrough.
Phase 02: /health/db does a REAL SELECT 1 (200 when up, honest 503 when down)."""

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from tests.conftest import needs_pg


async def test_health_ok(client):
    settings = get_settings()
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"] == settings.version
    assert body["environment"] == settings.environment
    assert res.headers["x-request-id"]


async def test_health_carries_request_id(client):
    res = await client.get("/health", headers={"x-request-id": "fixed-req-1"})
    assert res.headers["x-request-id"] == "fixed-req-1"


@needs_pg
async def test_health_db_up(client):
    res = await client.get("/health/db")
    assert res.status_code == 200
    body = res.json()
    assert body["database"] == "up"
    assert isinstance(body["latency_ms"], int)


async def test_health_db_down_is_honest_503(app):
    from httpx import ASGITransport, AsyncClient

    dead = create_async_engine(
        "postgresql+asyncpg://insider:insider@127.0.0.1:9/insiderlens_test",
        pool_size=1,
    )
    app.state.engine = dead
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        res = await c.get("/health/db")
    await dead.dispose()
    assert res.status_code == 503
    body = res.json()
    assert body["error"]["code"] == "db_unavailable"
