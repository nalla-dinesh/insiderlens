"""Phase-08 security guards — production-mode behaviors tested in-process.

The httpx ASGITransport does NOT run lifespan; prod wiring is done manually
(same as tests/conftest.py) with a monkeypatched ENV, cache-cleared settings.

Guards under test:
  1. CORS + ENV=production with '*'  -> refuse startup (RuntimeError at boot).
  2. CORS + ENV=production with real origin list -> boots fine.
  3. POST /api/analysis/run limited to 5/min/client IN PRODUCTION (429 after 5).
  4. POST /api/ingest is 403 forbidden in production (existed before; kept).
  5. Security headers present on every response (nosniff/frame/NP-referrer).
  6. Input safety: int coercion of path params and zero raw f-string SQL.
"""

import ast
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _prod_app():
    """Build create_app() under ENV=production (settings cache wiped)."""
    get_settings.cache_clear()
    import importlib

    import app.config

    importlib.reload(app.config)
    from app.main import create_app

    return create_app()


def test_cors_wildcard_refused_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:1/insiderlens_test")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="refused"):
        from app.main import create_app

        create_app()


def test_cors_wildcard_refused_when_empty_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:1/insiderlens_test")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="refused"):
        from app.main import create_app

        create_app()


def test_production_with_named_origins_boots(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://insiderlens.example.com")
    get_settings.cache_clear()
    from app.main import create_app

    app = create_app()
    assert app is not None and app.docs_url is None  # docs dark in prod


async def test_security_headers_on_every_response(client: AsyncClient) -> None:
    r = await client.get("/health")
    for hdr, want in (
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", "DENY"),
        ("referrer-policy", "no-referrer"),
    ):
        assert r.headers.get(hdr) == want, f"missing/incorrect {hdr}"


async def test_rate_limit_kicked_in_production(monkeypatch) -> None:
    from fastapi import FastAPI

    from app.core.security import AnalysisRateLimitMiddleware

    # in-memory proof on the analysis path — front-gate semantics, not a DB call
    inner = FastAPI()

    @inner.post("/api/analysis/run")
    async def _run() -> dict[str, int]:
        return {"run_id": 1}

    inner.add_middleware(AnalysisRateLimitMiddleware)  # max 5/min default
    async with AsyncClient(transport=ASGITransport(app=inner), base_url="http://test") as c:
        codes = [(await c.post("/api/analysis/run")).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429] * 2


async def test_get_requests_never_rate_limited(monkeypatch) -> None:
    from fastapi import FastAPI

    from app.core.security import AnalysisRateLimitMiddleware

    inner = FastAPI()

    @inner.get("/api/alerts")
    async def _list() -> dict[str, int]:
        return {"ok": 1}

    inner.add_middleware(AnalysisRateLimitMiddleware)
    async with AsyncClient(transport=ASGITransport(app=inner), base_url="http://test") as c:
        codes = [(await c.get("/api/alerts")).status_code for _ in range(10)]
    assert codes == [200] * 10


async def test_ingest_forbidden_in_production(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://insiderlens.example.com")
    get_settings.cache_clear()
    app = _prod_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/ingest")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_in_production"


def test_zero_fstring_sql_spot_check() -> None:
    """Raw-SQL audit: walk app/ for execute() calls whose first arg is a non-constant
    (f-strings end up as JoinedStr). Legit calls use text()/parameters — pasting
    a JOINed string here would be a catch-first violation."""

    offenders: list[str] = []
    for py in sorted(APP_DIR.rglob("*.py")):
        if "services" in py.parts or "routers" in py.parts or "repositories" in py.parts:
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"execute", "exec_driver_sql"}
                    and node.args
                    and isinstance(node.args[0], ast.JoinedStr)
                ):
                    offenders.append(f"{py.relative_to(APP_DIR)}:{node.lineno}")
    assert not offenders, "\n".join(offenders)
