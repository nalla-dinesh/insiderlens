"""Case service (pure logic, no HTTP) — the investigation loop.

State machine enforced HERE:
    OPEN → IN_PROGRESS → ESCALATED → CLOSED_TRUE / CLOSED_FALSE
pragmatic shortcuts (documented in PHASE_06_NOTES):
    IN_PROGRESS → CLOSED_TRUE / CLOSED_FALSE
CLOSED_* is immutable — any later write returns 409 (P5).

Sequential-case rule (P4): an alert belongs to AT MOST one non-closed case;
relinking is allowed only after the previous case is CLOSED_* (Phase-07 metrics
would double-count otherwise).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.alert import Alert
from app.models.case import Case, CaseNote
from app.models.employee import Employee
from app.schemas.alerts import AlertDetail
from app.schemas.cases import CaseCreate, CasePatch, NoteCreate

CASE_STATUSES = ("OPEN", "IN_PROGRESS", "ESCALATED", "CLOSED_TRUE", "CLOSED_FALSE")
CLOSED = ("CLOSED_TRUE", "CLOSED_FALSE")
BAND_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "OPEN": ("IN_PROGRESS",),
    "IN_PROGRESS": ("ESCALATED", "CLOSED_TRUE", "CLOSED_FALSE"),
    "ESCALATED": ("CLOSED_TRUE", "CLOSED_FALSE"),
    "CLOSED_TRUE": (),
    "CLOSED_FALSE": (),
}

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


def not_found(case_id: int) -> AppError:
    return AppError(
        code="case_not_found",
        message=f"Case {case_id} does not exist.",
        status_code=404,
        details={"case_id": case_id},
    )


async def validate_assignee(session: AsyncSession, name: str | None) -> None:
    if not name:
        return
    ok = (
        await session.execute(
            select(func.count())
            .select_from(Employee)
            .where(
                Employee.name == name,
                Employee.role.in_(("MANAGER", "ADMIN")),
                Employee.status == "ACTIVE",
            )
        )
    ).scalar()
    if not ok:
        raise AppError(
            code="assignee_invalid",
            message=f"'{name}' is not an ACTIVE MANAGER/ADMIN analyst.",
            status_code=422,
            details={"assignee": name},
        )


def model_payload(case: Case, alerts: list[Alert], notes: list[CaseNote]) -> dict:
    """CaseDetail payload — alerts ride FULL (reasons + evidence), not bare ids."""
    top_band = max((a.band for a in alerts), key=lambda b: BAND_RANK[b], default=None)
    return {
        "case_id": case.case_id,
        "title": case.title,
        "assignee": case.assignee,
        "status": case.status,
        "created_at": case.created_at,
        "closed_at": case.closed_at,
        "band": top_band,
        "alert_ids": [a.alert_id for a in alerts],
        "alerts": [_alert_detail(a) for a in alerts],
        "notes": [{"note_id": n.note_id, "author": n.author, "body": n.body, "ts": n.ts} for n in notes],
        "recommendations": RECOMMENDATIONS.get(top_band or "LOW", []),
    }


def _alert_detail(a: Alert) -> dict:
    """Case-embedded alert payload: full reasons+evidence verbatim; list-only
    computed fields (max_amount / entity_counts) stay empty here — the case view
    shows the full evidence, not the queue's display hints."""
    return AlertDetail(
        alert_id=a.alert_id,
        run_id=a.run_id,
        band=a.band,
        score=a.score,
        rule_set=list(a.rule_set),
        entity_ids=list(a.entity_ids),
        entity_type=a.entity_type,
        status=a.status,
        created_at=a.created_at,
        top_reasons=[r["text"] for r in a.reasons[:3]],
        max_amount=None,
        entity_counts={},
        reasons=a.reasons,
        evidence=a.evidence,
    ).model_dump(mode="json")


async def load_case(session: AsyncSession, case_id: int):
    case = (await session.execute(select(Case).where(Case.case_id == case_id))).scalar_one_or_none()
    if case is None:
        raise not_found(case_id)
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
    return case, alerts, notes


async def list_board(session: AsyncSession) -> dict:
    cases = (await session.execute(select(Case).order_by(Case.created_at.desc()))).scalars().all()
    alert_rows = (
        await session.execute(select(Alert.case_id, Alert.band).where(Alert.case_id.is_not(None)))
    ).all()
    band_by_case: dict[int, str] = {}
    count_by_case: dict[int, int] = {}
    for case_id, band in alert_rows:
        count_by_case[case_id] = count_by_case.get(case_id, 0) + 1
        cur = band_by_case.get(case_id)
        if cur is None or BAND_RANK[band] > BAND_RANK[cur]:
            band_by_case[case_id] = band
    grouped: dict[str, list[dict]] = {s: [] for s in CASE_STATUSES}
    for c in cases:
        grouped[c.status].append(
            {
                "case_id": c.case_id,
                "title": c.title,
                "assignee": c.assignee,
                "status": c.status,
                "created_at": c.created_at,
                "closed_at": c.closed_at,
                "alert_count": count_by_case.get(c.case_id, 0),
                "band": band_by_case.get(c.case_id),
            }
        )
    return {"statuses": CASE_STATUSES, "groups": grouped}


async def list_analysts(session: AsyncSession) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(Employee)
                .where(Employee.role.in_(("MANAGER", "ADMIN")), Employee.status == "ACTIVE")
                .order_by(Employee.role, Employee.name)
            )
        )
        .scalars()
        .all()
    )
    return [{"emp_id": e.emp_id, "name": e.name, "role": e.role, "branch": e.branch} for e in rows]


async def create_from_alert(session: AsyncSession, body: CaseCreate) -> dict:
    alert = (await session.execute(select(Alert).where(Alert.alert_id == body.alert_id))).scalar_one_or_none()
    if alert is None:
        raise AppError(
            code="alert_not_found",
            message=f"Alert {body.alert_id} does not exist.",
            status_code=404,
            details={"alert_id": body.alert_id},
        )
    if alert.case_id is not None:
        owner = (await session.execute(select(Case).where(Case.case_id == alert.case_id))).scalar_one()
        if owner.status not in CLOSED:
            raise AppError(
                code="alert_case_conflict",
                message=(
                    f"Alert AL-{body.alert_id:06d} is already linked to open case "
                    f"{owner.case_id} ({owner.status}). Close it first (sequential rule, P4)."
                ),
                status_code=409,
                details={"alert_id": body.alert_id, "case_id": owner.case_id},
            )

    await validate_assignee(session, body.assignee)

    if body.title and body.title.strip():
        title = body.title.strip()[:200]
    else:
        top = alert.reasons[0]["text"] if alert.reasons else "unspecified pattern"
        title = f"[{alert.band}] {top} · {len(alert.entity_ids)} entities"[:200]

    case = Case(title=title, assignee=body.assignee or None, status="OPEN")
    session.add(case)
    await session.flush()
    alert.case_id = case.case_id
    session.add(
        CaseNote(
            case_id=case.case_id,
            author="system",
            body=(
                f"Case created from alert AL-{alert.alert_id:06d} (band {alert.band}, score {alert.score})."
            ),
        )
    )
    await session.commit()
    case, alerts, notes = await load_case(session, case.case_id)
    return model_payload(case, alerts, notes)


async def patch_case(session: AsyncSession, case_id: int, body: CasePatch) -> dict:
    case, _, _ = await load_case(session, case_id)
    if case.status in CLOSED:
        raise AppError(
            code="case_closed",
            message=f"Case {case_id} is {case.status} — closed cases are immutable (P5).",
            status_code=409,
            details={"case_id": case_id, "status": case.status},
        )
    actor = body.actor or "analyst"
    audit: list[str] = []

    if body.title is not None and body.title.strip() and body.title.strip() != case.title:
        case.title = body.title.strip()[:200]
        audit.append(f"Title updated by {actor}.")

    if body.assignee is not None and body.assignee != case.assignee:
        await validate_assignee(session, body.assignee)
        audit.append(f"Assignee changed {case.assignee or '—'} → {body.assignee or '—'} by {actor}.")
        case.assignee = body.assignee or None

    if body.status is not None and body.status != case.status:
        legal = TRANSITIONS[case.status]
        if body.status not in legal:
            raise AppError(
                code="illegal_transition",
                message=(
                    f"Illegal transition {case.status} → {body.status}. "
                    f"Legal from {case.status}: {list(legal) or 'none (terminal state)'}."
                ),
                status_code=409,
                details={"from_state": case.status, "to_state": body.status, "legal": list(legal)},
            )
        audit.append(f"Status {case.status} → {body.status} by {actor}.")
        case.status = body.status
        if body.status in CLOSED:
            case.closed_at = datetime.now(UTC)

    for entry in audit:
        session.add(CaseNote(case_id=case.case_id, author="system", body=entry))
    await session.commit()
    case, alerts, notes = await load_case(session, case_id)
    return model_payload(case, alerts, notes)


async def add_note(session: AsyncSession, case_id: int, body: NoteCreate) -> dict:
    case, _, notes = await load_case(session, case_id)
    if case.status in CLOSED:
        raise AppError(
            code="case_closed",
            message=f"Case {case_id} is closed — notes are immutable too.",
            status_code=409,
            details={"case_id": case_id},
        )
    note = CaseNote(case_id=case.case_id, author=body.author or "analyst", body=body.body)
    session.add(note)
    await session.commit()
    return {"note_id": note.note_id, "case_id": case.case_id, "notes_count": len(notes) + 1}
