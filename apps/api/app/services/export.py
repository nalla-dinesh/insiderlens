"""Evidence ZIP export — one click, offline-openable, no server disk writes (P1).

Contents (exactly 5 entries — tests assert):
    report.pdf         ReportLab: cover, FULL score arithmetic (every reason),
                       graph page (PNG from frontend canvas, else text adjacency),
                       activity timeline, thresholds, recommendations, footer.
    evidence.json      case + alerts (reasons + evidence verbatim) — machine-usable.
    transactions.csv   every txn cited in evidence.records.txn_ids (real columns).
    activity_log.csv   every cited employee log.
    README.txt         10 lines explaining each file.

PNG input: front-end passes a dataURL (cy.png); query strings cannot safely carry
multi-MB payloads through HTTP stacks, so the image rides in the POST body;
GET (no image) stays for curl/jq flows.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.alert import Alert
from app.models.case import Case, CaseNote
from app.models.transaction import Transaction

BAND_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

RECOMMENDATIONS: dict[str, list[str]] = {
    "CRITICAL": [
        "Freeze outbound legs on every cited account (temporary hold ≤ 48h).",
        "Interview the cited employee within 24h; temporarily lock their role.",
        "Extend the ego graph to depth 2 — enumerate every shell ring.",
        "File a preliminary STR with this evidence bundle attached.",
    ],
    "HIGH": [
        "Place cited accounts on enhanced monitoring.",
        "Ask the employee's manager for context on cited actions.",
        "Re-run analysis after the next batch; watch for repeat_pattern growth.",
    ],
    "MEDIUM": [
        "Schedule a routine review within 7 days.",
        "Watch recurrence — a second occurrence escalates the band automatically.",
    ],
    "LOW": [
        "No immediate action; archive with a note.",
        "Link to an existing case only if the same entity reappears.",
    ],
}


def _plain(text: str) -> str:
    return re.sub(r"\*\*|\[|\]", "", text)


def _jsonable(obj):  # noqa: ANN202 — json.dumps default hook
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _inr(n: float | Decimal | None) -> str:
    try:
        return f"₹{float(n or 0):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _ts(ts) -> str:  # noqa: ANN001
    if isinstance(ts, datetime):
        return ts.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    return str(ts)


async def _bundle(session: AsyncSession, case_id: int) -> dict:
    case = (await session.execute(select(Case).where(Case.case_id == case_id))).scalar_one_or_none()
    if case is None:
        raise AppError(
            code="case_not_found",
            message=f"Case {case_id} does not exist.",
            status_code=404,
            details={"case_id": case_id},
        )
    alerts = list(
        (await session.execute(select(Alert).where(Alert.case_id == case_id).order_by(Alert.score.desc())))
        .scalars()
        .all()
    )
    notes = list(
        (
            await session.execute(
                select(CaseNote).where(CaseNote.case_id == case_id).order_by(CaseNote.ts, CaseNote.note_id)
            )
        )
        .scalars()
        .all()
    )
    txn_ids: set[int] = set()
    log_ids: set[int] = set()
    for a in alerts:
        recs = (a.evidence or {}).get("records") or {}
        txn_ids.update(int(x) for x in recs.get("txn_ids", []) or [])
        log_ids.update(int(x) for x in recs.get("log_ids", []) or [])
    txns = (
        list(
            (
                await session.execute(
                    select(Transaction).where(Transaction.txn_id.in_(txn_ids)).order_by(Transaction.ts)
                )
            )
            .scalars()
            .all()
        )
        if txn_ids
        else []
    )
    logs = (
        list(
            (
                await session.execute(
                    select(ActivityLog).where(ActivityLog.log_id.in_(log_ids)).order_by(ActivityLog.ts)
                )
            )
            .scalars()
            .all()
        )
        if log_ids
        else []
    )
    band = max((a.band for a in alerts), key=lambda b: BAND_RANK[b], default="LOW")
    return {
        "case": case,
        "alerts": alerts,
        "notes": notes,
        "txns": txns,
        "logs": logs,
        "band": band,
    }


# ---------------------------------------------------------------- PDF ----
_BODY = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#334155")
)
_SMALL = ParagraphStyle(
    "small", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#475569")
)
_H = ParagraphStyle(
    "h",
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=16,
    spaceBefore=10,
    textColor=colors.HexColor("#0e2a47"),
)
_TBL_STYLE = TableStyle(
    [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e2a47")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
)


def _footer(canvas, doc, case_id: int) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawString(
        1.6 * cm,
        1.0 * cm,
        f"Generated by InsiderLens — synthetic data · case {case_id} · page {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def build_pdf(bundle: dict, case: Case, graph_png: bytes | None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.6 * cm,
        title=f"Case {case.case_id} evidence",
    )
    generated = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
    el: list = []

    # ---- cover block
    el.append(Paragraph("InsiderLens — Evidence Report", ParagraphStyle("t", parent=_H, fontSize=18)))
    el.append(Spacer(1, 6))
    cover_rows = [
        ["Case", f"#{case.case_id}", "Band", bundle["band"]],
        ["Title", Paragraph(case.title, _BODY), "Status", case.status],
        ["Assignee", case.assignee or "—", "Generated (UTC)", generated],
        [
            "Linked alerts",
            ", ".join(f"AL-{a.alert_id:06d}" for a in bundle["alerts"]) or "—",
            "Closed at",
            _ts(case.closed_at) if case.closed_at else "—",
        ],
    ]
    t = Table(cover_rows, colWidths=[2.6 * cm, 9.6 * cm, 2.6 * cm, 3 * cm])
    t.setStyle(_TBL_STYLE)
    el.append(t)

    # ---- score arithmetic (EVERY reason — PDF table, never raw drawString overflow: P2)
    for a in bundle["alerts"]:
        el.append(Paragraph(f"Score arithmetic — AL-{a.alert_id:06d} (score {a.score}, band {a.band})", _H))
        rows = [["Rule", "+pts", "Why (verbatim reason)"]]
        total = 0
        for r in a.reasons:
            total += int(r["pts"])
            rows.append([r["rule"], f"+{r['pts']}", Paragraph(re.sub(r"\*\*", "", r["text"]), _SMALL)])
        match = "✓ verified" if total == a.score else f"✗ MISMATCH (Σ={total})"
        rows.append(["TOTAL", f"{total}", Paragraph(f"Score on record: {a.score} — {match}", _SMALL)])
        t = Table(rows, colWidths=[1.6 * cm, 1.4 * cm, 14.8 * cm], repeatRows=1)
        t.setStyle(_TBL_STYLE)
        el.append(t)

    # ---- narrative + how-to-read + rules reference (investigator opens this OFFLINE)
    first = bundle["alerts"][0] if bundle["alerts"] else None
    if first is not None:
        story = (
            f"Case #{case.case_id} was raised from alert AL-{first.alert_id:06d} "
            f"(band {bundle['band']}, score {first.score}). "
            f"The strongest signal is: {_plain(first.reasons[0]['text'] if first.reasons else 'n/a')}. "
            f"Cited entities: {', '.join(map(str, first.entity_ids))}. "
            f"Every reason below carries its own point value — the alert score equals the "
            f"exact sum of those values (verified in evidence.json per alert)."
        )
        el.append(Paragraph("Case narrative", _H))
        el.append(Paragraph(story, _BODY))

    el.append(Paragraph("How the detection engine reasons (reference)", _H))
    rules_ref = [
        ["Rule", "Family", "What it detects"],
        ["T1", "transactions", "circular routing — money leaves an account and returns via hops"],
        ["T2", "transactions", "funnel fan-in / fan-out beyond account norms"],
        ["T3", "transactions", "dormancy wake-ups — dormant accounts generating bursts"],
        ["T4", "transactions", "pass-through (wash) — near-in/out symmetry in short windows"],
        ["T5", "transactions", "structurally abnormal accounts (giant daily volume vs type)"],
        ["T6", "transactions", "velocity spikes — many legs in a short burst"],
        ["E1", "employee", "sensitive actions in the 22:00–06:00 IST night window"],
        ["E2", "employee", "actions outside the role's allowed permission set"],
        ["E3", "employee", "behaviour >3× personal norm AND >3× role peers (min 5/day)"],
        ["E4", "employee", "multiple config changes on one account in a day"],
        ["E5", "employee", "burst of ≥4 sensitive actions inside 24h"],
        ["F1", "fusion", "employee action followed by a transaction pattern ≤72h later"],
        ["F2", "fusion", "DISABLE_ALERT action within 72h of a high-value pattern"],
        ["F3", "fusion", "cross-branch approval of a leg that is part of a T-pattern"],
    ]
    t = Table(
        [[Paragraph(c, _SMALL) for c in r] for r in rules_ref],
        colWidths=[1.4 * cm, 2.4 * cm, 14.0 * cm],
        repeatRows=1,
    )
    t.setStyle(_TBL_STYLE)
    el.append(t)

    el.append(PageBreak())

    # ---- graph page
    el.append(Paragraph("Money-flow graph (cited evidence)", _H))
    if graph_png:
        img = Image(io.BytesIO(graph_png), width=17 * cm, height=17 * cm * 9 / 16 * 1.6)
        img.hAlign = "CENTER"
        el.append(img)
        el.append(Paragraph("Adjacency list (machine-readable backing of the image):", _BODY))
    else:
        el.append(Paragraph("Adjacency list (canvas snapshot not attached):", _BODY))
    lines: list[str] = []
    for a in bundle["alerts"]:
        g = (a.evidence or {}).get("graph") or {}
        for e in (g.get("edges") or [])[:40]:
            lines.append(
                f"  {e.get('source')} → {e.get('target')}  {_inr(e.get('amount'))}  "
                f"({e.get('channel', '—')} · {_ts(e.get('ts'))})"
            )
    if not lines:
        lines.append("  (no cited edges)")
    for line in lines:
        el.append(Paragraph(line, _SMALL))

    # cited account nodes table
    nodes: dict[int, dict] = {}
    for a in bundle["alerts"]:
        for n in ((a.evidence or {}).get("graph") or {}).get("nodes") or []:
            nodes[int(n["id"])] = n
    if nodes:
        el.append(Paragraph(f"Cited accounts ({len(nodes)})", _H))
        rows = [["acc_id", "type", "branch", "status", "cust_id"]]
        for n in sorted(nodes.values(), key=lambda x: int(x["id"])):
            rows.append(
                [
                    str(n["id"]),
                    str(n.get("type", "—")),
                    str(n.get("branch", "—")),
                    str(n.get("status", "—")),
                    str(n.get("cust_id", "—")),
                ]
            )
        t = Table(rows, colWidths=[2.6 * cm, 2.4 * cm, 5.0 * cm, 2.4 * cm, 2.4 * cm], repeatRows=1)
        t.setStyle(_TBL_STYLE)
        el.append(t)

    # ---- thresholds
    for a in bundle["alerts"]:
        gates = (a.evidence or {}).get("thresholds") or {}
        if gates:
            el.append(Paragraph(f"Threshold gates — AL-{a.alert_id:06d}", _H))
            rows = [["Gate", "Observed", "Limit", "Source"]]
            for key, gate in gates.items():
                rows.append(
                    [
                        Paragraph(str(key), _SMALL),
                        str(gate["observed"]),
                        str(gate["limit"]),
                        Paragraph(str(gate["source"]), _SMALL),
                    ]
                )
            t = Table(rows, colWidths=[6.6 * cm, 3.4 * cm, 3.4 * cm, 4.4 * cm], repeatRows=1)
            t.setStyle(_TBL_STYLE)
            el.append(t)

    # ---- timeline
    el.append(Paragraph("Activity timeline (cited events)", _H))
    tl_rows = [["When (UTC)", "Type", "Actor", "What happened"]]
    events: list[dict] = []
    for a in bundle["alerts"]:
        events.extend((a.evidence or {}).get("timeline") or [])
    events = sorted({(e["ts"], e["ref_id"], e["kind"]): e for e in events}.values(), key=lambda e: e["ts"])
    for e in events[:120]:
        tl_rows.append(
            [
                Paragraph(_ts(e["ts"]), _SMALL),
                e["kind"],
                str(e.get("ref_id", "—")),
                Paragraph(re.sub(r"\*\*", "", str(e["label"])), _SMALL),
            ]
        )
    if len(tl_rows) == 1:
        tl_rows.append(["—", "—", "—", "no cited events"])
    t = Table(tl_rows, colWidths=[3.6 * cm, 2.2 * cm, 1.8 * cm, 10.2 * cm], repeatRows=1)
    t.setStyle(_TBL_STYLE)
    el.append(t)
    if len(events) > 120:
        el.append(Paragraph(f"… {len(events) - 120} further events in evidence.json", _SMALL))

    # ---- cited transactions + cited employee activity (the raw truth, tabulated)
    if bundle["txns"]:
        el.append(Paragraph(f"Cited transactions ({len(bundle['txns'])})", _H))
        rows = [["txn", "From → To", "Amount", "When (UTC)", "Channel", "Approver"]]
        for t in bundle["txns"]:
            rows.append(
                [
                    str(t.txn_id),
                    f"{t.from_acc} → {t.to_acc}",
                    _inr(t.amount),
                    _ts(t.ts),
                    t.channel,
                    str(t.approved_by or "—"),
                ]
            )
        t = Table(rows, colWidths=[1.7 * cm, 3.8 * cm, 2.6 * cm, 4.2 * cm, 2.0 * cm, 1.9 * cm], repeatRows=1)
        t.setStyle(_TBL_STYLE)
        el.append(t)

    if bundle["logs"]:
        el.append(Paragraph(f"Cited employee actions ({len(bundle['logs'])})", _H))
        rows = [["log", "Employee", "When (UTC)", "Action", "Target a/c", "Details"]]
        for log_row in bundle["logs"]:
            details = (
                json.dumps(log_row.details, default=_jsonable)
                if isinstance(log_row.details, dict)
                else str(log_row.details)
            )
            rows.append(
                [
                    str(log_row.log_id),
                    str(log_row.emp_id),
                    _ts(log_row.ts),
                    log_row.action,
                    str(log_row.target_acc or "—"),
                    Paragraph(details[:160], _SMALL),
                ]
            )
        t = Table(rows, colWidths=[1.4 * cm, 1.9 * cm, 4.2 * cm, 3.2 * cm, 2.2 * cm, 4.9 * cm], repeatRows=1)
        t.setStyle(_TBL_STYLE)
        el.append(t)

    # ---- recommendations + notes
    el.append(Paragraph("Recommended next steps", _H))
    for rec in RECOMMENDATIONS.get(bundle["band"], []):
        el.append(Paragraph(f"• {rec}", _BODY))
    if bundle["notes"]:
        el.append(Paragraph("Case notes (audit trail)", _H))
        for n in bundle["notes"]:
            el.append(Paragraph(f"{_ts(n.ts)} — <b>{n.author}</b>: {n.body}", _SMALL))

    doc.build(
        el,
        onFirstPage=lambda c, d: _footer(c, d, case.case_id),
        onLaterPages=lambda c, d: _footer(c, d, case.case_id),
    )
    return buf.getvalue()


# ---------------------------------------------------------------- zip ----
def _decode_png(data_url: str) -> bytes:
    head, _, b64 = data_url.partition(",")
    if "base64" not in head:
        raise ValueError("graph_png must be a base64 dataURL")
    raw = base64.b64decode(b64)
    if not raw.startswith(b"\x89PNG"):
        raise ValueError("graph_png is not a PNG image")
    return raw


async def build_case_zip_response(
    session: AsyncSession, case_id: int, graph_png_url: str | None
) -> StreamingResponse:
    bundle = await _bundle(session, case_id)
    case: Case = bundle["case"]

    png: bytes | None = None
    if graph_png_url:
        png = _decode_png(graph_png_url)

    pdf_bytes = build_pdf(bundle, case, png)

    evidence = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case": {
            "case_id": case.case_id,
            "title": case.title,
            "status": case.status,
            "assignee": case.assignee,
            "created_at": case.created_at,
            "closed_at": case.closed_at,
            "band": bundle["band"],
        },
        "alerts": [
            {
                "alert_id": a.alert_id,
                "run_id": a.run_id,
                "band": a.band,
                "score": a.score,
                "rule_set": a.rule_set,
                "entity_ids": a.entity_ids,
                "entity_type": a.entity_type,
                "status": a.status,
                "reasons": a.reasons,
                "evidence": a.evidence,
                "score_arithmetic_verified": sum(int(r["pts"]) for r in a.reasons) == a.score,
            }
            for a in bundle["alerts"]
        ],
        "notes": [{"author": n.author, "ts": n.ts, "body": n.body} for n in bundle["notes"]],
        "recommended_next_steps": RECOMMENDATIONS.get(bundle["band"], []),
    }

    tx_io = io.StringIO()
    w = csv.writer(tx_io)
    w.writerow(["txn_id", "from_acc", "to_acc", "amount", "ts", "channel", "purpose", "approved_by"])
    for t in bundle["txns"]:
        w.writerow(
            [
                t.txn_id,
                t.from_acc,
                t.to_acc,
                str(t.amount),
                t.ts.isoformat(),
                t.channel,
                t.purpose or "",
                t.approved_by or "",
            ]
        )
    log_io = io.StringIO()
    w = csv.writer(log_io)
    w.writerow(["log_id", "emp_id", "ts", "action", "target_acc", "details", "ip", "device"])
    for log_row in bundle["logs"]:
        w.writerow(
            [
                log_row.log_id,
                log_row.emp_id,
                log_row.ts.isoformat(),
                log_row.action,
                log_row.target_acc or "",
                json.dumps(log_row.details, default=_jsonable),
                log_row.ip,
                log_row.device,
            ]
        )

    readme = (
        f"InsiderLens evidence bundle (case {case.case_id})\n"
        "1. report.pdf        — human-readable: cover, score arithmetic, graph, timeline, thresholds\n"
        "2. evidence.json     — machine-usable: case + alerts + reasons + evidence (verbatim)\n"
        "3. transactions.csv  — every cited transaction leg (real db columns)\n"
        "4. activity_log.csv  — every cited employee action (log rows)\n"
        "5. README.txt        — this file\n"
        "Score law: each alert's score == sum of its reasons' +pts (verified flag inside JSON).\n"
        "All amounts INR (en-IN grouping in PDF); timestamps UTC.\n"
        "The PNG graph page appears when the exporting analyst attached the canvas snapshot;\n"
        "otherwise the graph is rendered as a text adjacency list.\n"
        "Generated by InsiderLens — synthetic data, Phase 06.\n"
    )

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.pdf", pdf_bytes)
        zf.writestr("evidence.json", json.dumps(evidence, default=_jsonable, indent=2))
        zf.writestr("transactions.csv", tx_io.getvalue())
        zf.writestr("activity_log.csv", log_io.getvalue())
        zf.writestr("README.txt", readme)
    zbuf.seek(0)
    return StreamingResponse(
        zbuf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="case_{case_id}_evidence.zip"',
            "Content-Length": str(zbuf.getbuffer().nbytes),
        },
    )
