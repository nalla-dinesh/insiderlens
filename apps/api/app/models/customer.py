"""customers — KYC profile; phone indexed for contact-cluster evidence."""

from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    cust_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    occupation: Mapped[str] = mapped_column(String(60), nullable=False)
    declared_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    kyc_risk: Mapped[str] = mapped_column(String(8), nullable=False)  # LOW | MEDIUM | HIGH
    phone: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
