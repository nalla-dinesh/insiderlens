"""ground_truth — scenario membership, one row per (scenario, entity).

⚠ LAW: the DetectionEngine must never read this table. It exists ONLY for the
EvaluationService (Phase 07). entity_ids is INT[] at DB level; ingestion wraps the
CSV's single-id string into a 1-element array.
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroundTruth(Base):
    __tablename__ = "ground_truth"

    gt_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(4), nullable=False)  # S1..S7 | L1..L5
    entity_type: Mapped[str] = mapped_column(String(12), nullable=False)  # ACCOUNT|CUSTOMER|EMPLOYEE
    entity_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, nullable=False)
