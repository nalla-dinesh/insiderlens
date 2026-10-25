"""alerts — the product. Evidence is MANDATORY at DB level (CHECK constraints), so
a score can never be shown without its receipts — this is the platform's promise."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("jsonb_array_length(reasons) > 0", name="alerts_reasons_nonempty"),
        CheckConstraint("evidence <> CAST('{}' AS JSONB)", name="alerts_evidence_nonempty"),
    )

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.run_id"), nullable=False)
    rule_set: Mapped[list[str]] = mapped_column(ARRAY(String(4)), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(12), nullable=False)  # ACCOUNT|EMPLOYEE|CUSTOMER...
    entity_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(8), nullable=False)  # LOW|MEDIUM|HIGH|CRITICAL
    reasons: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)  # [{rule, pts, text}]
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)  # graph+timeline+thresholds
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN")
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.case_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
