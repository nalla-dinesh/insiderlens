"""Ingestion service tests — idempotency, counts, FKs, checksum gate.
Full 47k-row bundle timing is proven by the verification protocol (scripts/ingest.py),
so the suite stays fast with a mini bundle."""

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.db.session import build_session_factory
from app.models.account import Account
from app.models.employee import Employee
from app.models.transaction import Transaction
from app.repositories.ground_truth_repo import all_truth
from app.schemas.ingest import IngestReport
from app.services.ingestion import IngestionService
from tests.conftest import needs_pg

pytestmark = needs_pg


async def test_ingest_counts_match_csv_and_are_idempotent(engine, mini_bundle):
    factory = build_session_factory(engine)
    report1 = await IngestionService(factory, mini_bundle).run()
    IngestReport.model_validate(report1.model_dump())  # schema round-trip

    assert report1.checksum_ok is True
    assert report1.tables["roles"].rows_in_csv == 4
    assert report1.tables["employees"].rows_in_csv == 3
    assert report1.tables["customers"].rows_in_csv == 3
    assert report1.tables["accounts"].rows_in_csv == 4
    assert report1.tables["transactions"].rows_in_csv == 5
    assert report1.tables["activity_log"].rows_in_csv == 3
    assert report1.tables["ground_truth"].rows_in_csv == 4
    assert report1.total_inserted == report1.total_rows == 26

    report2 = await IngestionService(factory, mini_bundle).run()
    assert report2.total_inserted == 0, "second run must be a no-op"
    assert all(t.inserted == 0 and t.skipped == t.rows_in_csv for t in report2.tables.values())


async def test_rows_are_queryable_with_fks(engine, mini_bundle):
    factory = build_session_factory(engine)
    await IngestionService(factory, mini_bundle).run()

    async with factory() as s:
        emp = (await s.execute(select(Employee).where(Employee.emp_id == 1001))).scalar_one()
        assert emp.role == "OFFICER" and emp.branch == "Nagpur-East"

        txn = (await s.execute(select(Transaction).where(Transaction.txn_id == 3))).scalar_one()
        assert txn.approved_by == 1001  # FK to employees resolved

        acc = (await s.execute(select(Account).where(Account.acc_id == 200004))).scalar_one()
        assert acc.status == "DORMANT" and acc.cust_id == 100001

        truth = await all_truth(s)  # EVALUATION-ONLY repo — used here in tests only
        assert len(truth) == 4 and truth[2].entity_ids == [1001]  # single-id string -> INT[]


async def test_ingest_rejects_tampered_bundle(engine, mini_bundle):
    path = mini_bundle / "transactions.csv"
    path.write_bytes(path.read_bytes() + b"\n")  # byte-level drift breaks sha256 (any OS)
    with pytest.raises(AppError) as err:
        await IngestionService(build_session_factory(engine), mini_bundle).run()
    assert err.value.code == "checksum_mismatch"
    assert err.value.status_code == 409
