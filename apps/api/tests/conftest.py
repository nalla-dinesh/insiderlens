"""Test infrastructure — REAL PostgreSQL, no sqlite shims (P1 law).

The compose Postgres (or any reachable server via TEST_DATABASE_URL) hosts a
dedicated `insiderlens_test` database created by these fixtures. Every test gets a
fresh TRUNCATE — function-level isolation, engine per test (pool binds to the
test's event loop). If no Postgres is reachable, db-marked tests SKIP with an
explicit reason (never fake a pass).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.db.session import build_session_factory

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_YAML = REPO_ROOT / "infra" / "config" / "rules.yaml"
TEST_DB_NAME = "insiderlens_test"


def _test_base_url() -> str:
    """Maintenance URL (db = 'postgres') for the configured server."""
    return get_settings().database_url.rsplit("/", 1)[0] + "/postgres"


def _test_db_url() -> str:
    return get_settings().database_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


async def _bootstrap() -> None:
    admin = create_async_engine(_test_base_url(), execution_options={"isolation_level": "AUTOCOMMIT"})
    async with admin.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME})
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin.dispose()

    import app.models as _models  # noqa: F401  — registers all tables into Base.metadata

    engine = create_async_engine(_test_db_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def _pg_reachable() -> bool:
    try:
        asyncio.run(_bootstrap())
        return True
    except OSError:
        return False


PG_AVAILABLE: bool = _pg_reachable()
needs_pg = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL not reachable (run `make db-up`)")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    """Per-test engine on the test DB + all tables truncated (function loop-safe)."""
    eng = create_async_engine(_test_db_url(), pool_size=3)
    async with eng.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = build_session_factory(engine)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def app(engine):
    from app.main import create_app

    application = create_app()
    # httpx ASGITransport does not run lifespan -> wire state manually
    application.state.engine = engine
    application.state.session_factory = build_session_factory(engine)
    application.state.settings = get_settings()  # Phase-04 routers read rules_config from here
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------- live seeded bundle (S5 showcase tests, Phase 04) ----------------
# Fallback default exists ONLY for the sandbox layout; everywhere else the seeded
# bundle IS the demo DB from DATABASE_URL (or SEEDED_DATABASE_URL override).
SEEDED_DATABASE_URL = "postgresql+asyncpg://insider:insider@127.0.0.1:5432/insiderlens"


@pytest_asyncio.fixture
async def seeded_engine():
    """Connect to the REAL seeded bundle DB if present; otherwise skip loudly
    (never fake the S5 showcase — the whole point is REAL data)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = get_settings()
    url = settings.seed_database_url or settings.database_url
    eng = create_async_engine(url, pool_size=2)
    try:
        async with eng.connect() as conn:
            n = await conn.scalar(text("SELECT count(*) FROM transactions"))
            if not n:
                await eng.dispose()
                pytest.skip("seeded DB reachable but empty — run scripts/ingest.py")
    except Exception as e:  # noqa: BLE001 - skip is honest, silent-pass is not
        await eng.dispose()
        reason = f"seeded DB unusable ({type(e).__name__}: {e})"
        pytest.skip(f"{reason} — check DATABASE_URL / SEEDED_DATABASE_URL")
    yield eng
    await eng.dispose()


# ---------------- mini bundle (tiny but REAL 7-file CSV bundle) ----------------
MINI = {
    "roles": (
        "role_name,allowed_actions,description\n"
        "TELLER,APPROVE_TXN|LOGIN|VIEW_ACCOUNT,front line\n"
        "OFFICER,ADD_BENEFICIARY|APPROVE_TXN|KYC_EDIT|LOGIN|VIEW_ACCOUNT,kyc officer\n"
        "MANAGER,ADD_BENEFICIARY|APPROVE_TXN|BULK_EXPORT|KYC_EDIT|LIMIT_INCREASE|LOGIN|VIEW_ACCOUNT,mgr\n"
        "ADMIN,ADD_BENEFICIARY|APPROVE_TXN|BULK_EXPORT|DISABLE_ALERT|KYC_EDIT|LIMIT_INCREASE|LOGIN|VIEW_ACCOUNT,admin\n"
    ),
    "employees": (
        "emp_id,name,role,branch,join_date,status\n"
        "1001,Test Officer,OFFICER,Nagpur-East,2021-05-01,ACTIVE\n"
        "1002,Test Teller,TELLER,Pune-Main,2022-03-15,ACTIVE\n"
        "1003,Test Admin,ADMIN,Pune-Main,2020-01-10,ACTIVE\n"
    ),
    "customers": (
        "cust_id,name,occupation,declared_income,kyc_risk,phone,address\n"
        '100001,Mini Cust One,Teacher,45000.00,LOW,9811111111,"1, MG Road, Pune"\n'
        '100002,Mini Cust Two,Trader,320000.00,MEDIUM,9822222222,"2, Nehru Marg, Nagpur"\n'
        '100003,Mini Biz Corp,Business Entity,1500000.00,LOW,9833333333,"3, MG Road, Mumbai"\n'
    ),
    "accounts": (
        "acc_id,cust_id,type,branch,open_date,last_active_date,status\n"
        "200001,100001,SAVINGS,Pune-Main,2021-01-01,2026-08-15,ACTIVE\n"
        "200002,100002,CURRENT,Nagpur-East,2020-06-01,2026-08-15,ACTIVE\n"
        "200003,100003,CURRENT,Delhi-CP,2019-11-20,2026-08-15,ACTIVE\n"
        "200004,100001,SAVINGS,Pune-Main,2022-02-10,2024-01-01,DORMANT\n"
    ),
    "transactions": (
        "txn_id,from_acc,to_acc,amount,ts,channel,purpose,approved_by\n"
        "1,200001,200002,100.00,2026-07-05T09:30:00Z,IMPS,TRANSFER,\n"
        "2,200002,200003,190.00,2026-07-06T10:00:00Z,IMPS,TRANSFER,\n"
        "3,200003,200001,180.00,2026-07-08T11:00:00Z,NEFT,TRANSFER,1001\n"
        "4,200003,200001,45000.00,2026-08-01T09:40:00Z,ACH,SALARY,\n"
        "5,200001,200004,500.00,2026-07-09T20:10:00Z,UPI,TRANSFER,\n"
    ),
    "activity_log": (
        "log_id,emp_id,ts,action,target_acc,details,ip,device,off_hours,role_violation\n"
        '1,1001,2026-07-05T17:45:00Z,KYC_EDIT,200001,{"field":"phone"},10.20.1.5,branch-terminal,False,False\n'
        '2,1002,2026-07-05T18:15:00Z,KYC_EDIT,200001,{"field":"email"},10.20.2.7,branch-terminal,False,True\n'
        "3,1003,2026-07-06T03:30:00Z,LOGIN,,{},10.20.3.2,mobile-app,True,False\n"
    ),
    "ground_truth": (
        "gt_id,scenario_id,entity_type,entity_ids,is_suspicious\n"
        "1,S1,ACCOUNT,200001,True\n"
        "2,S1,ACCOUNT,200002,True\n"
        "3,S5,EMPLOYEE,1001,True\n"
        "4,L1,ACCOUNT,200004,False\n"
    ),
}


@pytest.fixture()
def mini_bundle(tmp_path: Path) -> Path:
    data_dir = tmp_path / "generated"
    data_dir.mkdir()
    files = {}
    for name, content in MINI.items():
        path = data_dir / f"{name}.csv"
        # newline="" : write bytes EXACTLY as given — Windows text-mode would turn
        # \n into \r\n and break byte-level checksums (caught on a Windows laptop).
        path.write_text(content, encoding="utf-8", newline="")
        files[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (data_dir / "meta.json").write_text(json.dumps({"files": files}), encoding="utf-8", newline="")
    return data_dir
