"""roles + employees. role FK points at roles.role_name (natural key)."""

from datetime import date

from sqlalchemy import ARRAY, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    role_name: Mapped[str] = mapped_column(String(16), primary_key=True)
    allowed_actions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Employee(Base):
    __tablename__ = "employees"

    emp_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # ids from CSV, never serial
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(ForeignKey("roles.role_name"), nullable=False)
    branch: Mapped[str] = mapped_column(String(40), nullable=False)
    join_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
