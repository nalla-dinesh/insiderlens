"""accounts — `branch` matters: the F3 cross-branch modifier compares it with the
acting employee's branch (S5). `last_active_date` + `status` feed the dormant view,
but rules compute dormancy from transaction history (Phase 03)."""

from datetime import date

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_cust_id", "cust_id"),
        Index("ix_accounts_branch", "branch"),
    )

    acc_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # ids from CSV
    cust_id: Mapped[int] = mapped_column(ForeignKey("customers.cust_id"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # SAVINGS|SALARY|CURRENT|MERCHANT
    branch: Mapped[str] = mapped_column(String(40), nullable=False)
    open_date: Mapped[date] = mapped_column(nullable=False)
    last_active_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="ACTIVE")
