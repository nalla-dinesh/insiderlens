"""transactions — ~47k rows; ids come from the CSV (P2: NEVER regenerate).
Indexes chosen for the exact read patterns: ego neighborhood, time-bounded edges,
and the graph loader in Phase 03."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_tx_from_ts", "from_acc", "ts"),
        Index("ix_tx_to_ts", "to_acc", "ts"),
        Index("ix_tx_ts", "ts"),
    )

    txn_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_acc: Mapped[int] = mapped_column(ForeignKey("accounts.acc_id"), nullable=False)
    to_acc: Mapped[int] = mapped_column(ForeignKey("accounts.acc_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(8), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(24), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("employees.emp_id"), nullable=True)
