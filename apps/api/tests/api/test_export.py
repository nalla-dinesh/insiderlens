"""Phase 06 — evidence export: the offline ZIP an investigator opens with NO tooling.

Asserts: exactly 5 entries; report.pdf is a real PDF (%PDF magic) and >10KB on the
S5-styled real case; evidence.json parses AND re-verifies the score law;
CSV row counts match the cited ids; both PNG and no-PNG paths produce valid PDFs.
"""

from __future__ import annotations

import io
import json
import zipfile

from tests.api.conftest import critical_alert, ingest_and_run, make_case
from tests.conftest import needs_pg

pytestmark = needs_pg

EXPECTED_ENTRIES = {"report.pdf", "evidence.json", "transactions.csv", "activity_log.csv", "README.txt"}

# 1×1 red PNG — a REAL canvas snapshot surrogate (dataURL like the frontend sends)
TINY_PNG_DATAURL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


async def test_export_zip_full_contents(client, engine, crafted_bundle):
    await ingest_and_run(client, engine, crafted_bundle)
    alert = await critical_alert(client)
    case = await make_case(client, alert["alert_id"], assignee="Test Manager")

    # 404 for a case that does not exist
    missing = await client.get("/api/cases/999999/export")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "case_not_found"

    # GET path (no PNG): ZIP streams in-memory
    resp = await client.get(f"/api/cases/{case['case_id']}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    assert f"case_{case['case_id']}_evidence.zip" in resp.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert set(zf.namelist()) == EXPECTED_ENTRIES, zf.namelist()

    pdf = zf.read("report.pdf")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 10_000, len(pdf)  # real case → real content, not a stub

    ev = json.loads(zf.read("evidence.json"))
    assert ev["case"]["case_id"] == case["case_id"]
    for a in ev["alerts"]:
        assert a["score"] == sum(int(r["pts"]) for r in a["reasons"])  # score law re-verified
        assert a["score_arithmetic_verified"] is True
    assert ev["recommended_next_steps"]

    recs = ev["alerts"][0]["evidence"]["records"]
    tx_rows = zf.read("transactions.csv").decode().strip().splitlines()
    log_rows = zf.read("activity_log.csv").decode().strip().splitlines()
    assert len(tx_rows) - 1 == len(recs["txn_ids"])
    assert len(log_rows) - 1 == len(recs["log_ids"])
    assert str(recs["txn_ids"][0]) in tx_rows[1]
    assert zf.read("README.txt").decode().count("\n") >= 9  # ~10 explanatory lines


async def test_export_post_with_graph_png_valid_pdf(client, engine, crafted_bundle):
    await ingest_and_run(client, engine, crafted_bundle)
    alert = await critical_alert(client)
    case = await make_case(client, alert["alert_id"])

    resp = await client.post(
        f"/api/cases/{case['case_id']}/export",
        json={"graph_png": TINY_PNG_DATAURL},
    )
    assert resp.status_code == 200, resp.text
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert set(zf.namelist()) == EXPECTED_ENTRIES
    pdf = zf.read("report.pdf")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 10_000
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 2  # cover+arithmetic page AND the graph page
    text = " ".join((p.extract_text() or "") for p in reader.pages)
    assert str(case["case_id"]) in text
    assert "graph" in text.lower()
