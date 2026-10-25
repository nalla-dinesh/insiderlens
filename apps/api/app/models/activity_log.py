"""activity_log — what employees DID to accounts. The E-rules' raw material.
flags off_hours/role_violation are generated hints; Phase 04 re-derives E1/E2 from
first principles (IST night window + roles table) so the engine never trusts data it
can itself verify."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base


class ActivityLog(Base):
    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_log_emp_ts", "emp_id", "ts"),
        Index("ix_log_action", "action"),
        Index("ix_log_target_acc", "target_acc"),
    )

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.emp_id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    target_acc: Mapped[int | None] = mapped_column(ForeignKey("accounts.acc_id"), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip: Mapped[str] = mapped_column(String(20), nullable=False)
    device: Mapped[str] = mapped_column(String(24), nullable=False)
    off_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role_violation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
